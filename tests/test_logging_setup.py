import logging
import logging.handlers
import tempfile
from pathlib import Path

from pytest_mock import MockerFixture

from best_practices_rag.logging_setup import _resolve_log_path, configure_skill_logging


def test_configure_adds_file_and_stderr_handlers(mocker: MockerFixture) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            assert any(
                isinstance(h, logging.handlers.RotatingFileHandler)
                for h in root.handlers
            )
            assert any(
                isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
                for h in root.handlers
            )
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_configure_is_idempotent(mocker: MockerFixture) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            count_after_first = len(root.handlers)
            configure_skill_logging()
            assert len(root.handlers) == count_after_first
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_file_handler_level_is_debug(mocker: MockerFixture) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            file_handlers = [
                h
                for h in root.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            assert file_handlers[0].level == logging.DEBUG
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_stderr_handler_level_is_warning(mocker: MockerFixture) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            stderr_handlers = [
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            ]
            assert stderr_handlers[0].level == logging.WARNING
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_creates_logs_directory(mocker: MockerFixture) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            assert log_path.parent.exists()
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_resolve_log_path_returns_dev_path_when_pyproject_present(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "best-practices-rag"\n')
    mocker.patch("best_practices_rag.logging_setup.Path.cwd", return_value=tmp_path)

    result = _resolve_log_path()

    assert result == tmp_path / "logs" / "skill.log"


def test_resolve_log_path_returns_prod_path_when_no_pyproject(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    # tmp_path has no pyproject.toml
    mocker.patch("best_practices_rag.logging_setup.Path.cwd", return_value=tmp_path)

    result = _resolve_log_path()

    assert (
        result == Path.home() / ".config" / "best-practices-rag" / "logs" / "skill.log"
    )


def test_resolve_log_path_returns_prod_path_when_pyproject_is_different_project(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "some-other-project"\n')
    mocker.patch("best_practices_rag.logging_setup.Path.cwd", return_value=tmp_path)

    result = _resolve_log_path()

    assert (
        result == Path.home() / ".config" / "best-practices-rag" / "logs" / "skill.log"
    )
