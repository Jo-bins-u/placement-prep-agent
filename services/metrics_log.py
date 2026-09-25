"""
Structured runtime metrics.

Every important backend result (resume parsed, answer scored, code judged, OTP
issued/verified, each HTTP request) is written as one JSON line to
logs/app_metrics.jsonl and as a readable line to logs/app_metrics.log.
`python -m validation.usage_report` turns these into a numeric report.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
JSONL_PATH = LOG_DIR / "app_metrics.jsonl"

JSONL_MAX_BYTES = 20_000_000   # rotate app_metrics.jsonl at ~20 MB ...
JSONL_BACKUPS = 5              # ... keeping app_metrics.jsonl.1 - .5 (older data is dropped)

_lock = threading.Lock()
_configured = False
log = logging.getLogger("prepwise.metrics")


def configure() -> None:
    """Attach file handlers once (safe to call repeatedly)."""
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app_metrics.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    for name in ("prepwise.metrics", "prepwise.auth"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    _configured = True


def _clean(value):
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _rotate_if_needed() -> None:
    """Size-based rotation so the metrics file can't grow without limit (call with _lock held)."""
    try:
        if not JSONL_PATH.exists() or JSONL_PATH.stat().st_size < JSONL_MAX_BYTES:
            return
        for index in range(JSONL_BACKUPS - 1, 0, -1):
            older = JSONL_PATH.with_name(f"{JSONL_PATH.name}.{index}")
            if older.exists():
                older.replace(JSONL_PATH.with_name(f"{JSONL_PATH.name}.{index + 1}"))
        JSONL_PATH.replace(JSONL_PATH.with_name(f"{JSONL_PATH.name}.1"))
    except OSError:  # pragma: no cover - never break a request over log housekeeping
        pass


def metric_files() -> list:
    """Current and rotated metrics files, oldest first."""
    rotated = [JSONL_PATH.with_name(f"{JSONL_PATH.name}.{i}") for i in range(JSONL_BACKUPS, 0, -1)]
    return [path for path in rotated + [JSONL_PATH] if path.exists()]


def log_event(event: str, **fields) -> None:
    """Record one metric event. Never raises (metrics must not break a request).
    Set PREPWISE_METRICS=off to disable (tests and the validation suite do this)."""
    if os.getenv("PREPWISE_METRICS", "on").lower() == "off":
        return
    try:
        configure()
        record = {"ts": datetime.utcnow().isoformat(timespec="milliseconds"), "event": event}
        record.update({k: _clean(v) for k, v in fields.items()})
        with _lock:
            _rotate_if_needed()
            with JSONL_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.info("%s %s", event, " ".join(f"{k}={v}" for k, v in record.items() if k not in ("ts", "event")))
    except Exception:  # pragma: no cover
        pass


class Timer:
    """with Timer() as t: ...  then t.ms"""

    def __enter__(self):
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self._start) * 1000
        return False
