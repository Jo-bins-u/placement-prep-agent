"""
Main app — wires M1 (parsing) -> M2 (question selection) -> M3 (evaluation)
-> M4 (analytics) -> dashboard, behind a minimal Flask frontend.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "modules" / "profile_parsing"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "question_generation"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "evaluation"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "analytics"))

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
import secrets
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

import database as db
from services.safe_parse import parse_resume_file, ParseBusy, ParseFailed
import generator
import evaluator
import analytics
from services.resume_feedback import analyze_resume_feedback
from services.metrics_log import log_event, Timer, configure as configure_metrics
from modules.coding.problem_generator import generate_dsa_problem, validate_problem_schema, public_problem
from modules.coding.runner import run_candidate_code, evaluate_submission
from markupsafe import Markup
from services.profile_sanitize import sanitize_profile, MAX_PROFILE_JSON_BYTES
from services.security import (get_secret_key, limiter, rate_limiting_enabled, csrf_token,
                               csrf_check_failed, CSRF_FIELD, mask_email, code_jobs, client_network)

app = Flask(__name__)
app.secret_key = get_secret_key()  # no fallback: refuses to start without a real key
app.config.update(
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # resumes and form posts; larger requests get a 413
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),  # signed cookies older than this are rejected
)
if os.getenv("PREPWISE_TRUST_PROXY") == "1":  # behind one reverse proxy: use its X-Forwarded-For for rate limits
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

import auth

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(session_id):
    return auth.User.from_session_id(session_id)

@app.template_filter("topic")
def format_topic(value):
    """Display helper: 'dynamic_programming' -> 'Dynamic Programming', but keep 'SQL' / 'System Design' as-is."""
    text = str(value or "").replace("_", " ").strip()
    return text.title() if text.islower() else text


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


@app.template_filter("initials")
def initials(value):
    """'Cezen Technologies Pvt. Ltd.' -> 'CT' (ignores company suffixes)."""
    skip = {"pvt", "ltd", "llc", "inc", "private", "limited", "the", "and", "of", "&", "co", "corp"}
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", str(value or "")) if w.lower().strip(".") not in skip]
    return ("".join(w[0] for w in words[:2]) or "?").upper()


@app.template_filter("span_length")
def span_length(duration):
    """'Apr 2026 – May 2026' -> '2 mos'; 'Mar–Apr 2025' -> '2 mos'; 'June 2020 – Present' -> '6 yrs 4 mos'."""
    text = str(duration or "").lower()
    points = re.findall(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*'?(\d{2,4})?", text)
    years = re.findall(r"\b(\d{4})\b", text)
    if not points and len(years) < 2:
        return None
    try:
        if len(points) >= 2:
            (m1, y1), (m2, y2) = points[0], points[-1]
            y2 = y2 or (years[-1] if years else "")
            y1 = y1 or y2
            start = (int(y1 if len(y1) == 4 else "20" + y1), _MONTHS[m1])
            end = (int(y2 if len(y2) == 4 else "20" + y2), _MONTHS[m2])
        elif points and re.search(r"present|current|now|ongoing", text):
            m1, y1 = points[0]
            start = (int(y1), _MONTHS[m1])
            today = datetime.utcnow()
            end = (today.year, today.month)
        else:
            return None
    except (ValueError, KeyError):
        return None
    months = (end[0] - start[0]) * 12 + (end[1] - start[1]) + 1  # inclusive: Apr–May = 2 months
    if months <= 0 or months > 600:
        return None
    y, m = divmod(months, 12)
    parts = ([f"{y} yr{'s' if y > 1 else ''}"] if y else []) + ([f"{m} mo{'s' if m > 1 else ''}"] if m else [])
    return " ".join(parts)


@app.template_filter("as_json")
def as_json(value):
    """Readable JSON for display (autoescaped by Jinja, unlike |tojson which emits \\u0027 etc.)."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


@app.context_processor
def static_version():
    """Cache-bust static assets: the URL changes whenever style.css changes."""
    def asset_version(filename):
        try:
            return int((Path(app.static_folder) / filename).stat().st_mtime)
        except OSError:
            return 0
    return {"asset_version": asset_version}


HTTPS_ONLY = os.getenv("PREPWISE_HTTPS") == "1"  # set when served over HTTPS (behind a TLS proxy)
if HTTPS_ONLY:
    app.config.update(SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https")


def csp_nonce() -> str:
    """Per-response random value; only <script> tags carrying it may run (blocks injected scripts)."""
    if not hasattr(g, "csp_nonce"):
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


@app.after_request
def _security_headers(response):
    csp = "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{csp_nonce()}'",
        # Inline style attributes are used for widths/colours computed in templates.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])
    headers = response.headers
    headers.setdefault("Content-Security-Policy", csp)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if HTTPS_ONLY:
        headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if current_user.is_authenticated and request.endpoint != "static":
        # Personal pages must not be kept by shared caches or shown again after logout via Back.
        headers["Cache-Control"] = "no-store"
    return response


@app.template_filter("safe_url")
def safe_url(value):
    """Only http(s) links are rendered as links; anything else (javascript:, data:, ...) is dropped.
    Bare domains like 'github.com/me' get https:// added."""
    import re as _re
    from urllib.parse import urlparse
    link = str(value or "").strip()
    if not link or _re.search(r"[\s\"'<>\\]", link):
        return None
    if "://" not in link:
        if link.startswith("/") or _re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", link):
            return None  # a scheme without '//' (javascript:..., mailto:...) or a relative path
        link = "https://" + link
    parsed = urlparse(link)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None
    return parsed.geturl()


@app.context_processor
def csrf_helpers():
    """{{ csrf_field() }} inside every POST form; {{ csrf_token() }} for fetch() headers."""
    def csrf_field():
        # Markup.format() HTML-escapes the values it inserts.
        return Markup('<input type="hidden" name="{}" value="{}">').format(CSRF_FIELD, csrf_token())
    return {"csrf_token": csrf_token, "csrf_field": csrf_field, "csp_nonce": csp_nonce}


@app.context_processor
def nav_candidate():
    """Let every page link to the signed-in user's latest profile (dashboard / practice / DSA)."""
    def latest_candidate_id():
        if not current_user.is_authenticated:
            return None
        try:
            rows = db.get_candidates_by_user(current_user.id)
        except Exception:
            return None
        return rows[0]["id"] if rows else None
    return {"latest_candidate_id": latest_candidate_id}


def _owned_candidate(candidate_id: int):
    """Return the candidate row if it belongs to the signed-in user, else None."""
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate["user_id"] != current_user.id:
        return None
    return candidate


def _skill_profiles(attempts, dsa_performance) -> dict:
    """Evidence-based proficiency per topic (see analytics.compute_proficiency)."""
    bank_difficulty = {}
    try:
        bank_difficulty = {q["id"]: q.get("difficulty") for q in generator.load_question_bank()}
    except Exception:
        pass
    evidence = [
        {
            "topic": row["topic"],
            "score": row["score"],
            "difficulty": row.get("difficulty") or bank_difficulty.get(row.get("question_id")),
            "created_at": row.get("created_at"),
            "source": "interview",
        }
        for row in attempts
    ]
    evidence += [
        {**item, "topic": format_topic(item.get("topic")), "source": "dsa"}
        for item in dsa_performance.get("submissions", [])
    ]
    return analytics.compute_proficiency(evidence)


def _lines(value: str) -> list:
    return [line.strip(" •-\t") for line in (value or "").splitlines() if line.strip(" •-\t")]


def _csv(value: str) -> list:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _indexed(form, prefix: str) -> list:
    """Indexes of repeated form groups, in the order they appear on the page."""
    return [key[len(prefix):] for key in form if key.startswith(prefix)]


UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
RESUME_SIGNATURES = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}


def _save_resume_upload(file):
    """Validate an uploaded resume and save it under a random server-chosen name.
    Returns (path, ext, error). The client's filename is never used as a path."""
    if not file or not file.filename:
        return None, "", "Please choose a resume file (.pdf or .docx)."
    ext = Path(file.filename.replace("\\", "/")).suffix.lower()
    if ext not in RESUME_SIGNATURES:
        return None, ext, "Only .pdf and .docx resumes are supported right now."
    head = file.stream.read(len(RESUME_SIGNATURES[ext]))
    file.stream.seek(0)
    if head != RESUME_SIGNATURES[ext]:
        return None, ext, "That file doesn't look like a real PDF or Word document."
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    file.save(path)
    return path, ext, None


def _discard(path):
    """Uploaded files are only needed while parsing; the parsed profile lives in the database."""
    try:
        if path:
            Path(path).unlink(missing_ok=True)
    except OSError:
        pass
(Path(__file__).parent / "data").mkdir(exist_ok=True)

try:
    db.init_db()
except RuntimeError as _db_error:  # show a clear message instead of a long traceback
    raise SystemExit(f"\n[Prepwise] {_db_error}\n") from None
configure_metrics()


def _profile_counts(profile) -> dict:
    data = profile.to_dict() if hasattr(profile, "to_dict") else profile
    return {
        "skills": len(data.get("skills") or []),
        "projects": len(data.get("projects") or []),
        "internships": len(data.get("internships") or []),
        "education": len(data.get("education") or []),
        "has_email": bool((data.get("contact") or {}).get("email")),
        "needs_review": len(data.get("needs_review") or []),
    }


@app.before_request
def _start_timer():
    request._prepwise_started = time.perf_counter()


PUBLIC_ENDPOINTS = {"home", "register", "verify_email", "resend_code", "login", "forgot_password",
                    "reset_password", "upload", "static"}
JSON_PREFIXES = ("/api/", "/coding/", "/questions/", "/performance", "/skill-gaps")


def _wants_json() -> bool:
    return request.path.startswith(JSON_PREFIXES) or request.path.endswith("/run") or request.is_json


MAX_DB_ID = 2**63 - 1


def _json_object():
    """The JSON body if it is an object, else None."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _json_list(payload: dict, key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _requested_candidate_ids() -> list:
    """Every candidate id named anywhere in the request: URL, query string (all repeats),
    form (all repeats) and JSON body. The guard checks all of them, so a request can't pass
    the check with one id and act on another."""
    values = []
    if (request.view_args or {}).get("candidate_id") not in (None, ""):
        values.append(request.view_args["candidate_id"])
    values += [v for v in request.args.getlist("candidate_id") if v != ""]
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        values += [v for v in request.form.getlist("candidate_id") if v != ""]
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict) and payload.get("candidate_id") not in (None, ""):
            values.append(payload.get("candidate_id"))
    return values


def _as_db_id(value):
    """Positive 64-bit integer id, or None (bools, floats like 1.5/1e308, huge numbers, text)."""
    if isinstance(value, bool) or isinstance(value, float):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= MAX_DB_ID else None


# endpoint -> [(key source, max requests, window seconds, shared bucket or None)].
# Only POSTs are counted. "user" = the signed-in account (falls back to IP).
AI_DAILY = ("user", 200, 86400, "ai_daily")  # one shared daily budget for every AI-backed action
RATE_LIMITS = {
    "login": [("ip", 30, 900, None), ("email", 10, 900, None)],
    "register": [("ip", 10, 3600, None)],
    "verify_email": [("ip", 30, 600, None), ("email", 10, 600, None)],
    "reset_password": [("ip", 30, 600, None), ("email", 10, 600, None)],
    # Per email *and* network, so strangers spamming someone's address can't get that person's
    # own requests refused (the per-account hourly code cap in auth.issue_otp still applies).
    "resend_code": [("ip", 20, 3600, None), ("email_net", 6, 3600, None)],
    "forgot_password": [("ip", 20, 3600, None), ("email_net", 6, 3600, None)],
    "upload": [("ip", 20, 3600, None)],
    "reupload_resume": [("user", 20, 3600, None)],
    # AI-backed (each can call the LLM): per-hour burst limit + the shared daily budget
    "submit_answer": [("user", 60, 3600, None), AI_DAILY],
    "skip_question": [("user", 60, 3600, None), AI_DAILY],
    "generate_question_api": [("user", 30, 3600, None), AI_DAILY],
    "evaluate_question_api": [("user", 30, 3600, None), AI_DAILY],
    "generate_dsa": [("user", 30, 3600, None), AI_DAILY],
    "generate_coding_problem_api": [("user", 30, 3600, None), AI_DAILY],
    # Code execution (each run starts sandbox containers)
    "run_dsa": [("user", 40, 600, "code_run")],
    "run_coding_api": [("user", 40, 600, "code_run")],
    "submit_dsa": [("user", 20, 600, "code_submit")],
    "submit_coding_api": [("user", 20, 600, "code_submit")],
}


def _limit_key(source: str) -> str | None:
    if source in ("email", "email_net"):  # same field the handlers read (form or query string)
        email = _normal_email(request.values.get("email"))
        if not email:
            return None
        return f"{email}|{client_network(request.remote_addr or '')}" if source == "email_net" else email
    if source == "user" and current_user.is_authenticated:
        return f"u{current_user.id}"
    return client_network(request.remote_addr or "")


@app.before_request
def _csrf_protect():
    if request.endpoint == "static" or not csrf_check_failed():
        return None
    log_event("csrf_rejected", endpoint=request.endpoint)
    message = "Your session expired or the form was submitted from another site. Reload the page and try again."
    if _wants_json():
        return jsonify({"error": message}), 400
    return render_template("error.html", code=400, title="Please try again", message=message), 400


@app.before_request
def _rate_limit():
    rules = RATE_LIMITS.get(request.endpoint)
    if not rules or request.method != "POST" or not rate_limiting_enabled():
        return None
    for source, limit, window, bucket in rules:
        who = _limit_key(source)
        if who is None:
            continue
        wait = limiter.hit(f"{bucket or request.endpoint}:{source}:{who}", limit, window)
        if wait:
            log_event("rate_limited", endpoint=request.endpoint, source=source, bucket=bucket or request.endpoint)
            if wait >= 3600:
                when = f"about {int(wait // 3600) + 1} hours"
            else:
                minutes = int(wait // 60) + 1
                when = f"about {minutes} minute{'s' if minutes > 1 else ''}"
            message = f"Too many requests. Please wait {when} and try again."
            if bucket == "ai_daily":
                message = f"You've reached today's limit for AI-generated questions and grading. Please try again in {when}."
            if _wants_json():
                return jsonify({"error": message}), 429, {"Retry-After": str(int(wait))}
            return render_template("error.html", code=429, title="Slow down", message=message), 429, {"Retry-After": str(int(wait))}
    return None


@app.before_request
def _access_guard():
    """Every non-public page needs a signed-in user, and any candidate id in the request
    must belong to that user — so nobody can read or score someone else's profile."""
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if not current_user.is_authenticated:
        if _wants_json():
            return jsonify({"error": "Login required."}), 401
        return login_manager.unauthorized()
    requested = _requested_candidate_ids()
    if requested:
        ids = {_as_db_id(value) for value in requested}
        candidate = db.get_candidate(ids.pop()) if len(ids) == 1 and None not in ids else None
        if not candidate or candidate["user_id"] != current_user.id:
            log_event("access_denied", endpoint=request.endpoint, user_id=current_user.id)
            if _wants_json():
                return jsonify({"error": "Candidate not found."}), 404
            flash("That profile wasn't found in your account.", "error")
            return redirect(url_for("home"))
    return None


@app.after_request
def _log_request(response):
    started = getattr(request, "_prepwise_started", None)
    if started is not None and request.endpoint not in (None, "static"):
        log_event("http_request", endpoint=request.endpoint, method=request.method,
                  status=response.status_code, ms=(time.perf_counter() - started) * 1000)
    return response


def _restore_and_save_profile(profile_data, user_id: int) -> int:
    return db.save_candidate(user_id, _profile_from_dict(profile_data))


def _profile_from_dict(profile_data):
    """Deserialise a CandidateProfile that was serialised to the session as JSON
    and save it as a new candidate row, returning the candidate_id."""
    import json as _json
    from modules.profile_parsing.schema import CandidateProfile, ContactInfo, Education, Internship, Project

    if isinstance(profile_data, str):
        profile_data = _json.loads(profile_data)
    import copy as _copy
    profile_data = _copy.deepcopy(profile_data)

    # Reconstruct nested dataclasses from dicts
    raw = profile_data
    contact = raw.get("contact", {})
    if isinstance(contact, dict):
        raw["contact"] = ContactInfo(**{k: v for k, v in contact.items() if k in ContactInfo.__dataclass_fields__})
    education = raw.get("education", [])
    raw["education"] = [
        Education(**{k: v for k, v in e.items() if k in Education.__dataclass_fields__})
        if isinstance(e, dict) else e
        for e in education
    ]
    projects = raw.get("projects", [])
    raw["projects"] = [
        Project(**{k: v for k, v in p.items() if k in Project.__dataclass_fields__})
        if isinstance(p, dict) else p
        for p in projects
    ]
    internships = raw.get("internships", [])
    raw["internships"] = [
        Internship(**{k: v for k, v in i.items() if k in Internship.__dataclass_fields__})
        if isinstance(i, dict) else i
        for i in internships
    ]
    allowed = CandidateProfile.__dataclass_fields__
    return CandidateProfile(**{k: v for k, v in raw.items() if k in allowed})


@app.route("/")
def home():
    return render_template("upload.html")


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normal_email(value) -> str:
    return (value or "").strip().lower()


def _digest(value):
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _safe_next(target: str) -> str:
    """Only allow same-site relative paths after login (prevents open redirects).
    Browsers drop tabs/newlines and treat '\\' like '/', so '/\t/evil.com' or '/\\evil.com'
    would become '//evil.com' - any control character, whitespace or backslash is refused."""
    from urllib.parse import urlsplit
    target = str(target or "")
    if (not target.startswith("/") or target.startswith("//") or "\\" in target
            or any(ord(ch) < 33 or ord(ch) == 127 for ch in target) or len(target) > 500):
        return url_for("home")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or parts.path.startswith("//"):
        return url_for("home")
    return target


def _after_login_redirect(user, next_url: str = ""):
    session.pop("pending_profile", None)  # older versions kept the whole resume in the cookie
    profile_data = db.pop_pending_upload(session.pop("pending_upload", None))
    if profile_data:
        candidate_id = _restore_and_save_profile(profile_data, user.id)
        return redirect(url_for("verify_profile", candidate_id=candidate_id))
    return redirect(_safe_next(next_url))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = _normal_email(request.form.get("email"))
        password = request.form.get("password", "")
        # The sign-up form always sends a name; older clients that don't are asked for it later.
        raw_name = request.form.get("display_name")
        display_name, name_problem = auth.clean_display_name(raw_name) if raw_name is not None else (None, None)
        problem = None if EMAIL_RE.match(email) else "Enter a valid email address."
        problem = problem or name_problem
        problem = problem or auth.password_problem(password, request.form.get("confirm_password", ""), email)
        if problem:
            flash(problem, "error")
            return render_template("auth/register.html", email=email,
                                   display_name=request.form.get("display_name", "")[:60]), 400

        # Same response whether or not the address already has an account, so sign-up can't be
        # used to find out who is registered. The real owner is told by email instead.
        password_hash = auth.hash_password(password)
        existing = db.get_user_by_email(email)
        if existing and existing["is_verified"]:
            # At most 3 "someone tried to sign up with your email" notices per address per day.
            if not rate_limiting_enabled() or not limiter.hit(f"exists_notice:{email}", 3, 86400):
                if os.getenv("PREPWISE_SYNC_EMAIL") == "1":
                    auth.send_account_exists_email(existing["email"])
                else:
                    import threading
                    threading.Thread(target=auth.send_account_exists_email, args=(existing["email"],), daemon=True).start()
        elif existing:
            # Signed up before but never verified. The new password is kept aside and applied
            # only if the code is entered in *this* browser (nonce in the signed session), so a
            # stranger re-registering the address can't get their password onto the account.
            nonce = secrets.token_urlsafe(24)
            session["pending_pw_nonce"] = nonce
            db.set_pending_password(existing["id"], password_hash, _digest(nonce))
            auth.issue_otp(existing, auth.PURPOSE_VERIFY, background=True)
        else:
            user_row = db.get_user_by_id(db.create_user(email, password_hash, display_name))
            # Emails go out in the background on every branch, so response time is the same
            # whether or not the address already has an account.
            auth.issue_otp(user_row, auth.PURPOSE_VERIFY, force=True, background=True)
        flash(f"We've sent a {auth.OTP_LENGTH}-digit code to {email}. Enter it below to finish signing up. "
              "(Already have an account? Just log in.)", "success")
        return redirect(url_for("verify_email", email=email))
    return render_template("auth/register.html", email=request.args.get("email", ""), display_name="")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email = _normal_email(request.values.get("email"))
    if request.method == "POST":
        user_row = db.get_user_by_email(email) if email else None
        if not user_row or user_row["is_verified"]:
            result = auth.OTP_INVALID  # same answer as a wrong code: don't reveal account status
        else:
            result = auth.verify_otp(user_row["id"], request.form.get("otp", ""), auth.PURPOSE_VERIFY)
        if result == auth.OTP_OK:
            db.apply_pending_password(user_row["id"], _digest(session.pop("pending_pw_nonce", None)))
            db.mark_user_verified(user_row["id"])
            user = auth.User(db.get_user_by_id(user_row["id"]))
            login_user(user)
            flash("Email verified! You're now logged in.", "success")
            return _after_login_redirect(user)
        flash(auth.OTP_MESSAGES[result], "error")
        return render_template("auth/verify_email.html", email=email, purpose=auth.PURPOSE_VERIFY), 400

    if not email:
        return redirect(url_for("register"))
    return render_template("auth/verify_email.html", email=email, purpose=auth.PURPOSE_VERIFY)


@app.route("/resend-code", methods=["POST"])
def resend_code():
    email = _normal_email(request.form.get("email"))
    purpose = request.form.get("purpose", auth.PURPOSE_VERIFY)
    if purpose not in (auth.PURPOSE_VERIFY, auth.PURPOSE_RESET):
        purpose = auth.PURPOSE_VERIFY
    target = "verify_email" if purpose == auth.PURPOSE_VERIFY else "reset_password"

    user_row = db.get_user_by_email(email) if email else None
    if user_row and not (purpose == auth.PURPOSE_VERIFY and user_row["is_verified"]):
        auth.issue_otp(user_row, purpose, background=True)
    # Same message in every case, so this can't be used to probe which emails are registered.
    flash(f"If {email} is waiting for a code, a new one is on its way. Codes can be re-sent once a minute.", "success")
    return redirect(url_for(target, email=email))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next", "")))

    if request.method == "POST":
        email = _normal_email(request.form.get("email"))
        password = request.form.get("password", "")
        next_url = request.form.get("next", "")
        user_row = db.get_user_by_email(email)
        if not user_row:
            auth.burn_password_check(password)  # equal timing for unknown emails
        if user_row and auth.check_password(password, user_row["password_hash"]):
            if user_row.get("pending_password_hash"):
                db.set_pending_password(user_row["id"], None)  # the real password was used: drop any pending one
            if not user_row["is_verified"]:
                result = auth.issue_otp(user_row, auth.PURPOSE_VERIFY)
                flash("Please verify your email first. " + result.message, "error")
                return redirect(url_for("verify_email", email=email))
            user = auth.User(user_row)
            login_user(user)
            return _after_login_redirect(user, next_url)
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html", next=next_url, email=email), 401
    return render_template("auth/login.html", next=request.args.get("next", ""), email=request.args.get("email", ""))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = _normal_email(request.form.get("email"))
        if not EMAIL_RE.match(email):
            flash("Enter a valid email address.", "error")
            return render_template("auth/forgot_password.html", email=email), 400
        user_row = db.get_user_by_email(email)
        if user_row:
            auth.issue_otp(user_row, auth.PURPOSE_RESET, background=True)  # outcome not shown: same page either way
        app.logger.info("password_reset_requested account_exists=%s", bool(user_row))
        flash(f"If an account exists for {email}, we've sent a {auth.OTP_LENGTH}-digit reset code.", "success")
        return redirect(url_for("reset_password", email=email))
    return render_template("auth/forgot_password.html", email=request.args.get("email", ""))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = _normal_email(request.values.get("email"))
    if not email:
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        problem = auth.password_problem(password, request.form.get("confirm_password", ""), email)
        user_row = db.get_user_by_email(email)
        if problem:
            flash(problem, "error")
        elif not user_row:
            flash(auth.OTP_MESSAGES[auth.OTP_INVALID], "error")
        else:
            result = auth.verify_otp(user_row["id"], request.form.get("otp", ""), auth.PURPOSE_RESET)
            if result == auth.OTP_OK:
                db.update_password(user_row["id"], auth.hash_password(password))
                db.set_pending_password(user_row["id"], None)
                db.mark_user_verified(user_row["id"])  # they proved they own the inbox
                if current_user.is_authenticated:
                    logout_user()
                app.logger.info("password_reset_completed user_id=%s", user_row["id"])
                flash("Password updated. Log in with your new password.", "success")
                return redirect(url_for("login", email=email))
            flash(auth.OTP_MESSAGES[result], "error")
        return render_template("auth/reset_password.html", email=email, purpose=auth.PURPOSE_RESET), 400
    return render_template("auth/reset_password.html", email=email, purpose=auth.PURPOSE_RESET)


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        user_row = db.get_user_by_id(current_user.id)
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("password", "")
        problem = auth.password_problem(new_pw, request.form.get("confirm_password", ""), current_user.email)
        if not auth.check_password(current_pw, user_row["password_hash"]):
            problem = "Your current password is incorrect."
        elif not problem and auth.check_password(new_pw, user_row["password_hash"]):
            problem = "Choose a password different from your current one."
        if problem:
            flash(problem, "error")
            return render_template("auth/change_password.html"), 400
        db.update_password(current_user.id, auth.hash_password(new_pw))
        app.logger.info("password_changed user_id=%s", current_user.id)
        # The new password hash changes the session fingerprint: every other browser is signed
        # out; this one is signed straight back in.
        login_user(auth.User(db.get_user_by_id(current_user.id)))
        flash("Your password has been changed. Any other devices have been signed out.", "success")
        return redirect(url_for("home"))
    return render_template("auth/change_password.html")


@app.route("/account/name", methods=["POST"])
@login_required
def change_display_name():
    name, problem = auth.clean_display_name(request.form.get("display_name"))
    if problem:
        flash(problem, "error")
    else:
        db.set_display_name(current_user.id, name)
        flash("Your display name has been updated.", "success")
    return redirect(url_for("change_password"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    # Invalidate this login everywhere, including any copy of the cookie (e.g. one stolen
    # earlier): the session version is part of every session's identity.
    db.bump_session_version(current_user.id)
    logout_user()
    return redirect(url_for("login"))


def _parse_uploaded(save_path, display_name: str, ext: str, source: str):
    """Parse in a time/memory-limited child process. Returns (profile, chars, error message)."""
    try:
        with Timer() as t:
            data, chars = parse_resume_file(save_path, display_name, client_network(request.remote_addr or ""))
        profile = _profile_from_dict(data)
    except ParseBusy:
        log_event("resume_parse_busy", source=source)
        return None, 0, "We're processing a lot of resumes right now. Please try again in a moment."
    except (ParseFailed, Exception) as exc:  # invalid, too complex or too slow: never crash the request
        log_event("resume_parse_failed", source=source, file_type=ext, reason=str(exc)[:40])
        return None, 0, "We couldn't read that file. Try exporting your resume as a PDF and upload it again."
    finally:
        _discard(save_path)
    log_event("resume_parsed", source=source, file_type=ext, ms=t.ms, chars=chars, **_profile_counts(profile))
    return profile, chars, None


@app.route("/upload", methods=["POST"])
def upload():
    save_path, ext, problem = _save_resume_upload(request.files.get("resume"))
    if problem:
        flash(problem, "error")
        return redirect(url_for("home"))
    display_name = secure_filename(request.files["resume"].filename) or f"resume{ext}"
    profile, chars, error = _parse_uploaded(save_path, display_name, ext, "upload")
    if error:
        flash(error, "error")
        return redirect(url_for("home"))

    if current_user.is_authenticated:
        candidate_id = db.save_candidate(current_user.id, profile)
        return redirect(url_for("verify_profile", candidate_id=candidate_id))
    else:
        # Only an opaque id goes in the (client-side) session cookie; the resume stays on the server.
        session["pending_upload"] = db.save_pending_upload(profile.to_json())
        flash("Please sign up or log in to view your resume analysis.", "success")
        return redirect(url_for("register"))


@app.route("/verify-profile/<int:candidate_id>", methods=["GET", "POST"])
@login_required
def verify_profile(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate["user_id"] != current_user.id:
        flash("Candidate not found or unauthorized.", "error")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])

    if request.method == "POST":
        form = request.form
        profile.setdefault("contact", {})
        profile["contact"]["name"] = form.get("contact_name", "").strip() or None
        profile["contact"]["email"] = form.get("contact_email", "").strip() or None
        profile["contact"]["phone"] = form.get("contact_phone", "").strip() or None

        profile["skills"] = _csv(form.get("skills", ""))

        education = []
        for idx in _indexed(form, "edu_institution_"):
            entry = {
                "institution": form.get(f"edu_institution_{idx}", "").strip() or None,
                "degree": form.get(f"edu_degree_{idx}", "").strip() or None,
                "field_of_study": form.get(f"edu_field_{idx}", "").strip() or None,
                "cgpa_or_percentage": form.get(f"edu_score_{idx}", "").strip() or None,
            }
            if any(entry.values()):
                education.append(entry)
        profile["education"] = education

        projects = []
        for idx in _indexed(form, "proj_title_"):
            points = _lines(form.get(f"proj_desc_{idx}", ""))
            title = form.get(f"proj_title_{idx}", "").strip()
            tech = _csv(form.get(f"proj_tech_{idx}", ""))
            links = _lines(form.get(f"proj_links_{idx}", ""))
            if not (title or points):
                continue
            projects.append({
                "title": title or None,
                "name": title or None,
                "description": " ".join(points) or None,
                "description_points": points,
                "tech_stack": tech,
                "technologies": tech,
                "links": links,
            })
        profile["projects"] = projects

        internships = []
        for idx in _indexed(form, "intern_role_"):
            points = _lines(form.get(f"intern_desc_{idx}", ""))
            entry = {
                "role": form.get(f"intern_role_{idx}", "").strip() or None,
                "company": form.get(f"intern_company_{idx}", "").strip() or None,
                "duration": form.get(f"intern_duration_{idx}", "").strip() or None,
                "location": form.get(f"intern_location_{idx}", "").strip() or None,
                "description": " ".join(points) or None,
                "description_points": points,
                "tech_stack": _csv(form.get(f"intern_tech_{idx}", "")),
            }
            if entry["role"] or entry["company"] or points:
                internships.append(entry)
        profile["internships"] = internships

        profile["verified"] = True
        profile = sanitize_profile(profile)  # whitelist fields, cap sizes, http(s)-only links
        db.update_candidate_profile(candidate_id, profile)
        flash("Profile saved. Your resume feedback has been refreshed.", "success")
        return redirect(url_for("dashboard", candidate_id=candidate_id))

    return render_template("verify_profile.html", candidate=candidate, profile=profile)


@app.route("/profile/<int:candidate_id>/reupload", methods=["POST"])
@login_required
def reupload_resume(candidate_id):
    """Replace the parsed resume details for an existing profile (practice history is kept)."""
    candidate = _owned_candidate(candidate_id)
    if not candidate:
        flash("Profile not found.", "error")
        return redirect(url_for("home"))

    back = url_for("dashboard", candidate_id=candidate_id)
    save_path, ext, problem = _save_resume_upload(request.files.get("resume"))
    if problem:
        flash(problem, "error")
        return redirect(back)
    display_name = secure_filename(request.files["resume"].filename) or f"resume{ext}"
    parsed, _, error = _parse_uploaded(save_path, display_name, ext, "reupload")
    if error:
        flash(error, "error")
        return redirect(back)

    profile = parsed.to_dict()
    profile["verified"] = False
    db.update_candidate_profile(candidate_id, profile)
    flash("Resume re-uploaded. Review the details we extracted, then save.", "success")
    return redirect(url_for("verify_profile", candidate_id=candidate_id))


@app.route("/dashboard/<int:candidate_id>")
@login_required
def dashboard(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    resume_feedback = db.get_resume_feedback(candidate_id)
    if resume_feedback and "experience" in (resume_feedback.get("category_scores") or {}):
        resume_feedback = None  # generated by an older version — rebuild with the current categories

    if resume_feedback is None:
        try:
            resume_feedback = analyze_resume_feedback(profile)
            db.save_resume_feedback(candidate_id, resume_feedback)
        except Exception:
            resume_feedback = {
                "overall_score": 0,
                "category_scores": {},
                "strengths": [],
                "weaknesses": ["Resume analysis could not be generated."],
                "suggestions": ["Reupload the resume to regenerate the review."],
                "summary": "Resume analysis needs regeneration.",
            }

    skill_profiles = _skill_profiles(attempts, dsa_performance)
    topic_scores = {topic: p["score"] for topic, p in skill_profiles.items()}
    weak_topics = analytics.weak_topics_from_profiles(skill_profiles)
    strong_topics = analytics.strong_topics_from_profiles(skill_profiles)
    recommendations = analytics.recommend_from_profiles(skill_profiles)
    avg_score = analytics.overall_proficiency(skill_profiles)

    return render_template(
        "dashboard.html",
        candidate=candidate,
        profile=profile,
        attempts=attempts,
        topic_scores=topic_scores,
        skill_profiles=skill_profiles,
        weak_topics=weak_topics,
        strong_topics=strong_topics,
        recommendations=recommendations,
        avg_score=avg_score,
        dsa_performance=dsa_performance,
        resume_feedback=resume_feedback,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/api/dashboard/<int:candidate_id>")
def dashboard_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    skill_profiles = _skill_profiles(attempts, dsa_performance)
    topic_scores = {topic: p["score"] for topic, p in skill_profiles.items()}
    return jsonify({
        "profile": profile,
        "projects": profile.get("projects", []),
        "skills": profile.get("skills", []),
        "internships": profile.get("internships", []),
        "education": profile.get("education", []),
        "interview": {
            "attempted": len(attempts),
            "average_score": analytics.overall_proficiency(skill_profiles),
        },
        "dsa": dsa_performance,
        "skill_gaps": topic_scores,
        "skill_profiles": skill_profiles,
    })


@app.route("/api/profile/<int:candidate_id>", methods=["GET", "PUT"])
def profile_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404

    if request.method == "GET":
        return jsonify(json.loads(candidate["profile_json"]))

    if (request.content_length or 0) > MAX_PROFILE_JSON_BYTES:
        return jsonify({"error": "Profile is too large."}), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Profile JSON object is required."}), 400
    contact = payload.get("contact")
    if not isinstance(contact, dict):
        return jsonify({"error": "Profile contact object is required."}), 400
    if not isinstance(payload.get("skills", []), list):
        return jsonify({"error": "Profile skills must be a list."}), 400
    profile = sanitize_profile(payload)  # unknown keys dropped, sizes capped, unsafe links removed
    if not db.update_candidate_profile(candidate_id, profile):
        return jsonify({"error": "Candidate not found."}), 404
    return jsonify(profile)


@app.route("/api/resume-feedback/<int:candidate_id>")
def resume_feedback_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404

    feedback = db.get_resume_feedback(candidate_id)
    if feedback is None or "experience" in (feedback.get("category_scores") or {}):
        profile = json.loads(candidate["profile_json"])
        feedback = analyze_resume_feedback(profile)
        db.save_resume_feedback(candidate_id, feedback)
    return jsonify(feedback)


PUBLIC_QUESTION_FIELDS = ("topic", "type", "difficulty", "prompt", "options", "reason", "source", "category", "mode", "repeat")


def _public_question(question: dict) -> dict:
    """What the browser may see: never the MCQ answer or the marking rubric."""
    return {k: question[k] for k in PUBLIC_QUESTION_FIELDS if k in question}


def _target_difficulty(skill_profiles: dict) -> str:
    """Adaptive difficulty from the candidate's rated topics."""
    rated = {t: p for t, p in skill_profiles.items() if p["status"] != "needs_data"}
    if not rated:
        return "medium"
    level = analytics.overall_proficiency(rated)
    return "easy" if level < 50 else ("medium" if level < 75 else "hard")


INTERVIEW_TOPIC_FOCUS = {"Behavioral": "behavioral", "Projects": "mixed", "Internships": "mixed", "Resume Skills": "skills"}


def practice_url(candidate_id, topic=None, mode=None):
    """Link to the right practice mode for a skill topic (used by the dashboard's Practice buttons)."""
    if topic in INTERVIEW_TOPIC_FOCUS:
        return url_for("practice", candidate_id=candidate_id, mode="interview", topic=INTERVIEW_TOPIC_FOCUS[topic])
    if topic and topic in generator.technical_topics():
        return url_for("practice", candidate_id=candidate_id, mode="technical", topic=topic)
    return url_for("practice", candidate_id=candidate_id, mode=mode) if mode else url_for("practice", candidate_id=candidate_id)


app.jinja_env.globals["practice_url"] = practice_url


def _practice_choice(profile: dict):
    """(mode, choice value) from the query string, else the last one used, else Technical/recommended."""
    remembered = session.get("practice_choice") or {}
    mode = request.args.get("mode") or remembered.get("mode") or "technical"
    mode = mode if mode in ("interview", "technical") else "technical"
    if "topic" in request.args:
        value = request.args.get("topic") or ""
    else:
        value = remembered.get(mode, "")
    if mode == "technical":
        value = value if value in generator.technical_topics() else "recommended"
    else:
        value = generator.resolve_focus(profile, value)["value"]
    choices = dict(remembered, mode=mode)
    choices[mode] = value
    session["practice_choice"] = choices
    return mode, value


@app.route("/practice/<int:candidate_id>")
@login_required
def practice(candidate_id):
    candidate = db.get_candidate(candidate_id)
    profile = json.loads(candidate["profile_json"])
    mode, value = _practice_choice(profile)
    issued = db.get_open_issued_question(candidate_id)
    if issued is not None:
        q = issued["question"]
        if q.get("mode", "technical") != mode or q.get("choice", value) != value:
            db.close_issued_question(issued["id"], "switched")  # user changed mode/topic: not counted
            issued = None
    if issued is None:
        attempts = db.get_attempts(candidate_id)
        dsa_performance = db.get_dsa_performance(candidate_id)
        skill_profiles = _skill_profiles(attempts, dsa_performance)
        answered = db.get_answered_question_ids(candidate_id)
        previous = db.get_recent_question_prompts(candidate_id)
        with Timer() as t:
            if mode == "interview":
                question = generator.pick_interview_question(
                    profile, generator.resolve_focus(profile, value), answered,
                    difficulty=_target_difficulty(skill_profiles), previous_prompts=previous)
            else:
                # Recommended = weak topics first, then topics that still need evidence.
                weak_topics = analytics.weak_topics_from_profiles(skill_profiles) + [
                    t for t, p in skill_profiles.items() if p["status"] == "needs_data"
                ]
                question = generator.pick_technical_question(
                    profile, None if value == "recommended" else value, weak_topics, answered,
                    difficulty=_target_difficulty(skill_profiles), previous_prompts=previous)
        if not question:
            flash("No questions are available for that choice right now. Try another topic.", "error")
            return redirect(url_for("dashboard", candidate_id=candidate_id))
        question = dict(question, mode=mode, choice=value)
        issue_id = f"iq-{uuid.uuid4().hex}"
        db.save_issued_question(issue_id, candidate_id, question)
        log_event("question_issued", source=question.get("source", "bank"), topic=question.get("topic"), mode=mode,
                  difficulty=question.get("difficulty"), ms=t.ms)
        issued = {"id": issue_id, "question": question}

    focus_options = generator.interview_focus_options(profile)
    return render_template(
        "practice.html",
        candidate_id=candidate_id,
        issue_id=issued["id"],
        question=_public_question(issued["question"]),
        mode=mode,
        choice=value,
        technical_topics=generator.technical_topics(),
        focus_options=focus_options,
        focus_label=generator.resolve_focus(profile, value)["label"] if mode == "interview" else value,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/practice/<int:candidate_id>/skip", methods=["POST"])
@login_required
def skip_question(candidate_id):
    issued = db.get_issued_question(request.form.get("issue_id", ""))
    if issued and issued["candidate_id"] == candidate_id:
        db.close_issued_question(issued["id"], "skipped")
        log_event("question_skipped", topic=issued["question"].get("topic"))
    return redirect(url_for("practice", candidate_id=candidate_id))


@app.route("/practice/<int:candidate_id>/submit", methods=["POST"])
@login_required
def submit_answer(candidate_id):
    answer_text = request.form.get("answer_text", "")
    issued = db.get_issued_question(request.form.get("issue_id", ""))
    # The question (with its answer key / rubric) always comes from the server-side store.
    if not issued or issued["candidate_id"] != candidate_id:
        flash("That question could not be found. Here's a new one.", "error")
        return redirect(url_for("practice", candidate_id=candidate_id))
    if not db.close_issued_question(issued["id"], "answered"):
        flash("You've already answered that question.", "error")
        return redirect(url_for("practice", candidate_id=candidate_id))
    question = issued["question"]

    with Timer() as t:
        result = evaluator.evaluate_answer_detailed(question, answer_text)
    score, feedback = result["score"], result["feedback"]
    log_event("answer_evaluated", topic=question.get("topic"), type=question.get("type"), source=question.get("source", "bank"),
              difficulty=question.get("difficulty"), score=score, method=result.get("method"),
              answer_words=len(answer_text.split()), ms=t.ms, valid=0 <= float(score) <= 100)
    db.save_attempt(candidate_id, question.get("id", issued["id"]), question["topic"], answer_text, score, feedback,
                    difficulty=question.get("difficulty"))

    return render_template(
        "result.html",
        candidate_id=candidate_id,
        question=question,
        answer_text=answer_text,
        score=score,
        feedback=feedback,
        evaluation=result,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/questions/generate", methods=["POST"])
def generate_question_api():
    payload = _json_object()
    if payload is None:
        return jsonify({"error": "A JSON object is required."}), 400
    candidate_id = payload.get("candidate_id")
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    # The prompt is built from the profile stored on the server (already ownership-checked by
    # the access guard), never from profile text sent by the client.
    candidate = db.get_candidate(int(candidate_id))
    profile = json.loads(candidate["profile_json"])
    weak_topics = [str(t)[:60] for t in _json_list(payload, "weak_topics")[:10] if isinstance(t, str)]
    answered_ids = [str(i)[:80] for i in _json_list(payload, "answered_ids")[:500] if isinstance(i, (str, int))]
    question = generator.pick_next_question(profile.get("skills") or [], weak_topics, set(answered_ids), profile=profile)
    if question is None:
        return jsonify({"error": "No question available."}), 404
    public = _public_question(question)
    public["issue_id"] = f"iq-{uuid.uuid4().hex}"  # stored so it's graded without trusting the client
    db.save_issued_question(public["issue_id"], int(candidate_id), question)
    return jsonify(public)


@app.route("/questions/evaluate", methods=["POST"])
def evaluate_question_api():
    payload = _json_object()
    question = (payload or {}).get("question")
    answer_text = (payload or {}).get("answer_text") or ""
    if not isinstance(question, dict) or not isinstance(answer_text, str):
        return jsonify({"error": "Send {\"question\": {...}, \"answer_text\": \"...\"}."}), 400
    question = {"type": str(question.get("type") or "short_answer")[:20], "prompt": str(question.get("prompt") or "")[:1000],
                "difficulty": str(question.get("difficulty") or "medium")[:20],
                "answer": str(question.get("answer") or "")[:500],
                "keywords": [str(k)[:80] for k in _json_list(question, "keywords")[:15]]}
    answer_text = answer_text[:4000]
    score, feedback = evaluator.evaluate_answer(question, answer_text)
    return jsonify({
        "score": score,
        "feedback": feedback,
        "strengths": ["Clear explanation", "Good project context"] if score >= 70 else ["Need more depth"],
        "weaknesses": ["Could be more specific"] if score < 70 else [],
        "improved_answer": answer_text,
    })


def code_job(view):
    """One running code/generation job per user and a small global cap (see JobSlots)."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        key = f"u{current_user.id}" if current_user.is_authenticated else (request.remote_addr or "?")
        refused = code_jobs.try_acquire(key)
        if refused:
            message = ("Your previous run is still in progress - wait for it to finish." if refused == "user"
                       else "The code runner is busy right now. Please try again in a few seconds.")
            log_event("code_job_refused", endpoint=request.endpoint, reason=refused)
            if _wants_json() or request.endpoint in ("run_dsa",):
                return jsonify({"error": message}), 429
            flash(message, "error")
            if "candidate_id" in kwargs:
                return redirect(url_for("dsa_practice", candidate_id=kwargs["candidate_id"]))
            return redirect(url_for("home"))
        try:
            return view(*args, **kwargs)
        finally:
            code_jobs.release(key)
    return wrapper


@app.route("/dsa/<int:candidate_id>")
@login_required
def dsa_practice(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))
    return render_template(
        "dsa_practice.html",
        candidate_id=candidate_id,
        problem=None,
        dsa_performance=db.get_dsa_performance(candidate_id),
        candidate_id_for_nav=candidate_id,
    )


@app.route("/dsa/<int:candidate_id>/generate", methods=["POST"])
@login_required
@code_job
def generate_dsa(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    profile = json.loads(candidate["profile_json"])
    difficulty = (request.form.get("difficulty") or "medium").lower()
    topic = (request.form.get("topic") or "arrays").lower()
    language = request.form.get("language") or "Python"
    previous_hashes = db.get_recent_coding_hashes(candidate_id, topic, difficulty)
    problem = generate_dsa_problem(profile, difficulty, topic, language, previous_hashes=previous_hashes)
    if not validate_problem_schema(problem):
        flash("The generated problem failed validation. Please try again.")
        return redirect(url_for("dsa_practice", candidate_id=candidate_id))
    db.save_coding_problem(problem["id"], candidate_id, problem)
    problem_for_view = public_problem(problem)
    return render_template(
        "dsa_practice.html",
        candidate_id=candidate_id,
        problem=problem_for_view,
        dsa_performance=db.get_dsa_performance(candidate_id),
        candidate_id_for_nav=candidate_id,
    )


def _owned_by_user(candidate_id) -> bool:
    candidate = db.get_candidate(int(candidate_id)) if candidate_id is not None else None
    return bool(candidate and candidate["user_id"] == current_user.id)


def _stored_problem_for_user(problem_id):
    stored = db.get_coding_problem(problem_id) if problem_id else None
    return stored["problem"] if stored and _owned_by_user(stored["candidate_id"]) else None


def _stored_problem(problem_id: str, candidate_id: int):
    stored = db.get_coding_problem(problem_id)
    if not stored or stored["candidate_id"] != candidate_id:
        return None
    return stored["problem"]


@app.route("/dsa/<int:candidate_id>/run", methods=["POST"])
@code_job
def run_dsa(candidate_id):
    problem_id = request.form.get("problem_id")
    problem = _stored_problem(problem_id, candidate_id) if problem_id else None
    if not problem:
        return jsonify({"error": "Problem not found."}), 404
    with Timer() as t:
        result = run_candidate_code(problem, request.form.get("code", ""))
    log_event("code_run", topic=problem.get("topic"), difficulty=problem.get("difficulty"), status=result.get("status"),
              passed=result.get("passed_tests"), total=result.get("total_tests"), ms=t.ms)
    return jsonify(result)


@app.route("/dsa/<int:candidate_id>/submit", methods=["POST"])
@code_job
def submit_dsa(candidate_id):
    problem_id = request.form.get("problem_id")
    problem = _stored_problem(problem_id, candidate_id) if problem_id else None
    if not problem:
        flash("That coding problem could not be found.")
        return redirect(url_for("dsa_practice", candidate_id=candidate_id))
    with Timer() as t:
        result = evaluate_submission(problem, request.form.get("code", ""))
    log_event("code_submitted", topic=problem.get("topic"), difficulty=problem.get("difficulty"), status=result.get("status"),
              passed=result.get("passed_tests"), total=result.get("total_tests"), score=result.get("coding_score"), ms=t.ms)
    if result.get("status") == "unavailable":  # nothing was executed: don't record a zero score
        flash(result.get("message"), "error")
        view = dict(public_problem(problem), starter_code=request.form.get("code", ""))  # keep their code
        return render_template("dsa_practice.html", candidate_id=candidate_id, problem=view,
                               dsa_performance=db.get_dsa_performance(candidate_id), candidate_id_for_nav=candidate_id), 503
    db.save_coding_submission(
        candidate_id,
        problem_id,
        request.form.get("code", ""),
        result.get("passed_tests", 0),
        result.get("total_tests", 0),
        result.get("coding_score", 0),
        result.get("execution_time", 0),
        result.get("memory_usage", 0),
        result.get("status", "incorrect"),
        result.get("feedback", ""),
    )
    return render_template(
        "dsa_result.html",
        candidate_id=candidate_id,
        problem=problem,
        result=result,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/coding/problems/generate", methods=["POST"])
@code_job
def generate_coding_problem_api():
    payload = _json_object() or {}
    candidate_id = payload.get("candidate_id")
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    candidate_id = int(candidate_id)
    profile = json.loads(db.get_candidate(candidate_id)["profile_json"])  # server copy, not client text
    difficulty = str(payload.get("difficulty") or "medium").lower()[:20]
    topic = str(payload.get("topic") or "arrays").lower()[:40]
    language = str(payload.get("language") or profile.get("preferred_language") or "python").lower()[:20]
    previous_hashes = db.get_recent_coding_hashes(candidate_id, topic, difficulty)
    problem = generate_dsa_problem(profile=profile, difficulty=difficulty, topic=topic, language=language, previous_hashes=previous_hashes)
    if not validate_problem_schema(problem):
        return jsonify({"error": "Generated problem failed validation."}), 400
    db.save_coding_problem(problem["id"], candidate_id, problem)
    public = public_problem(problem)
    return jsonify({"problem": public, "problem_id": problem["id"]})


@app.route("/coding/run", methods=["POST"])
@login_required
@code_job
def run_coding_api():
    payload = _json_object() or {}
    problem_id, code = payload.get("problem_id"), payload.get("code") or ""
    if not isinstance(code, str):
        return jsonify({"error": "code must be a string."}), 400
    problem = _stored_problem_for_user(problem_id) if isinstance(problem_id, str) else None
    if not problem:
        return jsonify({"error": "Problem not found."}), 404
    return jsonify(run_candidate_code(problem, code))


@app.route("/coding/submit", methods=["POST"])
@login_required
@code_job
def submit_coding_api():
    payload = _json_object() or {}
    problem_id, code = payload.get("problem_id"), payload.get("code") or ""
    if not isinstance(code, str):
        return jsonify({"error": "code must be a string."}), 400
    stored = db.get_coding_problem(problem_id) if isinstance(problem_id, str) and problem_id else None
    if not stored or not _owned_by_user(stored["candidate_id"]):
        return jsonify({"error": "Problem not found."}), 404
    candidate_id, problem = stored["candidate_id"], stored["problem"]  # never trust tests sent by the client
    result = evaluate_submission(problem, code)
    if result.get("status") == "unavailable":
        return jsonify(result), 503
    if problem_id:
        db.save_coding_submission(candidate_id, problem_id, code, result.get("passed_tests", 0), result.get("total_tests", 0), result.get("coding_score", 0), result.get("execution_time", 0), result.get("memory_usage", 0), result.get("status", "incorrect"), result.get("feedback", ""))
    return jsonify(result)


@app.route("/performance")
def performance_api():
    candidate_id = request.args.get("candidate_id", type=int)
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    skill_profiles = _skill_profiles(attempts, dsa_performance)
    return jsonify({
        "candidate_id": candidate_id,
        "overall_score": analytics.overall_proficiency(skill_profiles),
        "topic_scores": {topic: p["score"] for topic, p in skill_profiles.items()},
        "skill_profiles": skill_profiles,
        "attempt_count": len(attempts),
    })


@app.route("/skill-gaps")
def skill_gaps_api():
    candidate_id = request.args.get("candidate_id", type=int)
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    skill_profiles = _skill_profiles(attempts, dsa_performance)
    topic_scores = {topic: p["score"] for topic, p in skill_profiles.items()}
    weak_topics = analytics.weak_topics_from_profiles(skill_profiles)
    strong_topics = analytics.strong_topics_from_profiles(skill_profiles)
    recommendations = analytics.recommend_from_profiles(skill_profiles)
    return jsonify({
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "recommended_learning": recommendations,
        "topic_scores": topic_scores,
    })


@app.errorhandler(404)
def _not_found(_error):
    if _wants_json():
        return jsonify({"error": "Not found."}), 404
    return render_template("error.html", code=404, title="Page not found",
                           message="That page doesn't exist or has moved."), 404


@app.errorhandler(413)
def _too_large(_error):
    message = "That file is too large. Resumes must be under 5 MB."
    if _wants_json():
        return jsonify({"error": message}), 413
    flash(message, "error")
    return redirect(url_for("home"))


@app.errorhandler(500)
def _server_error(_error):
    # Details go to the server log only; the browser gets a generic page (no stack traces).
    if _wants_json():
        return jsonify({"error": "Something went wrong."}), 500
    return render_template("error.html", code=500, title="Something went wrong",
                           message="An unexpected error occurred. Please try again."), 500


if __name__ == "__main__":
    # The interactive debugger allows running code from the browser, so it is off unless
    # you explicitly set FLASK_DEBUG=1 on your own machine. Never enable it on a server.
    debug = os.getenv("FLASK_DEBUG") == "1"
    app.run(debug=debug, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")))
