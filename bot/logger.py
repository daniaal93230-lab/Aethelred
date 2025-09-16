# bot/logger.py
import logging
import sys

_LOGGER_CREATED = False

def get_logger(name: str = "brain") -> logging.Logger:
    global _LOGGER_CREATED
    logger = logging.getLogger(name)
    if _LOGGER_CREATED:
        return logger

    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
    logger.propagate = False

    _LOGGER_CREATED = True
    return logger
