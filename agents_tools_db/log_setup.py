"""
log_setup.py — Centralized logging for Pay Restore Demo
=========================================================
Provides a file-based logger for system failures and critical tool events.
Conversational content (LLM responses) is NOT logged here — only system events.

Log file: pay_restore.log (in project root, git-ignored)

Event categories:
    SAFETY    — Azure API calls, blocks, errors (T1/T2a/T2b)
    TOOL      — Critical tool executions (T3 payment, T5 restore, T6 plan change)
    API       — Gemini API failures (timeouts, DNS, connection errors)
    DB        — Database errors
    SYSTEM    — Startup, shutdown, configuration errors

Usage:
    from pay_restore_demo.log_setup import get_logger
    log = get_logger("safety")
    log.info("BLOCKED  category=Violence  account=20001")
    log.error("Azure timeout — failing open  url=...")
"""

import logging
import logging.handlers
import os
from datetime import datetime

_LOG_PATH = os.path.join(os.path.dirname(__file__), "pay_restore.log")

_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure():
    global _configured
    if _configured:
        return

    root = logging.getLogger("pay_restore")
    root.setLevel(logging.DEBUG)

    # File handler — rotates at 5 MB, keeps 3 backups
    fh = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(fh)

    # Console handler — WARNING and above only (don't flood terminal)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(ch)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the pay_restore namespace."""
    _configure()
    return logging.getLogger(f"pay_restore.{name}")
