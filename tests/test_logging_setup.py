import logging
import logging.handlers
import tempfile
from pathlib import Path
from unittest.mock import patch

from best_practices_rag.logging_setup import configure_skill_logging


def test_configure_adds_file_and_stderr_handlers() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            with patch("best_practices_rag.logging_setup._LOG_FILE", log_path):
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


def test_configure_is_idempotent() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            with patch("best_practices_rag.logging_setup._LOG_FILE", log_path):
                configure_skill_logging()
                count_after_first = len(root.handlers)
                configure_skill_logging()
                assert len(root.handlers) == count_after_first
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)


def test_file_handler_level_is_debug() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            with patch("best_practices_rag.logging_setup._LOG_FILE", log_path):
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


def test_stderr_handler_level_is_warning() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            with patch("best_practices_rag.logging_setup._LOG_FILE", log_path):
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


def test_creates_logs_directory() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    try:
        root.handlers.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "skill.log"
            with patch("best_practices_rag.logging_setup._LOG_FILE", log_path):
                configure_skill_logging()
                assert log_path.parent.exists()
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)
