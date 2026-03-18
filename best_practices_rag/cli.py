"""CLI entry points for best-practices-rag.

Subcommands:
    install   — copy agents, commands, scripts, and references to .claude/
    setup-db  — start Neo4j via Docker and apply schema
    check     — validate installation
"""

import argparse
import shutil
import subprocess
import sys
import time
from importlib.resources import files
from pathlib import Path


def _bundle_root() -> Path:
    return Path(str(files("best_practices_rag") / "_claude_files"))


def _copy_tree(src: Path, dst: Path, *, force: bool) -> list[str]:
    """Recursively copy files from src to dst. Returns list of copied paths."""
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
    print("  1. uv run best-practices-rag setup-db")
    print("  2. Copy .env.example to .env and set NEO4J_PASSWORD")
    print("  3. Optionally set EXA_API_KEY in .env for web search")
    print("  4. Use /bp <technologies> to query best practices")


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
        auth_file.write_text("neo4j/changeme\n")
        print("Created secrets/neo4j_auth_dev (default password: changeme)")
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
        from best_practices_rag.setup_schema import main as setup_main

        setup_main()
        print("Schema applied successfully.")
    except Exception as e:
        print(f"Schema setup failed: {e}")
        print("You can retry later with: uv run python -m best_practices_rag.setup_schema")
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
        "skills/best-practices-rag/scripts/query_kb.py",
        "skills/best-practices-rag/scripts/search_exa.py",
        "skills/best-practices-rag/scripts/store_result.py",
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
        from best_practices_rag.config import get_settings

        settings = get_settings()
        from neo4j import GraphDatabase

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
        from best_practices_rag.config import get_settings

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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="best-practices-rag",
        description="Manage best-practices-rag Claude Code skill",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install
    install_parser = subparsers.add_parser(
        "install", help="Copy agents, commands, scripts, and references to .claude/"
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

    # check
    check_parser = subparsers.add_parser(
        "check", help="Validate installation"
    )
    check_parser.set_defaults(func=cmd_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
