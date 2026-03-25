import json
import sys
from pathlib import Path

import pytest
from neo4j.exceptions import AuthError, ServiceUnavailable
from pytest_mock import MockerFixture

from best_practices_rag.cli import _generate_slug
from best_practices_rag.cli import _resolve_exa_num_results
from best_practices_rag.cli import check
from best_practices_rag.cli import logs
from best_practices_rag.cli import main
from best_practices_rag.cli import query_kb
from best_practices_rag.cli import search_exa
from best_practices_rag.cli import setup
from best_practices_rag.cli import setup_schema
from best_practices_rag.cli import update
from best_practices_rag.cli import version
from best_practices_rag.search import ExaSearchError


class TestGenerateSlug:
    def test_sorts_and_dedupes(self) -> None:
        result = _generate_slug(
            ["fastapi", "sqlalchemy"], ["session management"], "codegen"
        )
        assert result == "fastapi-management-session-sqlalchemy-codegen"

    def test_tech_topic_boundary_irrelevant(self) -> None:
        as_tech = _generate_slug(["testing"], ["patterns"], "codegen")
        as_topic = _generate_slug(["patterns"], ["testing"], "codegen")
        assert as_tech == as_topic

    def test_multiword_topic_split(self) -> None:
        one_phrase = _generate_slug(["fastapi"], ["session management"], "codegen")
        two_words = _generate_slug(["fastapi"], ["session", "management"], "codegen")
        assert one_phrase == two_words

    def test_truncation_at_word_boundary(self) -> None:
        result = _generate_slug(
            [
                "alpha",
                "bravo",
                "charlie",
                "delta",
                "echo",
                "foxtrot",
                "golf",
                "hotel",
                "india",
            ],
            ["juliet", "kilo"],
            "codegen",
        )
        assert result.endswith("-codegen")
        slug_body = result.removesuffix("-codegen")
        assert len(slug_body) <= 60

    def test_research_mode_suffix(self) -> None:
        result = _generate_slug(["fastapi"], ["async"], mode="research")
        assert result == "async-fastapi-research"


def test_setup_schema_success(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_setup = mocker.patch("best_practices_rag.cli.run_migrations")

    setup_schema()

    mock_setup.assert_called_once()
    out = capsys.readouterr().out
    assert "Applying database schema" in out
    assert "Schema applied successfully" in out


def test_setup_schema_failure_exits(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch(
        "best_practices_rag.cli.run_migrations",
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

    setup(
        force=False,
        password=None,
        neo4j_uri=None,
        neo4j_username=None,
        exa_api_key=None,
        neo4j_port=None,
    )

    config_dir = tmp_path / ".config" / "best-practices-rag"
    assert (config_dir / ".env").exists()
    env_content = (config_dir / ".env").read_text()
    assert "NEO4J_URI=" in env_content
    assert "NEO4J_PASSWORD" not in env_content

    assert (config_dir / "secrets" / "neo4j_password").exists()


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
    mock_setup_main = mocker.patch("best_practices_rag.cli.run_migrations")
    mock_docker = mocker.patch("best_practices_rag.cli._setup_docker_neo4j")

    bundle = tmp_path / "bundle"
    (bundle / "infra").mkdir(parents=True)
    (bundle / "infra" / ".env.example").write_text("# example\n")

    setup(
        force=False,
        password=None,
        neo4j_uri="bolt://myserver:7687",
        neo4j_username="neo4j",
        exa_api_key=None,
        neo4j_port=None,
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
    existing_env.write_text("NEO4J_URI=bolt://localhost:7687\n")

    secrets_dir = config_dir / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    (secrets_dir / "neo4j_password").write_text("oldpass")

    setup(
        force=True,
        password="newpass",
        neo4j_uri=None,
        neo4j_username=None,
        exa_api_key=None,
        neo4j_port=None,
    )

    assert (secrets_dir / "neo4j_password").read_text() == "oldpass"


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
    mock_settings.exa_api_key.get_secret_value.return_value = "test-key"
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)
    mock_driver_instance = mocker.MagicMock()
    all_index_names = [
        "bp_fulltext",
        "constraint_best_practice_id",
        "constraint_technology_id",
        "constraint_pattern_id",
        "index_best_practice_name",
        "index_best_practice_category",
        "index_technology_name",
    ]
    mock_driver_instance.execute_query.return_value = (
        [{"names": all_index_names}],
        None,
        None,
    )
    mocker.patch(
        "best_practices_rag.cli.GraphDatabase.driver", return_value=mock_driver_instance
    )

    check()

    out = capsys.readouterr().out
    assert "~/.claude/" in out
    assert "[FAIL]" not in out
    assert "[pass] Exa API key configured" in out
    assert "[pass] Schema indexes" in out


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
    mock_schema = mocker.patch("best_practices_rag.cli._run_setup_schema")

    update()

    assert mock_run.call_args[0][0] == ["uv", "tool", "upgrade", "best-practices-rag"]
    mock_schema.assert_called_once()


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
    mock_schema = mocker.patch("best_practices_rag.cli._run_setup_schema")

    update()

    assert mock_run.call_args[0][0] == [
        "pipx",
        "upgrade",
        "best-practices-rag",
    ]
    mock_schema.assert_called_once()


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


def test_query_kb_auth_error_returns_json_and_exits(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.configure_skill_logging")
    mock_settings = mocker.MagicMock()
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.neo4j_username = "neo4j"
    mock_settings.neo4j_password.get_secret_value.return_value = "wrong"
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)
    mocker.patch(
        "best_practices_rag.cli.GraphStore",
        side_effect=AuthError("bad credentials"),
    )

    with pytest.raises(SystemExit) as exc_info:
        query_kb(
            tech="fastapi",
            topics="async",
            languages=None,
            include_bodies=False,
            output_format="json",
        )

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["count"] == 0
    assert result["results"] == []
    assert "neo4j_unavailable" in result["error"]


def test_query_kb_service_unavailable_returns_json_and_exits(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.configure_skill_logging")
    mock_settings = mocker.MagicMock()
    mock_settings.neo4j_uri = "bolt://localhost:7687"
    mock_settings.neo4j_username = "neo4j"
    mock_settings.neo4j_password.get_secret_value.return_value = "test"
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)
    mocker.patch(
        "best_practices_rag.cli.GraphStore",
        side_effect=ServiceUnavailable("connection refused"),
    )

    with pytest.raises(SystemExit) as exc_info:
        query_kb(
            tech="fastapi",
            topics="async",
            languages=None,
            include_bodies=False,
            output_format="json",
        )

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["count"] == 0
    assert "neo4j_unavailable" in result["error"]


def test_setup_with_exa_api_key(
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

    setup(
        force=False,
        password=None,
        neo4j_uri=None,
        neo4j_username=None,
        exa_api_key="test-exa-key-123",
        neo4j_port=None,
    )

    exa_file = tmp_path / ".config" / "best-practices-rag" / "secrets" / "exa_api_key"
    assert exa_file.exists()
    assert exa_file.read_text() == "test-exa-key-123"


def test_setup_with_neo4j_port(
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch(
        "best_practices_rag.cli._bundle_root", return_value=tmp_path / "bundle"
    )
    mocker.patch("best_practices_rag.cli._copy_tree", return_value=[])
    mock_docker = mocker.patch("best_practices_rag.cli._setup_docker_neo4j")

    bundle = tmp_path / "bundle"
    (bundle / "infra").mkdir(parents=True)
    (bundle / "infra" / ".env.example").write_text("# example\n")

    setup(
        force=False,
        password=None,
        neo4j_uri=None,
        neo4j_username=None,
        exa_api_key=None,
        neo4j_port=7688,
    )

    env_content = (tmp_path / ".config" / "best-practices-rag" / ".env").read_text()
    assert "bolt://localhost:7688" in env_content
    mock_docker.assert_called_once()
    call_kwargs = mock_docker.call_args
    assert call_kwargs[1]["port"] == 7688


def test_setup_without_exa_key_prints_instructions(
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

    setup(
        force=False,
        password=None,
        neo4j_uri=None,
        neo4j_username=None,
        exa_api_key=None,
        neo4j_port=None,
    )

    out = capsys.readouterr().out
    assert "[action required]" in out
    assert "exa_api_key" in out


def test_resolve_exa_num_results_returns_explicit_value() -> None:
    assert _resolve_exa_num_results(7) == 7


def test_resolve_exa_num_results_reads_settings_when_none(
    mocker: MockerFixture,
) -> None:
    mock_settings = mocker.MagicMock()
    mock_settings.exa_num_results = 3
    mocker.patch("best_practices_rag.cli.get_settings", return_value=mock_settings)

    assert _resolve_exa_num_results(None) == 3


def test_search_exa_error_outputs_json_and_exits(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.configure_skill_logging")
    mocker.patch(
        "best_practices_rag.cli.search_best_practices",
        side_effect=ExaSearchError("Exa search failed — rate limited (429)"),
    )

    with pytest.raises(SystemExit) as exc_info:
        search_exa(
            query="FastAPI async patterns",
            exclude_domains=None,
            cutoff_date=None,
            num_results=5,
            top_n=5,
            category=None,
            output_file=None,
        )

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["count"] == 0
    assert parsed["results"] == []
    assert "rate limited" in parsed["error"]


def test_search_exa_error_writes_empty_file_when_output_file_given(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch("best_practices_rag.cli.configure_skill_logging")
    mocker.patch(
        "best_practices_rag.cli.search_best_practices",
        side_effect=ExaSearchError("Exa search failed"),
    )
    output_file = str(tmp_path / "out.md")

    with pytest.raises(SystemExit) as exc_info:
        search_exa(
            query="test query",
            exclude_domains=None,
            cutoff_date=None,
            num_results=5,
            top_n=5,
            category=None,
            output_file=output_file,
        )

    assert exc_info.value.code == 0
    assert Path(output_file).exists()
    assert Path(output_file).read_text() == ""
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["output_file"] == output_file


def test_logs_command_exits_when_no_log_file(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch(
        "best_practices_rag.cli._resolve_log_path",
        return_value=tmp_path / "nonexistent" / "skill.log",
    )

    with pytest.raises(SystemExit) as exc_info:
        logs(lines=50, follow=False)

    assert exc_info.value.code == 1


def test_logs_command_calls_tail(mocker: MockerFixture, tmp_path: Path) -> None:
    log_file = tmp_path / "skill.log"
    log_file.write_text("log entry\n")
    mocker.patch(
        "best_practices_rag.cli._resolve_log_path",
        return_value=log_file,
    )
    mock_run = mocker.patch("best_practices_rag.cli.subprocess.run")

    logs(lines=20, follow=False)

    mock_run.assert_called_once_with(["tail", "-20", str(log_file)])


def test_logs_command_follow_calls_tail_f(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    log_file = tmp_path / "skill.log"
    log_file.write_text("log entry\n")
    mocker.patch(
        "best_practices_rag.cli._resolve_log_path",
        return_value=log_file,
    )
    mock_run = mocker.patch("best_practices_rag.cli.subprocess.run")

    logs(lines=50, follow=True)

    mock_run.assert_called_once_with(["tail", "-f", str(log_file)])
