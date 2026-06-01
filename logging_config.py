"""
Wakeel — Logging Configuration

Sets up:
    - Standard application logs to stderr (human-readable)
    - Audit logs to logs/audit.jsonl (structured, one JSON per line)
    - Per-run logs to logs/run_<run_id>.jsonl (rotated per request)
"""

import logging
import os
import sys
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "./logs"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure all loggers used by Wakeel. Call once at startup."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Root logger -> stderr, human-readable
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    # Clear any pre-existing handlers (uvicorn / streamlit add their own)
    for h in list(root.handlers):
        root.removeHandler(h)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(stderr_handler)

    # Audit logger -> logs/audit.jsonl, structured
    audit_logger = logging.getLogger("wakeel.llm.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False  # don't double-log to stderr

    audit_handler = logging.FileHandler(LOG_DIR / "audit.jsonl", encoding="utf-8")
    audit_handler.setFormatter(logging.Formatter(fmt="%(message)s"))
    audit_logger.addHandler(audit_handler)

    # Agent interaction logger -> per-run files (set up by run.py per request)
    logging.getLogger("wakeel.agents").setLevel(LOG_LEVEL)


def get_run_logger(run_id: str) -> logging.Logger:
    """Get a logger that writes structured JSONL to logs/run_<run_id>.jsonl."""
    name = f"wakeel.run.{run_id}"
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.FileHandler(LOG_DIR / f"run_{run_id}.jsonl", encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt="%(message)s"))
    logger.addHandler(handler)
    return logger
