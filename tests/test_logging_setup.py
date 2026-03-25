import logging
import logging.handlers
import tempfile
from pathlib import Path

from pytest_mock import MockerFixture

from best_practices_rag.logging_setup import _resolve_log_path, configure_skill_logging


def _app_logger() -> logging.Logger:
    return logging.getLogger("best_practices_rag")


def _clear_app_logger() -> None:
    app = _app_logger()
    for h in app.handlers[:]:
        h.close()
        app.removeHandler(h)
    app.propagate = True
    app.setLevel(logging.NOTSET)


def test_configure_adds_file_and_stderr_handlers(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            app = _app_logger()
            assert any(
                isinstance(h, logging.handlers.RotatingFileHandler)
                for h in app.handlers
            )
            assert any(
                isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
                for h in app.handlers
            )
    finally:
        _clear_app_logger()


def test_configure_is_idempotent(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            count_after_first = len(_app_logger().handlers)
            configure_skill_logging()
            assert len(_app_logger().handlers) == count_after_first
    finally:
        _clear_app_logger()


def test_file_handler_level_is_debug(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            file_handlers = [
                h
                for h in _app_logger().handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            assert file_handlers[0].level == logging.DEBUG
    finally:
        _clear_app_logger()


def test_stderr_handler_level_is_warning(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            stderr_handlers = [
                h
                for h in _app_logger().handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            ]
            assert stderr_handlers[0].level == logging.WARNING
    finally:
        _clear_app_logger()


def test_creates_logs_directory(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            assert log_path.parent.exists()
    finally:
        _clear_app_logger()


def test_propagate_is_disabled(mocker: MockerFixture) -> None:
    try:
        _clear_app_logger()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            assert _app_logger().propagate is False
    finally:
        _clear_app_logger()


def test_configure_adds_file_handler_even_when_root_has_other_handler(
    mocker: MockerFixture,
) -> None:
    root = logging.getLogger()
    original_root_handlers = root.handlers[:]
    try:
        _clear_app_logger()
        root.addHandler(
            logging.StreamHandler()
        )  # simulates a library pre-adding a handler
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            mocker.patch("best_practices_rag.logging_setup._LOG_FILE", log_path)
            configure_skill_logging()
            assert any(
                isinstance(h, logging.handlers.RotatingFileHandler)
                for h in _app_logger().handlers
            )
    finally:
        _clear_app_logger()
        root.handlers.clear()
        root.handlers.extend(original_root_handlers)


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
