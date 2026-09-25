"""Security helpers shared by the app and auth: the signing key and a small rate limiter.

The rate limiter is in-memory (per process). That is right for a single `python app.py`
or single-worker deployment; with several gunicorn workers or servers, move the counters
to Redis (e.g. Flask-Limiter with a Redis storage URI) so the limits are shared.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

MIN_SECRET_LENGTH = 32

_MISSING_KEY_HELP = (
    "SECRET_KEY is not set (or is shorter than 32 characters). It signs every login session, "
    "so the app refuses to start without one.\n"
    "Add a line like this to your .env file (start.ps1 does it for you automatically):\n"
    "    SECRET_KEY=<output of: python -c \"import secrets; print(secrets.token_urlsafe(64))\">"
)

_KNOWN_WEAK = {"dev-secret-change-this-for-real-deployment", "change-me", "secret", "changeme"}


def get_secret_key() -> str:
    """The app's signing key from the environment. No fallback: a missing or weak key is fatal."""
    key = (os.getenv("SECRET_KEY") or "").strip()
    if len(key) < MIN_SECRET_LENGTH or key.lower() in _KNOWN_WEAK:
        raise RuntimeError(_MISSING_KEY_HELP)
    return key


class RateLimiter:
    """Sliding-window counter: allow at most `limit` hits per `window` seconds for each key.
    Memory is bounded: empty/expired keys are dropped and at most `max_keys` are kept
    (least recently used are evicted first)."""

    def __init__(self, max_keys: int = 100_000):
        from collections import OrderedDict
        self._hits = OrderedDict()   # key -> (deque of hit times, window)
        self._lock = threading.Lock()
        self.max_keys = max_keys
        self._calls = 0

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> float:
        """Record a hit. Returns 0 if allowed, otherwise the seconds until the next hit is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._hits.get(key)
            if entry is None:
                if len(self._hits) >= self.max_keys and not self._make_room(now):
                    # Table full of clients that are all still active (a flood of new keys):
                    # refuse rather than forget someone's lockout.
                    return 60.0
                hits = deque()
            else:
                hits = entry[0]
            while hits and hits[0] <= now - window:
                hits.popleft()
            self._hits[key] = (hits, window)
            self._hits.move_to_end(key)
            if len(hits) >= limit:
                return max(1.0, hits[0] + window - now)
            hits.append(now)
            self._calls += 1
            if self._calls % 1000 == 0:  # amortised clean-up of expired keys
                self._sweep(now)
            return 0.0

    def _make_room(self, now: float) -> bool:
        """Evict the least-recently-used key if it has expired (O(1)). False if even that one is active."""
        oldest_key, (hits, window) = next(iter(self._hits.items()))
        if hits and hits[-1] > now - window:
            return False
        del self._hits[oldest_key]
        return True

    def _sweep(self, now: float) -> None:
        for key in [k for k, (hits, window) in self._hits.items() if not hits or hits[-1] <= now - window]:
            del self._hits[key]

    def __len__(self) -> int:
        return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_network(ip: str) -> str:
    """Rate-limit IPv6 clients by their /64 (one household or server can own the whole block)."""
    import ipaddress
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip or "unknown"
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


limiter = RateLimiter()


def rate_limiting_enabled() -> bool:
    return os.getenv("PREPWISE_RATELIMIT", "on").strip().lower() not in ("off", "0", "false")


# ---------------------------------------------------------------------------
# CSRF protection (synchroniser token kept in the signed session cookie)
# ---------------------------------------------------------------------------
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRFToken"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_enabled() -> bool:
    return os.getenv("PREPWISE_CSRF", "on").strip().lower() not in ("off", "0", "false")


def csrf_token() -> str:
    """The current session's CSRF token (created on first use)."""
    from flask import session

    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def csrf_check_failed() -> bool:
    """True when an unsafe request lacks a valid token.

    JSON requests are exempt: a browser can only send `Content-Type: application/json`
    cross-site after a CORS preflight, which this app never approves (no CORS headers),
    so another site can't forge them. Every HTML form and the fetch() calls send a token."""
    from flask import request, session

    if request.method not in _UNSAFE_METHODS or request.is_json or not csrf_enabled():
        return False
    expected = session.get("_csrf")
    given = request.form.get(CSRF_FIELD) or request.headers.get(CSRF_HEADER) or ""
    return not (expected and given and hmac.compare_digest(str(expected), str(given)))


# ---------------------------------------------------------------------------
# Session revocation: a login is tied to the password it was made with
# ---------------------------------------------------------------------------
def password_fingerprint(password_hash: str) -> str:
    """Short keyed digest of the stored password hash. Stored in the session with the user id,
    so changing or resetting the password invalidates every existing login for that account."""
    digest = hmac.new(get_secret_key().encode("utf-8"), str(password_hash or "").encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:24]


def mask_email(email: str) -> str:
    """'jane.doe@gmail.com' -> 'j***@gmail.com' for logs."""
    email = str(email or "")
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


# ---------------------------------------------------------------------------
# Concurrency slots for slow work (code execution / problem generation)
# ---------------------------------------------------------------------------
class JobSlots:
    """At most `per_user` running jobs per user and `total` overall, so a few people can't
    occupy every server thread with long-running code."""

    def __init__(self, per_user: int = 1, total: int = 4):
        self.per_user, self.total = per_user, total
        self._running: dict = {}
        self._lock = threading.Lock()

    def try_acquire(self, user_key) -> str | None:
        """None if acquired, else "user" (their own job is still running) or "busy"."""
        with self._lock:
            if self._running.get(user_key, 0) >= self.per_user:
                return "user"
            if sum(self._running.values()) >= self.total:
                return "busy"
            self._running[user_key] = self._running.get(user_key, 0) + 1
            return None

    def release(self, user_key) -> None:
        with self._lock:
            left = self._running.get(user_key, 0) - 1
            if left > 0:
                self._running[user_key] = left
            else:
                self._running.pop(user_key, None)


code_jobs = JobSlots(per_user=1, total=int(os.getenv("PREPWISE_MAX_CODE_JOBS", "4")))
