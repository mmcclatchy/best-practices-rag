import logging
import logging.handlers
from pathlib import Path


def _resolve_log_path() -> Path:
    local_marker = Path.cwd() / "pyproject.toml"
    if local_marker.exists() and "best-practices-rag" in local_marker.read_text()[:200]:
        return Path.cwd() / "logs" / "skill.log"
    return Path.home() / ".config" / "best-practices-rag" / "logs" / "skill.log"


_LOG_FILE = _resolve_log_path()
_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def configure_skill_logging() -> None:
    _LOG_FILE.parent.mkdir(exist_ok=True)

    app = logging.getLogger("best_practices_rag")
    if any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "baseFilename", None) == str(_LOG_FILE)
        for h in app.handlers
    ):
        return

    app.setLevel(logging.DEBUG)
    app.propagate = False

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    app.addHandler(file_handler)
    app.addHandler(stderr_handler)
