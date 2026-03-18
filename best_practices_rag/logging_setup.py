import logging
import logging.handlers
from pathlib import Path


_LOG_FILE = Path.cwd() / "logs" / "skill.log"
_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def configure_skill_logging() -> None:
    _LOG_FILE.parent.mkdir(exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)

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

    root.addHandler(file_handler)
    root.addHandler(stderr_handler)
