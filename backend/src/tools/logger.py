"""
Centralized logging configuration for DeerFlow Portfolio.
Import this module in any component that needs structured logging.

Usage:
    from src.tools.logger import get_logger
    logger = get_logger("portfolio_monitor")
    logger.info("Monitor started")
    logger.error("Connection failed", exc_info=True)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Returns a named logger with:
    - RotatingFileHandler → logs/<name>.log  (5 MB, 3 backups)
    - StreamHandler       → stdout

    Already-configured loggers are returned as-is (idempotent).
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    fh = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger
