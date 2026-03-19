"""CLI entry points for best-practices-rag.

Subcommands:
    install       — copy agents, commands, and references to .claude/
    setup-db      — start Neo4j via Docker and apply schema
    setup-schema  — apply schema to an existing Neo4j instance (no Docker required)
    check         — validate installation
    query-kb      — query Neo4j knowledge base for best practices
    search-exa    — search Exa for best practices
    store-result  — store synthesized best practice into Neo4j
    init          — one-command setup (create .env, install, setup-db, check)
    uninstall     — remove installed .claude/ files
"""

import argparse
import json
import logging
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any


from best_practices_rag.config import get_settings
from best_practices_rag.graph_store import GraphStore
from best_practices_rag.knowledge_base import query_knowledge_base, summarize_neo4j_results
from best_practices_rag.logging_setup import configure_skill_logging
from best_practices_rag.parser import build_synthesized_bundle
from best_practices_rag.search import search_best_practices
from best_practices_rag.setup_schema import main as setup_main
from best_practices_rag.staleness import check_staleness, load_current_versions
from best_practices_rag.storage import store_results
from neo4j import GraphDatabase


def _bundle_root() -> Path:
    return Path(str(files("best_practices_rag") / "_claude_files"))


def _copy_tree(src: Path, dst: Path, *, force: bool) -> list[str]:
    copied: list[str] = []
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.exists() and not force:
            print(f"  skip (exists): {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(str(rel))
        print(f"  copied: {target}")
    return copied


def cmd_install(args: argparse.Namespace) -> None:
    bundle = _bundle_root()
    project_root = Path.cwd()
    claude_dir = project_root / ".claude"
    force = args.force

    print("Installing best-practices-rag files...\n")

    # Copy commands
    _copy_tree(bundle / "commands", claude_dir / "commands", force=force)

    # Copy agents
    _copy_tree(bundle / "agents", claude_dir / "agents", force=force)

    # Copy skills
    _copy_tree(
        bundle / "skills" / "best-practices-rag",
        claude_dir / "skills" / "best-practices-rag",
        force=force,
    )

    # Copy .env.example if not present
    env_example = project_root / ".env.example"
    if not env_example.exists() or force:
        shutil.copy2(bundle / "infra" / ".env.example", env_example)
        print(f"  copied: {env_example}")

    # Create directories
    for d in [".best-practices", "logs"]:
        (project_root / d).mkdir(exist_ok=True)
        print(f"  created dir: {d}/")

    print("\nInstall complete.")
    print("\nNext steps:")
    print()
    print("Standalone Neo4j (Docker):")
    print("  1. best-practices-rag init         (one command: .env + Docker + schema + check)")
    print("  OR step by step:")
    print("  1. cp .env.example .env            (then set NEO4J_PASSWORD)")
    print("  2. best-practices-rag setup-db")
    print("  3. best-practices-rag check")
    print()
    print("Existing Neo4j (already running):")
    print("  1. cp .env.example .env            (then set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)")
    print("  2. best-practices-rag setup-schema")
    print("  3. best-practices-rag check")
    print()
    print("Then: Use /bp <technologies> in Claude Code")


def cmd_setup_db(args: argparse.Namespace) -> None:
    # Check docker is available
    for cmd in ["docker", "docker compose"]:
        binary = cmd.split()[0]
        if shutil.which(binary) is None:
            print(f"Error: '{binary}' not found. Docker is required for Neo4j.")
            sys.exit(1)

    project_root = Path.cwd()
    bundle = _bundle_root()

    # Copy docker-compose.yml
    compose_file = project_root / "docker-compose.yml"
    if not compose_file.exists():
        shutil.copy2(bundle / "infra" / "docker-compose.yml", compose_file)
        print("Copied docker-compose.yml")

    # Create secrets directory
    secrets_dir = project_root / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    auth_file = secrets_dir / "neo4j_auth_dev"
    if not auth_file.exists():
        password = "changeme"
        env_file = project_root / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("NEO4J_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
                    break
        auth_file.write_text(f"neo4j/{password}\n")
        print(f"Created secrets/neo4j_auth_dev (password: {password})")
        if password == "changeme":
            print("  Change this before production use!")

    # Start Neo4j
    print("\nStarting Neo4j via Docker...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    if result.returncode != 0:
        print(f"Error starting Neo4j:\n{result.stderr}")
        sys.exit(1)
    print(result.stdout)

    # Wait for health check
    print("Waiting for Neo4j to be ready...")
    timeout = 120
    interval = 5
    elapsed = 0
    while elapsed < timeout:
        check = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )
        if "healthy" in check.stdout.lower():
            print("Neo4j is ready.")
            break
        time.sleep(interval)
        elapsed += interval
        print(f"  waiting... ({elapsed}s / {timeout}s)")
    else:
        print(f"Warning: Neo4j did not become healthy within {timeout}s.")
        print("It may still be starting. Check with: docker compose ps")

    # Apply schema
    print("\nApplying database schema...")
    try:
        setup_main()
        print("Schema applied successfully.")
    except Exception as e:
        print(f"Schema setup failed: {e}")
        print("You can retry later with: best-practices-rag setup-db")
        sys.exit(1)


def cmd_setup_schema(args: argparse.Namespace) -> None:
    print("Applying database schema...")
    try:
        setup_main()
        print("Schema applied successfully.")
    except Exception as e:
        print(f"Schema setup failed: {e}")
        sys.exit(1)


def cmd_check(args: argparse.Namespace) -> None:
    project_root = Path.cwd()
    claude_dir = project_root / ".claude"
    all_ok = True

    print("Checking best-practices-rag installation...\n")

    # Check .claude/ files
    expected_files = [
        "commands/bp.md",
        "commands/bpr.md",
        "agents/bp-synthesizer.md",
        "agents/bp-gap-handler.md",
        "skills/best-practices-rag/references/synthesis-format.md",
        "skills/best-practices-rag/references/synthesis-format-codegen.md",
        "skills/best-practices-rag/references/synthesis-format-research.md",
        "skills/best-practices-rag/references/tech-versions.md",
    ]
    for f in expected_files:
        path = claude_dir / f
        if path.exists():
            print(f"  [pass] .claude/{f}")
        else:
            print(f"  [FAIL] .claude/{f} — missing")
            all_ok = False

    # Check Neo4j connectivity
    print()
    try:
        settings = get_settings()

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
        )
        driver.verify_connectivity()
        driver.close()
        print("  [pass] Neo4j connection")
    except Exception as e:
        print(f"  [FAIL] Neo4j connection — {e}")
        all_ok = False

    # Check Exa API key
    try:
        settings = get_settings()
        key = settings.exa_api_key.get_secret_value()
        if key:
            print("  [pass] Exa API key configured")
        else:
            print("  [info] Exa API key not set (optional — needed for /bp gap-fill)")
    except Exception:
        print("  [info] Exa API key not set (optional — needed for /bp gap-fill)")

    print()
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed. See above for details.")
        sys.exit(1)


def cmd_query_kb(args: argparse.Namespace) -> None:
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "query_kb invoked — tech=%r topics=%r languages=%r include_bodies=%r",
        args.tech,
        args.topics,
        args.languages,
        args.include_bodies,
    )

    tech_names = [t.strip() for t in args.tech.split(",") if t.strip()]
    topic_keywords = [t.strip().lower() for t in args.topics.split(",") if t.strip()]
    lang_names = (
        [lang.strip() for lang in args.languages.split(",") if lang.strip()]
        if args.languages
        else None
    )

    settings = get_settings()
    graph_store = GraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
    )

    current_versions = load_current_versions(
        Path("./.claude/skills/best-practices-rag/references")
    )

    query = " ".join(tech_names + topic_keywords)
    results = query_knowledge_base(
        query=query,
        graph_store=graph_store,
        tech_names=tech_names,
        topic_keywords=topic_keywords,
        lang_names=lang_names,
    )

    for result in results:
        staleness = check_staleness(result, current_versions)
        result["is_stale"] = staleness["is_stale"]
        result["staleness_reason"] = staleness["reason"]
        result["stale_technologies"] = staleness["stale_technologies"]
        result["fresh_technologies"] = staleness["fresh_technologies"]
        result["version_deltas"] = staleness["version_deltas"]
        result["document_age_days"] = staleness["document_age_days"]

    summary = summarize_neo4j_results(results)

    if args.include_bodies:
        slim_results = results
    else:
        slim_results = [
            {k: v for k, v in r.items() if k != "body" or r.get("is_stale")}
            for r in results
        ]

    log.debug("query_kb complete — %d results returned", len(results))
    output = {
        "count": len(results),
        "results": slim_results,
        "summary": summary,
    }
    print(json.dumps(output))


def cmd_search_exa(args: argparse.Namespace) -> None:
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "search_exa invoked — query=%r exclude_domains=%r cutoff_date=%r num_results=%d top_n=%d category=%r",
        args.query,
        args.exclude_domains,
        args.cutoff_date,
        args.num_results,
        args.top_n,
        args.category,
    )

    exclude_domains = (
        [d.strip() for d in args.exclude_domains.split(",") if d.strip()]
        if args.exclude_domains
        else None
    )

    results = search_best_practices(
        query=args.query,
        num_results=args.num_results,
        exclude_domains=exclude_domains,
        start_published_date=args.cutoff_date,
        category=args.category,
    )

    log.debug(
        "search_exa complete — %d total results, returning top %d",
        len(results),
        args.top_n,
    )
    top_results = results[: args.top_n]
    output = {
        "count": len(results),
        "results": [
            {
                "url": r.url,
                "title": r.title,
                "summary": r.summary,
                "published_date": r.published_date,
                "text": r.text,
            }
            for r in top_results
        ],
    }
    print(json.dumps(output))


def cmd_store_result(args: argparse.Namespace) -> None:
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "store_result invoked — tech=%r query=%r content_file=%r source_urls=%r languages=%r tech_versions=%r source_tiers=%r",
        args.tech,
        args.query,
        args.content_file,
        args.source_urls,
        args.languages,
        args.tech_versions,
        args.source_tiers,
    )

    tech_names = [t.strip() for t in args.tech.split(",") if t.strip()]
    source_urls = (
        [u.strip() for u in args.source_urls.split(",") if u.strip()]
        if args.source_urls
        else []
    )
    lang_names = (
        [lang.strip() for lang in args.languages.split(",") if lang.strip()]
        if args.languages
        else None
    )
    tech_versions = json.loads(args.tech_versions) if args.tech_versions else None
    source_tiers = json.loads(args.source_tiers) if args.source_tiers else None

    content_path = Path(args.content_file)
    synthesized_content = content_path.read_text(encoding="utf-8")

    bundle = build_synthesized_bundle(
        synthesized_content=synthesized_content,
        tech_names=tech_names,
        source_urls=source_urls,
        query=args.query,
        lang_names=lang_names,
        tech_versions=tech_versions,
        source_tiers=source_tiers,
    )

    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    node_name = bp_nodes[0].name if bp_nodes else ""

    settings = get_settings()
    graph_store = GraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
    )

    nodes_count = store_results(bundle, graph_store)

    log.debug(
        "store_result complete — node_name=%r nodes=%d relations=%d",
        node_name,
        nodes_count,
        len(bundle.relations),
    )
    output = {
        "stored": True,
        "node_name": node_name,
        "nodes_count": nodes_count,
        "relations_count": len(bundle.relations),
    }
    print(json.dumps(output))


def cmd_init(args: argparse.Namespace) -> None:
    project_root = Path.cwd()
    password = args.password or secrets.token_urlsafe(16)

    # Write .env
    env_file = project_root / ".env"
    env_content = (
        f"NEO4J_URI=bolt://localhost:7687\n"
        f"NEO4J_USERNAME=neo4j\n"
        f"NEO4J_PASSWORD={password}\n"
        f"\n"
        f"# Optional — Exa API for web search (enables /bp gap-fill)\n"
        f"# EXA_API_KEY=your-exa-api-key-here\n"
    )
    env_file.write_text(env_content)
    print(f"Created .env with NEO4J_PASSWORD={password}")

    # Create secrets directory and auth file
    secrets_dir = project_root / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    auth_file = secrets_dir / "neo4j_auth_dev"
    auth_file.write_text(f"neo4j/{password}\n")
    print("Created secrets/neo4j_auth_dev")

    # Install files
    cmd_install(argparse.Namespace(force=False))

    # Setup DB (auth file already exists, will be skipped)
    cmd_setup_db(argparse.Namespace())

    # Check installation
    cmd_check(argparse.Namespace())


def cmd_uninstall(args: argparse.Namespace) -> None:
    project_root = Path.cwd()
    claude_dir = project_root / ".claude"

    files_to_remove = [
        claude_dir / "commands" / "bp.md",
        claude_dir / "commands" / "bpr.md",
        claude_dir / "agents" / "bp-synthesizer.md",
        claude_dir / "agents" / "bp-gap-handler.md",
    ]

    # Collect reference files
    refs_dir = claude_dir / "skills" / "best-practices-rag" / "references"
    if refs_dir.exists():
        files_to_remove.extend(refs_dir.glob("*.md"))

    for f in files_to_remove:
        if f.exists():
            f.unlink()
            print(f"  removed: {f}")
        else:
            print(f"  skip (missing): {f}")

    # Clean up empty dirs
    for d in [
        claude_dir / "skills" / "best-practices-rag" / "references",
        claude_dir / "skills" / "best-practices-rag",
        claude_dir / "skills",
    ]:
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
            print(f"  removed dir: {d}")

    if args.all:
        for f_name in ["docker-compose.yml", ".env", ".env.example"]:
            f = project_root / f_name
            if f.exists():
                f.unlink()
                print(f"  removed: {f}")

    print("\nUninstall complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="best-practices-rag",
        description="Manage best-practices-rag Claude Code skill",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    install_parser = subparsers.add_parser(
        "install", help="Copy agents, commands, and references to .claude/"
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    install_parser.set_defaults(func=cmd_install)

    # setup-db
    setup_parser = subparsers.add_parser(
        "setup-db", help="Start Neo4j via Docker and apply schema"
    )
    setup_parser.set_defaults(func=cmd_setup_db)

    # setup-schema
    schema_parser = subparsers.add_parser(
        "setup-schema",
        help="Apply schema to an existing Neo4j instance (no Docker required)",
    )
    schema_parser.set_defaults(func=cmd_setup_schema)

    # check
    check_parser = subparsers.add_parser("check", help="Validate installation")
    check_parser.set_defaults(func=cmd_check)

    # query-kb
    qk_parser = subparsers.add_parser(
        "query-kb", help="Query Neo4j knowledge base for best practices"
    )
    qk_parser.add_argument(
        "--tech", required=True, help="Comma-separated technology names"
    )
    qk_parser.add_argument(
        "--topics", required=True, help="Comma-separated topic keywords"
    )
    qk_parser.add_argument(
        "--languages", default=None, help="Comma-separated language names (optional)"
    )
    qk_parser.add_argument(
        "--include-bodies",
        action="store_true",
        default=False,
        help="Include body fields for all non-stale results (not just stale ones)",
    )
    qk_parser.set_defaults(func=cmd_query_kb)

    # search-exa
    se_parser = subparsers.add_parser(
        "search-exa", help="Search Exa for best practices"
    )
    se_parser.add_argument("--query", required=True, help="Search query string")
    se_parser.add_argument(
        "--exclude-domains",
        default=None,
        help="Comma-separated domains to exclude (optional)",
    )
    se_parser.add_argument(
        "--cutoff-date",
        default=None,
        help="ISO date string for start_published_date filter (optional)",
    )
    se_parser.add_argument(
        "--num-results",
        type=int,
        default=10,
        help="Number of Exa results to request (default: 10)",
    )
    se_parser.add_argument(
        "--top-n", type=int, default=5, help="Number of top results (default: 5)"
    )
    se_parser.add_argument(
        "--category",
        default=None,
        help="Exa category filter (e.g. 'github', 'blog', 'paper') (optional)",
    )
    se_parser.set_defaults(func=cmd_search_exa)

    # store-result
    sr_parser = subparsers.add_parser(
        "store-result", help="Store synthesized best practice into Neo4j"
    )
    sr_parser.add_argument(
        "--tech", required=True, help="Comma-separated technology names"
    )
    sr_parser.add_argument("--query", required=True, help="Original query string")
    sr_parser.add_argument(
        "--content-file",
        required=True,
        help="Path to file containing synthesized markdown content",
    )
    sr_parser.add_argument(
        "--source-urls", default=None, help="Comma-separated source URLs (optional)"
    )
    sr_parser.add_argument(
        "--languages", default=None, help="Comma-separated language names (optional)"
    )
    sr_parser.add_argument(
        "--tech-versions",
        default=None,
        help="JSON string of {tech: version} at synthesis time (optional)",
    )
    sr_parser.add_argument(
        "--source-tiers",
        default=None,
        help="JSON string of {url: tier} mapping source URLs to quality tiers (optional)",
    )
    sr_parser.set_defaults(func=cmd_store_result)

    # init
    init_parser = subparsers.add_parser(
        "init",
        help="One-command setup: create .env, install files, start Neo4j, check",
    )
    init_parser.add_argument(
        "--password",
        default=None,
        help="Neo4j password (auto-generated if not provided)",
    )
    init_parser.set_defaults(func=cmd_init)

    # uninstall
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Remove installed .claude/ files"
    )
    uninstall_parser.add_argument(
        "--all",
        action="store_true",
        help="Also remove docker-compose.yml, .env, and .env.example",
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
