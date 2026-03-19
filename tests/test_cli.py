import argparse
import sys

import pytest
from pytest_mock import MockerFixture


def test_setup_schema_success(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    mock_setup = mocker.patch("best_practices_rag.cli.setup_main")

    from best_practices_rag.cli import cmd_setup_schema

    cmd_setup_schema(argparse.Namespace())

    mock_setup.assert_called_once()
    out = capsys.readouterr().out
    assert "Applying database schema" in out
    assert "Schema applied successfully" in out


def test_setup_schema_failure_exits(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    mocker.patch("best_practices_rag.cli.setup_main", side_effect=RuntimeError("connection refused"))

    from best_practices_rag.cli import cmd_setup_schema

    with pytest.raises(SystemExit) as exc_info:
        cmd_setup_schema(argparse.Namespace())

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Schema setup failed" in out
    assert "connection refused" in out


def test_setup_schema_registered_as_subcommand() -> None:
    from best_practices_rag.cli import main
    import argparse

    # Parse --help equivalent by checking subcommands are registered
    # We do this by verifying the parser accepts setup-schema
    from best_practices_rag import cli
    import importlib

    # Build the parser by calling parse_args with --help would sys.exit,
    # so instead we verify via direct subparser inspection
    parser = argparse.ArgumentParser(prog="best-practices-rag")
    subparsers = parser.add_subparsers(dest="command")

    # Confirm setup-schema is wired in real main by running it with --help
    # and catching the SystemExit(0)
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["best-practices-rag", "setup-schema", "--help"]
        main()

    assert exc_info.value.code == 0


def test_cmd_install_shows_both_paths(mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: pytest.TempPathFactory) -> None:
    mocker.patch("best_practices_rag.cli._bundle_root", return_value=tmp_path)
    mocker.patch("best_practices_rag.cli._copy_tree", return_value=[])

    # Stub out the infra file copies
    infra = tmp_path / "infra"
    infra.mkdir(parents=True)
    (infra / ".env.example").write_text("")

    mocker.patch("shutil.copy2")

    from best_practices_rag.cli import cmd_install

    cmd_install(argparse.Namespace(force=False))

    out = capsys.readouterr().out
    assert "Standalone Neo4j" in out
    assert "Existing Neo4j" in out
    assert "setup-schema" in out
    assert "setup-db" in out
