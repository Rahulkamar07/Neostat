"""Central logging configuration.

Logs go to stdout (for Render/Railway) and a rotating file under logs/.
Never log request bodies that may contain secrets, or exception objects
that might include API keys.
"""

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from app.core.config import get_settings

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: Optional[str] = None) -> None:
    """Idempotent logging setup used at application startup."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_level = getattr(logging, (level or settings.log_level), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Keep third-party loggers quieter unless we are debugging.
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Logging configured (level=%s, env=%s)", settings.log_level, settings.app_env
    )


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
