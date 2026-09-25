"""
Authentication helpers: password hashing, one-time codes (OTP) and email delivery.

OTP design
----------
* Codes are 6 digits from ``secrets`` (cryptographically secure), never ``random``.
* Only an HMAC-SHA256 of the code is stored, bound to the user id and purpose,
  so a leaked database row can't be replayed and a sign-up code can't be used
  to reset a password.
* Each code expires after OTP_TTL_MINUTES, allows OTP_MAX_ATTEMPTS wrong
  guesses, and a new code can be requested only after OTP_RESEND_SECONDS.
"""

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bcrypt
from flask_login import UserMixin

import database as db
from services.security import mask_email

log = logging.getLogger("prepwise.auth")

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_CODES_PER_HOUR = 6
PASSWORD_MIN_LENGTH = 8

PURPOSE_VERIFY = "verify"
PURPOSE_RESET = "reset"
_PURPOSES = {PURPOSE_VERIFY, PURPOSE_RESET}


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw((password or "").encode("utf-8"), (hashed or "").encode("utf-8"))
    except ValueError:
        return False


_DUMMY_HASH = []


def burn_password_check(password: str) -> None:
    """Spend the same bcrypt time as a real check, so response timing doesn't reveal
    whether an email address has an account."""
    if not _DUMMY_HASH:
        _DUMMY_HASH.append(hash_password(secrets.token_urlsafe(16)))
    check_password(password, _DUMMY_HASH[0])


DISPLAY_NAME_MAX = 40


def clean_display_name(value) -> tuple:
    """(cleaned name, error or None). Display only: letters, digits, spaces and . - ' _ allowed."""
    import unicodedata
    name = " ".join(str(value or "").split())
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")  # no control/invisible chars
    if len(name) < 2:
        return "", "Please enter a name of at least 2 characters."
    if len(name) > DISPLAY_NAME_MAX:
        return "", f"Please keep your name under {DISPLAY_NAME_MAX} characters."
    if not all(ch.isalnum() or ch in " .-'_" for ch in name):
        return "", "Names can use letters, numbers, spaces and . - ' _ only."
    return name, None


PASSWORD_MAX_BYTES = 72  # bcrypt only uses the first 72 bytes (and bcrypt 5 rejects longer input)

# A small offline blocklist of the most common passwords that pass the length/letter/digit rules.
# The breached-password check below covers millions more when the internet is reachable.
_COMMON_PASSWORDS = {
    "password1", "password12", "password123", "password1234", "passw0rd1", "abc12345", "abcd1234",
    "qwerty123", "qwerty1234", "1q2w3e4r", "1q2w3e4r5t", "iloveyou1", "welcome1", "welcome123",
    "admin123", "admin1234", "letmein1", "monkey123", "dragon123", "football1", "baseball1",
    "sunshine1", "princess1", "trustno1", "zaq12wsx", "asdf1234", "test1234", "hello123",
    "changeme1", "p@ssw0rd", "p@ssword1", "india123", "student123", "placement1", "prepwise1",
}


def password_problem(password: str, confirm: str | None = None, email: str | None = None) -> str | None:
    """Return a user-facing error for a weak/mismatched password, or None if it's fine.
    Follows NIST SP 800-63B: length first, then block common, breached and personal passwords."""
    password = password or ""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return f"Password is too long (maximum {PASSWORD_MAX_BYTES} bytes)."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one number."
    if confirm is not None and password != confirm:
        return "Passwords do not match."
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(lowered)) <= 2:
        return "That password is too common. Please choose something harder to guess."
    local_part = (email or "").split("@")[0].lower()
    if len(local_part) >= 4 and local_part in lowered:
        return "Your password shouldn't contain your email address."
    if password_breached(password):
        return "That password has appeared in a known data breach. Please choose a different one."
    return None


def password_breached(password: str) -> bool:
    """Have I Been Pwned "range" check (k-anonymity: only the first 5 characters of the SHA-1
    hash leave this machine, never the password). Fails open if the service can't be reached.
    Disable with PREPWISE_HIBP=off (e.g. offline development)."""
    if os.getenv("PREPWISE_HIBP", "on").strip().lower() in ("off", "0", "false"):
        return False
    import urllib.request
    # SHA-1 is what the HIBP range API uses; it's a lookup key here, not password storage.
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        request = urllib.request.Request(f"https://api.pwnedpasswords.com/range/{prefix}",
                                         headers={"Add-Padding": "true", "User-Agent": "Prepwise"})
        # Fixed https:// URL (never user-controlled), so the scheme check B310 warns about is moot.
        with urllib.request.urlopen(request, timeout=3) as response:  # nosec B310
            body = response.read().decode("utf-8", "ignore")
    except Exception as exc:
        log.info("breached_password_check_skipped reason=%s", type(exc).__name__)
        return False
    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix and count.strip() not in ("", "0"):
            return True
    return False


# ---------------------------------------------------------------------------
# One-time codes
# ---------------------------------------------------------------------------
def generate_otp(length: int = OTP_LENGTH) -> str:
    """Uniformly random numeric code (leading zeros allowed) from a CSPRNG."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _secret() -> bytes:
    from services.security import get_secret_key
    return get_secret_key().encode("utf-8")


def hash_otp(user_id: int, purpose: str, code: str) -> str:
    message = f"{user_id}:{purpose}:{code}".encode("utf-8")
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def _normalise_code(code: str) -> str:
    return "".join(ch for ch in (code or "") if ch.isdigit())


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _metric(event, **fields):
    try:
        from services.metrics_log import log_event
        log_event(event, **fields)
    except Exception:
        pass


@dataclass
class OtpIssueResult:
    ok: bool
    message: str
    wait_seconds: int = 0
    delivered: bool = False


def issue_otp(user_row, purpose: str, *, now: datetime | None = None, force: bool = False,
              background: bool = False) -> OtpIssueResult:
    """Create, store and email a new code. Enforces the resend cool-down unless force=True."""
    if purpose not in _PURPOSES:
        raise ValueError(f"Unknown OTP purpose: {purpose}")
    now = now or datetime.utcnow()
    sent_at = _parse_time(user_row.get("otp_sent_at")) if hasattr(user_row, "get") else None
    if sent_at and not force and user_row.get("otp_purpose") == purpose:
        elapsed = (now - sent_at).total_seconds()
        if elapsed < OTP_RESEND_SECONDS:
            wait = int(OTP_RESEND_SECONDS - elapsed) + 1
            return OtpIssueResult(False, f"Please wait {wait} seconds before requesting another code.", wait)

    # Hard cap on codes per account per hour (each new code gets fresh attempts, so this
    # bounds total guesses even for someone who waits out every cool-down).
    from services.security import limiter, rate_limiting_enabled
    if rate_limiting_enabled():
        # Counted per purpose, so reset-code spam can't block sign-up verification (or vice versa).
        wait = limiter.hit(f"otp_issue:{user_row['id']}:{purpose}", OTP_MAX_CODES_PER_HOUR, 3600)
        if wait:
            log.warning("otp_issue_capped user_id=%s purpose=%s", user_row["id"], purpose)
            return OtpIssueResult(False, f"Too many codes requested. Try again in {int(wait // 60) + 1} minutes.", int(wait))

    code = generate_otp()
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)
    db.store_otp(user_row["id"], hash_otp(user_row["id"], purpose, code), purpose, expires.isoformat(), now.isoformat())
    if background and os.getenv("PREPWISE_SYNC_EMAIL") != "1":  # tests send synchronously
        # Send without making the visitor wait on SMTP: otherwise response time would reveal
        # whether an account exists (existing accounts would be the slow ones).
        import threading
        threading.Thread(target=send_otp_email, args=(user_row["email"], code, purpose), daemon=True).start()
        log.info("otp_issued user_id=%s purpose=%s delivered=background ttl_min=%s", user_row["id"], purpose, OTP_TTL_MINUTES)
        _metric("otp_issued", purpose=purpose, delivered="background", mail_configured=_mail_configured())
        return OtpIssueResult(True, f"We sent a {OTP_LENGTH}-digit code to {user_row['email']}.", 0, False)
    delivered = send_otp_email(user_row["email"], code, purpose)
    log.info("otp_issued user_id=%s purpose=%s delivered=%s ttl_min=%s", user_row["id"], purpose, delivered, OTP_TTL_MINUTES)
    _metric("otp_issued", purpose=purpose, delivered=delivered, mail_configured=_mail_configured())
    if not delivered and _mail_configured():
        return OtpIssueResult(False, "We couldn't send the email right now. Please try again in a minute.", 0, False)
    return OtpIssueResult(True, f"We sent a {OTP_LENGTH}-digit code to {user_row['email']}.", 0, delivered)


# Result codes from verify_otp
OTP_OK = "ok"
OTP_INVALID = "invalid"
OTP_EXPIRED = "expired"
OTP_LOCKED = "locked"
OTP_MISSING = "missing"

OTP_MESSAGES = {
    OTP_INVALID: "That code isn't right. Check the email and try again.",
    OTP_EXPIRED: "That code has expired. Request a new one.",
    OTP_LOCKED: "Too many incorrect attempts. Request a new code.",
    OTP_MISSING: "No active code for this account. Request a new one.",
}


def verify_otp(user_id: int, code: str, purpose: str, *, now: datetime | None = None) -> str:
    """Check a code. Returns one of OTP_OK / OTP_INVALID / OTP_EXPIRED / OTP_LOCKED / OTP_MISSING.
    Every check atomically spends one attempt first (so concurrent guesses can't bypass the
    limit), and a correct code is consumed exactly once."""
    now = now or datetime.utcnow()
    row = db.get_user_by_id(user_id)
    if not row or not row.get("otp_code") or row.get("otp_purpose") != purpose:
        result = OTP_MISSING
    else:
        active = db.consume_otp_attempt(user_id, purpose, OTP_MAX_ATTEMPTS)
        if active is None:
            result = OTP_LOCKED
        elif (_parse_time(active.get("otp_expires_at")) or now) < now:
            result = OTP_EXPIRED
        else:
            given = hash_otp(user_id, purpose, _normalise_code(code))
            if hmac.compare_digest(str(active["otp_code"]), given) and db.consume_otp_code(user_id, given):
                result = OTP_OK
            else:
                fresh = db.get_user_by_id(user_id) or {}
                attempts_left = OTP_MAX_ATTEMPTS - int(fresh.get("otp_attempts") or OTP_MAX_ATTEMPTS)
                result = OTP_LOCKED if attempts_left <= 0 else OTP_INVALID
    log.info("otp_verify user_id=%s purpose=%s result=%s", user_id, purpose, result)
    _metric("otp_verified", purpose=purpose, result=result)
    return result


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
def _mail_configured() -> bool:
    return bool(os.getenv("MAIL_USERNAME") and os.getenv("MAIL_PASSWORD"))


_SUBJECTS = {
    PURPOSE_VERIFY: "Your Prepwise verification code",
    PURPOSE_RESET: "Reset your Prepwise password",
}
_INTROS = {
    PURPOSE_VERIFY: "Use this code to verify your Prepwise account:",
    PURPOSE_RESET: "Use this code to reset your Prepwise password:",
}


def send_otp_email(email: str, otp: str, purpose: str = PURPOSE_VERIFY) -> bool:
    """Send the code by SMTP. Returns True if the mail server accepted it.
    Without MAIL_USERNAME/MAIL_PASSWORD (local development) the code is printed to the console."""
    if not _mail_configured():
        # Local development without email: the code can be shown in this console, but only
        # when explicitly allowed - never on a real server, where logs are kept and shared.
        if _console_codes_allowed():
            print(f"\n{'=' * 40}")
            print("[DEV] MAIL_USERNAME / MAIL_PASSWORD not set - email not sent")
            print(f"[EMAIL] TO: {mask_email(email)}  PURPOSE: {purpose}")
            print(f"[OTP] CODE: {otp}")
            print(f"{'=' * 40}\n", flush=True)
        else:
            log.warning("otp_not_delivered mail_not_configured to=%s purpose=%s "
                        "(set MAIL_* in .env, or FLASK_DEBUG=1 to show codes in this console)",
                        mask_email(email), purpose)
        return False

    mail_username = os.getenv("MAIL_USERNAME")
    mail_password = os.getenv("MAIL_PASSWORD", "").replace(" ", "")
    msg = MIMEMultipart()
    msg["From"] = os.getenv("EMAIL_FROM", mail_username)
    msg["To"] = email
    msg["Subject"] = _SUBJECTS.get(purpose, _SUBJECTS[PURPOSE_VERIFY])
    body = (
        f"Hello,\n\n{_INTROS.get(purpose, _INTROS[PURPOSE_VERIFY])}\n\n    {otp}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes. If you didn't request it, you can ignore this email.\n\n"
        "The Prepwise Team"
    )
    msg.attach(MIMEText(body, "plain"))
    try:
        mail_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
        mail_port = int(os.getenv("MAIL_PORT", 587))
        with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
            server.starttls()
            server.login(mail_username, mail_password)
            server.send_message(msg)
        log.info("otp_email_sent to=%s purpose=%s", mask_email(email), purpose)
        return True
    except Exception as exc:
        log.error("otp_email_failed to=%s purpose=%s error=%s", mask_email(email), purpose, type(exc).__name__)
        return False


def _console_codes_allowed() -> bool:
    return os.getenv("FLASK_DEBUG") == "1" or os.getenv("PREPWISE_PRINT_OTP") == "1"


def send_account_exists_email(email: str) -> bool:
    """Someone tried to sign up with an address that already has an account. Tell the owner
    by email instead of telling the visitor on screen (which would reveal the account exists)."""
    if not _mail_configured():
        if _console_codes_allowed():
            print(f"[DEV] Sign-up attempted for existing account {mask_email(email)} - notice not emailed", flush=True)
        return False
    mail_username = os.getenv("MAIL_USERNAME")
    msg = MIMEMultipart()
    msg["From"] = os.getenv("EMAIL_FROM", mail_username)
    msg["To"] = email
    msg["Subject"] = "Someone tried to sign up with your email"
    msg.attach(MIMEText(
        "Hello,\n\nSomeone just tried to create a Prepwise account with this email address, but you "
        "already have one. If it was you, simply log in - or use \"Forgot password?\" on the login "
        "page if you don't remember your password.\n\nIf it wasn't you, no action is needed; your "
        "account hasn't been changed.\n\nThe Prepwise Team", "plain"))
    try:
        with smtplib.SMTP(os.getenv("MAIL_SERVER", "smtp.gmail.com"), int(os.getenv("MAIL_PORT", 587)), timeout=15) as server:
            server.starttls()
            server.login(mail_username, os.getenv("MAIL_PASSWORD", "").replace(" ", ""))
            server.send_message(msg)
        log.info("account_exists_email_sent to=%s", mask_email(email))
        return True
    except Exception as exc:
        log.error("account_exists_email_failed to=%s error=%s", mask_email(email), type(exc).__name__)
        return False


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.email = user_dict["email"]
        self.password_hash = user_dict["password_hash"]
        self.is_verified = user_dict["is_verified"]
        self.created_at = user_dict["created_at"]
        self.session_version = int(user_dict.get("session_version") or 0)
        self.display_name = user_dict.get("display_name") or ""

    def _fingerprint(self) -> str:
        from services.security import password_fingerprint
        return password_fingerprint(f"{self.password_hash}|v{self.session_version}")

    def get_id(self):
        """Session identity = user id + a fingerprint of the current password hash and session
        version, so a password change/reset, or logging out, invalidates every copy of the
        session cookie."""
        return f"{self.id}:{self._fingerprint()}"

    @classmethod
    def get(cls, user_id):
        row = db.get_user_by_id(user_id)
        if row:
            return cls(row)
        return None

    @classmethod
    def from_session_id(cls, session_id):
        """Load the user for a session identity, or None if it's stale (password changed/logged out)."""
        raw_id, _, fingerprint = str(session_id or "").partition(":")
        try:
            user = cls.get(int(raw_id))
        except (TypeError, ValueError):
            return None
        if not user or not fingerprint or not hmac.compare_digest(fingerprint, user._fingerprint()):
            return None
        return user
