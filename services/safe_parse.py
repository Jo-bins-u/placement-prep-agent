"""Parse untrusted resume files safely.

Parsing runs in a separate Python process with a wall-clock timeout (plus CPU/memory limits
on Linux/macOS), and only a few parses may run at once, so a crafted "PDF bomb" or zip bomb
can't tie up the web server's threads or memory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

WORKER = Path(__file__).with_name("resume_worker.py")
PARSE_TIMEOUT_SECONDS = 10       # real resumes parse in well under a second
PARSE_MEMORY_BYTES = 1024 * 1024 * 1024  # enforced by the worker itself (all platforms)
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_CONCURRENT_PARSES = 4
QUEUE_WAIT_SECONDS = 8           # wait this long for a free slot before saying "busy"

_slots = threading.BoundedSemaphore(MAX_CONCURRENT_PARSES)
_per_client: dict = {}
_per_client_lock = threading.Lock()


class ParseBusy(Exception):
    """Too many resumes are being parsed right now."""


class ParseFailed(Exception):
    """The file couldn't be parsed (invalid, too complex, or took too long)."""


def parse_resume_file(path, display_name: str, client: str = "") -> tuple[dict, int]:
    """Return (profile dict, number of text characters). Raises ParseBusy or ParseFailed.
    Each client (IP / IPv6 /64) may have one parse at a time, so a few senders of slow files
    can't hold every slot; others wait briefly in line instead of being refused at once."""
    with _per_client_lock:
        if client and _per_client.get(client):
            raise ParseBusy()
        if client:
            _per_client[client] = True
    try:
        if not _slots.acquire(timeout=QUEUE_WAIT_SECONDS):
            raise ParseBusy()
        try:
            return _run_worker(path, display_name)
        finally:
            _slots.release()
    finally:
        if client:
            with _per_client_lock:
                _per_client.pop(client, None)


def _run_worker(path, display_name: str) -> tuple[dict, int]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8",
           "PREPWISE_PARSE_MEMORY": str(PARSE_MEMORY_BYTES), "PREPWISE_PARSE_CPU": str(PARSE_TIMEOUT_SECONDS)}
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    try:
        done = subprocess.run(  # nosec B603 - fixed interpreter and script, no shell
            [sys.executable, str(WORKER), str(path), display_name],
            capture_output=True, timeout=PARSE_TIMEOUT_SECONDS, env=env, start_new_session=True)
    except subprocess.TimeoutExpired as exc:
        raise ParseFailed("timeout") from exc
    if done.returncode != 0 or len(done.stdout) > MAX_OUTPUT_BYTES:
        raise ParseFailed("worker_error")
    try:
        result = json.loads(done.stdout.decode("utf-8"))
        return result["profile"], int(result["chars"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ParseFailed("bad_output") from exc
