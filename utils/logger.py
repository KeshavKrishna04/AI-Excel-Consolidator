import logging
import os
from typing import Optional


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "agent") -> logging.Logger:
    """
    Return a process-wide logger configured for console + file output.
    Log level can be controlled with LOG_LEVEL env var (DEBUG/INFO/WARN/ERROR).
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)

    if not logger.handlers:
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        file_handler = logging.FileHandler("agent.log")
        file_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    _LOGGERS[name] = logger
    return logger

