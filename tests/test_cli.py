import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from best_practices_rag.cli import check
from best_practices_rag.cli import main
from best_practices_rag.cli import query_kb
from best_practices_rag.cli import setup
from best_practices_rag.cli import setup_schema
from best_practices_rag.cli import update
from best_practices_rag.cli import version


def test_setup_schema_success(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_setup = mocker.patch("best_practices_rag.cli.setup_main")

    setup_schema()

    mock_setup.assert_called_once()
    out = capsys.readouterr().out
    assert "Applying database schema" in out
    assert "Schema applied successfully" in out


def test_setup_schema_failure_exits(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch(
        "best_practices_rag.cli.setup_main",
        side_effect=RuntimeError("connection refused"),
    )

    with pytest.raises(SystemExit) as exc_info:
        setup_schema()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Schema setup failed" in out
    assert "connection refused" in out


def test_setup_schema_registered_as_subcommand() -> None:
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["best-practices-rag", "setup-schema", "--help"]
        main()

    assert exc_info.value.code == 0


def test_setup_standalone_creates_global_files(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch(
        "best_practices_rag.cli._bundle_root", return_value=tmp_path / "bundle"
    )
    mocker.patch("best_practices_rag.cli._copy_tree", return_value=[])
    mocker.patch("best_practices_rag.cli._setup_docker_neo4j")

    bundle = tmp_path / "bundle"
    (bundle / "infra").mkdir(parents=True)
    (bundle / "infra" / ".env.example").write_text("# example\n")

    setup(force=False, password=None, neo4j_uri=None, neo4j_username=None)

    config_dir = tmp_path / ".config" / "best-practices-rag"
    assert (config_dir / ".env").exists()
    env_content = (config_dir / ".env").read_text()
    assert "NEO4J_URI=" in env_content
    assert "NEO4J_PASSWORD=" in env_content


def test_setup_existing_neo4j_skips_docker(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch(
        "best_practices_rag.cli._bundle_root", return_value=tmp_path / "bundle"
    )
    mocker.patch("best_practices_rag.cli._copy_tree", return_value=[])
    mock_setup_main = mocker.patch("best_practices_rag.cli.setup_main")
    mock_docker = mocker.patch("best_practices_rag.cli._setup_docker_neo4j")

    bundle = tmp_path / "bundle"
    (bundle / "infra").mkdir(parents=True)
    (bundle / "infra" / ".env.example").write_text("# example\n")

    setup(
        force=False,
        password=None,
        neo4j_uri="bolt://myserver:7687",
        neo4j_username="neo4j",
    )

    mock_setup_main.assert_called_once()
    mock_docker.assert_not_called()


def test_setup_force_overwrites(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch(
        "best_practices_rag.cli._bundle_root", return_value=tmp_path / "bundle"
    )
    mocker.patch("best_practices_rag.cli._copy_tree", return_value=[])
    mocker.patch("best_practices_rag.cli._setup_docker_neo4j")

    bundle = tmp_path / "bundle"
    (bundle / "infra").mkdir(parents=True)
    (bundle / "infra" / ".env.example").write_text("# example\n")

    config_dir = tmp_path / ".config" / "best-practices-rag"
    config_dir.mkdir(parents=True)
    existing_env = config_dir / ".env"
    existing_env.write_text("NEO4J_PASSWORD=old\n")

    setup(force=True, password="newpass", neo4j_uri=None, neo4j_username=None)

    assert "newpass" in existing_env.read_text()


def test_cmd_check_validates_global_claude_dir(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch("pathlib.Path.home", return_value=tmp_path)

    claude_dir = tmp_path / ".claude"
    for f in [
        "commands/bp.md",
        "commands/bpr.md",
        "agents/bp-pipeline.md",
        "skills/best-practices-rag/references/synthesis-format.md",
        "skills/best-practices-rag/references/synthesis-format-codegen.md",
        "skills/best-practices-rag/references/synthesis-format-research.md",
        "skills/best-practices-rag/references/tech-versions.md",
    ]:
        p = claude_dir / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")

    mock_settings = mocker.MagicMock()
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.neo4j_username = "neo4j"
    mock_settings.neo4j_password.get_secret_value.return_value = "test"
    mock_settings.exa_api_key.get_secret_value.return_value = ""
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)
    mock_driver_instance = mocker.MagicMock()
    mocker.patch(
        "best_practices_rag.cli.GraphDatabase.driver", return_value=mock_driver_instance
    )

    check()

    out = capsys.readouterr().out
    assert "~/.claude/" in out
    file_check_section = out.split("Neo4j")[0]
    assert "[FAIL]" not in file_check_section


def test_version_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    version()

    out = capsys.readouterr().out
    assert "best-practices-rag v" in out


def test_update_uses_uv(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch(
        "best_practices_rag.cli.shutil.which",
        side_effect=lambda x: "/usr/bin/uv" if x == "uv" else None,
    )
    mock_run = mocker.patch(
        "best_practices_rag.cli.subprocess.run",
        return_value=mocker.MagicMock(returncode=0),
    )

    update()

    assert mock_run.call_args[0][0] == ["uv", "tool", "upgrade", "best-practices-rag"]


def test_update_falls_back_to_pipx(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch(
        "best_practices_rag.cli.shutil.which",
        side_effect=lambda x: None if x == "uv" else "/usr/bin/pipx",
    )
    mock_run = mocker.patch(
        "best_practices_rag.cli.subprocess.run",
        return_value=mocker.MagicMock(returncode=0),
    )

    update()

    assert mock_run.call_args[0][0] == [
        "pipx",
        "upgrade",
        "best-practices-rag",
    ]


def test_update_exits_if_no_manager(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.shutil.which", return_value=None)

    with pytest.raises(SystemExit) as exc_info:
        update()

    assert exc_info.value.code == 1


def test_query_kb_format_md_outputs_markdown(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.configure_skill_logging")
    mock_settings = mocker.MagicMock()
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.neo4j_username = "neo4j"
    mock_settings.neo4j_password.get_secret_value.return_value = "test"
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)
    mocker.patch("best_practices_rag.cli.GraphStore")
    mocker.patch("best_practices_rag.cli.load_current_versions", return_value={})

    fresh_result = {
        "name": "fastapi-async",
        "title": "FastAPI Async Patterns",
        "display_name": "FastAPI",
        "version": "0.116",
        "synthesized_at": "2026-03-15T10:00:00Z",
        "body": "# FastAPI Async Best Practices\n\nUse async endpoints.",
    }
    stale_result = {
        "name": "sqlalchemy-sessions",
        "title": "SQLAlchemy Session Management",
        "display_name": "SQLAlchemy",
        "version": "2.0",
        "synthesized_at": "2026-01-10T08:00:00Z",
        "body": "# SQLAlchemy Sessions\n\nUse scoped sessions.",
    }
    mocker.patch(
        "best_practices_rag.cli.query_knowledge_base",
        return_value=[fresh_result, stale_result],
    )
    mocker.patch(
        "best_practices_rag.cli.check_staleness",
        side_effect=[
            {
                "is_stale": False,
                "reason": "current",
                "stale_technologies": [],
                "fresh_technologies": ["fastapi"],
                "version_deltas": {},
                "document_age_days": 5,
            },
            {
                "is_stale": True,
                "reason": "version_mismatch",
                "stale_technologies": ["sqlalchemy"],
                "fresh_technologies": [],
                "version_deltas": {"sqlalchemy": {"stored": "2.0", "current": "2.1"}},
                "document_age_days": 69,
            },
        ],
    )

    query_kb(
        tech="fastapi,sqlalchemy",
        topics="async,sessions",
        languages=None,
        include_bodies=False,
        output_format="md",
    )

    out = capsys.readouterr().out
    assert "# Knowledge Base Results (2 entries)" in out
    assert "=== ENTRY: fastapi-async | STATUS: fresh ===" in out
    assert "=== ENTRY: sqlalchemy-sessions | STATUS: stale ===" in out
    assert "- **Staleness Reason:** version_mismatch" in out
    assert "- **Stale Technologies:** sqlalchemy" in out
    assert "sqlalchemy: 2.0 → 2.1" in out
    assert "# FastAPI Async Best Practices" in out
    assert "# SQLAlchemy Sessions" in out
    assert not out.strip().startswith("{")
