from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    Path(settings.log_file_path).parent.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                },
                "json": {
                    "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": settings.log_level,
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": settings.log_file_path,
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "formatter": "plain",
                    "level": settings.log_level,
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": settings.log_level,
            },
        }
    )
