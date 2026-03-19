"""CLI entry points for best-practices-rag."""

import json
import logging
import secrets
import shutil
import subprocess
import sys
import time
from importlib.resources import files
from pathlib import Path

import typer
from neo4j import GraphDatabase

from best_practices_rag import __version__
from best_practices_rag.config import get_settings
from best_practices_rag.graph_store import GraphStore
from best_practices_rag.knowledge_base import (
    query_knowledge_base,
    summarize_neo4j_results,
)
from best_practices_rag.logging_setup import configure_skill_logging
from best_practices_rag.parser import build_synthesized_bundle
from best_practices_rag.search import search_best_practices
from best_practices_rag.setup_schema import main as setup_main
from best_practices_rag.staleness import check_staleness, load_current_versions
from best_practices_rag.storage import store_results


app = typer.Typer(
    name="best-practices-rag",
    help="Manage best-practices-rag Claude Code skill.",
    no_args_is_help=True,
    add_completion=False,
)


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


def _bundle_claude_files(bundle: Path) -> set[str]:
    result: set[str] = set()
    for prefix, src in [
        ("commands", bundle / "commands"),
        ("agents", bundle / "agents"),
        ("skills/best-practices-rag", bundle / "skills" / "best-practices-rag"),
    ]:
        if src.exists():
            for item in src.rglob("*"):
                if item.is_file():
                    result.add(f"{prefix}/{item.relative_to(src)}")
    return result


def _read_manifest(config_dir: Path) -> list[str]:
    path = config_dir / "manifest.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("files", [])
    except Exception:
        return []


def _write_manifest(config_dir: Path, files: set[str]) -> None:
    (config_dir / "manifest.json").write_text(
        json.dumps({"version": __version__, "files": sorted(files)}, indent=2)
    )


def _remove_stale_claude_files(
    claude_dir: Path, config_dir: Path, new_files: set[str]
) -> None:
    stale = [f for f in _read_manifest(config_dir) if f not in new_files]
    for rel in stale:
        target = claude_dir / rel
        if target.exists():
            target.unlink()
            print(f"  removed (stale): {target}")


def _setup_docker_neo4j(config_dir: Path) -> None:
    for cmd in ["docker", "docker compose"]:
        binary = cmd.split()[0]
        if shutil.which(binary) is None:
            print(f"Error: '{binary}' not found. Docker is required for Neo4j.")
            sys.exit(1)

    bundle = _bundle_root()

    compose_file = config_dir / "docker-compose.yml"
    if not compose_file.exists():
        shutil.copy2(bundle / "infra" / "docker-compose.yml", compose_file)
        print("Copied docker-compose.yml")

    secrets_dir = config_dir / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    auth_file = secrets_dir / "neo4j_auth_dev"
    if not auth_file.exists():
        password = "changeme"
        env_file = config_dir / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("NEO4J_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
                    break
        auth_file.write_text(f"neo4j/{password}\n")
        print(f"Created secrets/neo4j_auth_dev (password: {password})")
        if password == "changeme":
            print("  Change this before production use!")

    print("\nStarting Neo4j via Docker...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        capture_output=True,
        text=True,
        cwd=str(config_dir),
    )
    if result.returncode != 0:
        print(f"Error starting Neo4j:\n{result.stderr}")
        sys.exit(1)
    print(result.stdout)

    print("Waiting for Neo4j to be ready...")
    timeout = 120
    interval = 5
    elapsed = 0
    while elapsed < timeout:
        ps = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=str(config_dir),
        )
        if "healthy" in ps.stdout.lower():
            print("Neo4j is ready.")
            break
        time.sleep(interval)
        elapsed += interval
        print(f"  waiting... ({elapsed}s / {timeout}s)")
    else:
        print(f"Warning: Neo4j did not become healthy within {timeout}s.")
        print("It may still be starting. Check with: docker compose ps")

    print("\nApplying database schema...")
    try:
        setup_main()
        print("Schema applied successfully.")
    except Exception as e:
        print(f"Schema setup failed: {e}")
        print("You can retry later with: best-practices-rag setup-schema")
        sys.exit(1)


@app.command()
def setup(
    force: bool = typer.Option(False, help="Overwrite existing files"),
    password: str | None = typer.Option(
        None, help="Neo4j password (auto-generated if omitted)"
    ),
    neo4j_uri: str | None = typer.Option(
        None, help="Skip Docker, connect to an existing Neo4j instance"
    ),
    neo4j_username: str | None = typer.Option(
        None, help="Neo4j username (default: neo4j)"
    ),
) -> None:
    """Install best-practices-rag globally.

    Copies skill files to ~/.claude/, writes credentials to
    ~/.config/best-practices-rag/.env, and starts Neo4j via Docker
    (unless --neo4j-uri is provided).

    \b
    Standalone (Docker):
        best-practices-rag setup
        best-practices-rag setup --password mysecretpassword

    Existing Neo4j:
        best-practices-rag setup --neo4j-uri bolt://host:7687
    """
    config_dir = Path.home() / ".config" / "best-practices-rag"
    config_dir.mkdir(parents=True, exist_ok=True)
    claude_dir = Path.home() / ".claude"

    print("Installing best-practices-rag globally...\n")

    bundle = _bundle_root()
    new_files = _bundle_claude_files(bundle)
    _remove_stale_claude_files(claude_dir, config_dir, new_files)
    _copy_tree(bundle / "commands", claude_dir / "commands", force=force)
    _copy_tree(bundle / "agents", claude_dir / "agents", force=force)
    _copy_tree(
        bundle / "skills" / "best-practices-rag",
        claude_dir / "skills" / "best-practices-rag",
        force=force,
    )
    _write_manifest(config_dir, new_files)

    env_example = config_dir / ".env.example"
    if not env_example.exists() or force:
        shutil.copy2(bundle / "infra" / ".env.example", env_example)
        print(f"  copied: {env_example}")

    env_file = config_dir / ".env"
    if not env_file.exists() or force:
        pwd = password or secrets.token_urlsafe(16)
        uri = neo4j_uri or "bolt://localhost:7687"
        username = neo4j_username or "neo4j"
        env_file.write_text(
            f"NEO4J_URI={uri}\n"
            f"NEO4J_USERNAME={username}\n"
            f"NEO4J_PASSWORD={pwd}\n"
            "\n"
            "# Optional — Exa API for web search (enables /bp gap-fill)\n"
            "# EXA_API_KEY=your-exa-api-key-here\n"
        )
        print(f"  wrote: {env_file}")

    if neo4j_uri:
        print("\nApplying schema to existing Neo4j...")
        try:
            setup_main()
            print("Schema applied successfully.")
        except Exception as e:
            print(f"Schema setup failed: {e}")
            sys.exit(1)
    else:
        _setup_docker_neo4j(config_dir)

    print("\nSetup complete. Run 'best-practices-rag check' to validate.")


@app.command()
def setup_schema() -> None:
    """Apply schema to an existing Neo4j instance.

    No Docker required. Reads connection details from
    ~/.config/best-practices-rag/.env (or a CWD .env override).
    Use this if schema setup failed during 'best-practices-rag setup',
    or after a Neo4j upgrade.
    """
    print("Applying database schema...")
    try:
        setup_main()
        print("Schema applied successfully.")
    except Exception as e:
        print(f"Schema setup failed: {e}")
        sys.exit(1)


@app.command()
def check() -> None:
    """Validate the global installation.

    Checks that required files exist in ~/.claude/, that Neo4j is
    reachable with the configured credentials, and reports Exa API key
    status (optional — needed for /bp gap-fill).
    """
    claude_dir = Path.home() / ".claude"
    all_ok = True

    print("Checking best-practices-rag installation...\n")

    expected_files = [
        "commands/bp.md",
        "commands/bpr.md",
        "agents/bp-pipeline.md",
        "skills/best-practices-rag/references/synthesis-format.md",
        "skills/best-practices-rag/references/synthesis-format-codegen.md",
        "skills/best-practices-rag/references/synthesis-format-research.md",
        "skills/best-practices-rag/references/tech-versions.md",
    ]
    for f in expected_files:
        path = claude_dir / f
        if path.exists():
            print(f"  [pass] ~/.claude/{f}")
        else:
            print(f"  [FAIL] ~/.claude/{f} — missing")
            all_ok = False

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


@app.command()
def query_kb(
    tech: str = typer.Option(..., help="Comma-separated technology names"),
    topics: str = typer.Option(..., help="Comma-separated topic keywords"),
    languages: str | None = typer.Option(
        None, help="Comma-separated language names (optional)"
    ),
    include_bodies: bool = typer.Option(
        False, help="Include body fields for all non-stale results"
    ),
) -> None:
    """Query the Neo4j knowledge base for best practices.

    Used internally by the /bp and /bpr Claude Code skill commands.
    Returns JSON to stdout.

    \b
    Example:
        best-practices-rag query-kb --tech fastapi,sqlalchemy --topics async,sessions
    """
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "query_kb invoked — tech=%r topics=%r languages=%r include_bodies=%r",
        tech,
        topics,
        languages,
        include_bodies,
    )

    tech_names = [t.strip() for t in tech.split(",") if t.strip()]
    topic_keywords = [t.strip().lower() for t in topics.split(",") if t.strip()]
    lang_names = (
        [lang.strip() for lang in languages.split(",") if lang.strip()]
        if languages
        else None
    )

    settings = get_settings()
    graph_store = GraphStore(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password.get_secret_value(),
    )

    current_versions = load_current_versions(
        Path.home() / ".claude" / "skills" / "best-practices-rag" / "references"
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

    if include_bodies:
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


@app.command()
def search_exa(
    query: str = typer.Option(..., help="Search query string"),
    exclude_domains: str | None = typer.Option(
        None, help="Comma-separated domains to exclude (optional)"
    ),
    cutoff_date: str | None = typer.Option(
        None, help="ISO date string for start_published_date filter (optional)"
    ),
    num_results: int = typer.Option(10, help="Number of Exa results to request"),
    top_n: int = typer.Option(5, help="Number of top results to return"),
    category: str | None = typer.Option(
        None, help="Exa category filter (e.g. github, blog, paper)"
    ),
) -> None:
    """Search Exa for best practices content.

    Used internally by the bp-pipeline agent when the knowledge base has
    a gap. Returns JSON to stdout.

    \b
    Example:
        best-practices-rag search-exa --query "FastAPI async session management"
    """
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "search_exa invoked — query=%r exclude_domains=%r cutoff_date=%r num_results=%d top_n=%d category=%r",
        query,
        exclude_domains,
        cutoff_date,
        num_results,
        top_n,
        category,
    )

    domains = (
        [d.strip() for d in exclude_domains.split(",") if d.strip()]
        if exclude_domains
        else None
    )

    results = search_best_practices(
        query=query,
        num_results=num_results,
        exclude_domains=domains,
        start_published_date=cutoff_date,
        category=category,
    )

    log.debug(
        "search_exa complete — %d total results, returning top %d",
        len(results),
        top_n,
    )
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
            for r in results[:top_n]
        ],
    }
    print(json.dumps(output))


@app.command()
def store_result(
    tech: str = typer.Option(..., help="Comma-separated technology names"),
    query: str = typer.Option(..., help="Original query string"),
    content_file: str = typer.Option(
        ..., help="Path to file containing synthesized markdown content"
    ),
    source_urls: str | None = typer.Option(
        None, help="Comma-separated source URLs (optional)"
    ),
    languages: str | None = typer.Option(
        None, help="Comma-separated language names (optional)"
    ),
    tech_versions: str | None = typer.Option(
        None, help="JSON string of {tech: version} at synthesis time (optional)"
    ),
    source_tiers: str | None = typer.Option(
        None,
        help="JSON string of {url: tier} mapping source URLs to quality tiers (optional)",
    ),
) -> None:
    """Store a synthesized best-practices document into Neo4j.

    Used internally by the bp-pipeline agent after synthesis. Content is
    read from a file to avoid shell escaping issues with large documents.

    \b
    Example:
        best-practices-rag store-result --tech fastapi --query "async sessions" \\
            --content-file .best-practices/fastapi-async-codegen.md
    """
    configure_skill_logging()
    log = logging.getLogger(__name__)
    log.debug(
        "store_result invoked — tech=%r query=%r content_file=%r source_urls=%r languages=%r tech_versions=%r source_tiers=%r",
        tech,
        query,
        content_file,
        source_urls,
        languages,
        tech_versions,
        source_tiers,
    )

    tech_names = [t.strip() for t in tech.split(",") if t.strip()]
    urls = (
        [u.strip() for u in source_urls.split(",") if u.strip()] if source_urls else []
    )
    lang_names = (
        [lang.strip() for lang in languages.split(",") if lang.strip()]
        if languages
        else None
    )
    versions = json.loads(tech_versions) if tech_versions else None
    tiers = json.loads(source_tiers) if source_tiers else None

    content_path = Path(content_file)
    synthesized_content = content_path.read_text(encoding="utf-8")

    bundle = build_synthesized_bundle(
        synthesized_content=synthesized_content,
        tech_names=tech_names,
        source_urls=urls,
        query=query,
        lang_names=lang_names,
        tech_versions=versions,
        source_tiers=tiers,
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


@app.command()
def uninstall(
    remove_all: bool = typer.Option(
        False, "--all", help="Also remove ~/.config/best-practices-rag/"
    ),
) -> None:
    """Remove installed ~/.claude/ files.

    By default only removes the skill files from ~/.claude/. Use --all
    to also delete credentials and Docker data in
    ~/.config/best-practices-rag/.

    \b
    Remove ~/.claude/ files only:
        best-practices-rag uninstall

    Also remove credentials and Docker data:
        best-practices-rag uninstall --all
    """
    claude_dir = Path.home() / ".claude"

    files_to_remove = [
        claude_dir / "commands" / "bp.md",
        claude_dir / "commands" / "bpr.md",
        claude_dir / "agents" / "bp-pipeline.md",
    ]

    refs_dir = claude_dir / "skills" / "best-practices-rag" / "references"
    if refs_dir.exists():
        files_to_remove.extend(refs_dir.glob("*.md"))

    for f in files_to_remove:
        if f.exists():
            f.unlink()
            print(f"  removed: {f}")
        else:
            print(f"  skip (missing): {f}")

    for d in [
        claude_dir / "skills" / "best-practices-rag" / "references",
        claude_dir / "skills" / "best-practices-rag",
        claude_dir / "skills",
    ]:
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
            print(f"  removed dir: {d}")

    if remove_all:
        config_dir = Path.home() / ".config" / "best-practices-rag"
        if config_dir.exists():
            shutil.rmtree(config_dir)
            print(f"  removed dir: {config_dir}")

    print("\nUninstall complete.")


@app.command()
def version() -> None:
    """Show the installed version.

    Reads the version from the installed package metadata.
    """
    print(f"best-practices-rag v{__version__}")


@app.command()
def update() -> None:
    """Upgrade best-practices-rag to the latest release.

    Detects whether the tool was installed via uv or pipx and runs
    the appropriate upgrade command automatically.

    \b
    Manual upgrade:
        uv tool upgrade best-practices-rag
        pipx upgrade best-practices-rag
    """
    for manager, cmd in [
        ("uv", ["uv", "tool", "upgrade", "best-practices-rag"]),
        ("pipx", ["pipx", "upgrade", "best-practices-rag"]),
    ]:
        if shutil.which(manager):
            print(f"Upgrading via {manager}...")
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"{manager} upgrade failed.", file=sys.stderr)
                sys.exit(1)
            print("\nUpdating ~/.claude/ skill files...")
            config_dir = Path.home() / ".config" / "best-practices-rag"
            claude_dir = Path.home() / ".claude"
            bundle = _bundle_root()
            new_files = _bundle_claude_files(bundle)
            _remove_stale_claude_files(claude_dir, config_dir, new_files)
            _copy_tree(bundle / "commands", claude_dir / "commands", force=True)
            _copy_tree(bundle / "agents", claude_dir / "agents", force=True)
            _copy_tree(
                bundle / "skills" / "best-practices-rag",
                claude_dir / "skills" / "best-practices-rag",
                force=True,
            )
            _write_manifest(config_dir, new_files)
            return

    print("Error: neither uv nor pipx found.", file=sys.stderr)
    print("Run one of:", file=sys.stderr)
    print("  uv tool upgrade best-practices-rag", file=sys.stderr)
    print("  pipx upgrade best-practices-rag", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
