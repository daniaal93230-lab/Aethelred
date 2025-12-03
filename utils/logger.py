"""
Centralized structured logging system.

Phase 2 upgrade: production-grade structured JSON + rich context.
Supports:
 - human-readable console logs for dev
 - structured JSON logs for production
 - consistent fields (ts, level, msg, extra)
 - DI-compatible and engine-safe
"""

from __future__ import annotations
import logging
import json
import datetime
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.datetime.now(datetime.UTC).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }

        # merge extra fields
        if hasattr(record, "__dict__"):
            for k, v in record.__dict__.items():
                if k not in ("msg", "args", "levelname", "name"):
                    payload[k] = v

        return json.dumps(payload)


def setup_logger(name: str) -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


# module-level logger (legacy modules import this)
logger = logging.getLogger("aethelred")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)


def log_extra(**kwargs: Any) -> dict:
    return {"extra": kwargs}


# -------------------------------------------------------------------
# Backwards-compatibility for legacy imports expected by tests:
# get_logger, log_json
# -------------------------------------------------------------------


def get_logger(name: str = "aethelred") -> logging.Logger:
    """Legacy shim: return module logger or create one with given name."""
    try:
        return logging.getLogger(name)
    except Exception:
        return logger


def log_json(*args: Any, **fields: Any) -> None:
    """Flexible legacy shim to support older call patterns.

    Supported signatures:
      - log_json(logger, level, msg, **extra)
      - log_json(msg, **fields)
    """
    try:
        # pattern: log_json(logger, level, msg, **extra)
        if len(args) >= 3 and isinstance(args[0], logging.Logger):
            lg = args[0]
            level = str(args[1]).lower()
            msg = args[2]
            extra = fields or {}
            method = getattr(lg, level, lg.info)
            method(msg, extra={"extra": extra})
            return

        # pattern: log_json(msg, **fields)
        if len(args) >= 1 and isinstance(args[0], str):
            msg = args[0]
            logger.info(msg, extra={"extra": fields})
            return

        # fallback: no-op
    except Exception:
        try:
            logger.info(str(args) if args else "log_json_fallback", extra={"extra": fields})
        except Exception:
            pass
