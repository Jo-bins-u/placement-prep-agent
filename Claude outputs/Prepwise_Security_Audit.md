# Prepwise (placement-prep-agent): Security Audit Report

**Scope:** the full repository at branch `fix/frontend-bugs` (Flask app, templates, services, modules, validation, tests, config/scripts), plus the project zip that was supplied.
**Method:** static review of every route and security-relevant module; secret scanning of the working tree and of the full git history (4 commits in the original repo); dependency manifest review.
**Constraints:** no code was changed, and nothing destructive was run.

**Secrets:** every secret value is **REDACTED**. Findings name only the file and the key.

**Confidence labels:**

- **Confirmed:** verified from the code or the repository.
- **Likely:** strong static evidence, but the exploit depends on the environment.
- **Potential:** needs runtime verification.
- **Hardening:** a best-practice gap with no direct exploit path.

---

## 1. Executive Summary

Prepwise has a sound core:

- bcrypt password hashing;
- parameterised SQL everywhere;
- HMAC-hashed, single-use OTPs with expiry and attempt limits;
- a central ownership guard that closes the earlier IDOR;
- server-side storage of questions and test cases, so clients cannot choose their own grading data.

The serious risks are at the **edges**: code execution, secrets, file handling, and abuse controls.

1. **Any registered user can run arbitrary code on the host machine.** When Docker isn't running (the default on your Windows PC), submitted DSA code executes as a normal local Python process. It can read `.env` (Groq key, database URL, Gmail app password), the database, and every uploaded resume.
2. **`SECRET_KEY` is not set in `.env`, so the hardcoded fallback key is live.** Anyone who has read the source can forge a Flask session cookie and log in as any user.
3. **The public `/upload` endpoint writes files using the client-supplied filename.** An unauthenticated request can write `.pdf`/`.docx` files outside `uploads/`, or overwrite other users' resumes.
4. **The OTP checks can be raced and nothing is rate limited.** This makes password-reset brute force practical in principle, which means account takeover.
5. **`app.run(debug=True)`** enables the Werkzeug debugger whenever the app is started with `python app.py` (the path `start.ps1` uses).
6. **Live credentials and real people's resumes were packaged in the project zip.** The `.env` file, `uploads/` (5 real resumes) and `data/app.db` were all included. Git history is clean: `.env` was never committed.

**Overall risk:** high for any deployment beyond a single developer's laptop. Most fixes are small and local (config, a few lines per route, two libraries).

---

## 2. Critical Findings (full detail)

### C-01: Unsandboxed execution of user-submitted code on the host

| Field | Value |
|---|---|
| Severity | **Critical** |
| Confidence | **Confirmed** |
| Category | Remote Code Execution / Sandbox escape (OWASP A04, A05) |
| File | `modules/coding/runner.py` |
| Location | `_run_case()` (lines ~36–66), `_docker_command()` (~84–97) |
| Endpoints | `POST /dsa/<id>/run`, `POST /dsa/<id>/submit`, `POST /coding/run`, `POST /coding/submit`; also internally `verify_llm_problem()` in `problem_generator.py` |

**Description:** Submitted code is written into a harness file and executed.

- If `docker info` succeeds, it runs in a well-restricted container: no network, read-only, all capabilities dropped, non-root, memory and PID limits.
- Otherwise it falls back to `subprocess.run([sys.executable, script])` on the host, with a 3-second timeout and a minimal `PATH`. There is no filesystem, network, memory or process isolation.
- `PREPWISE_SANDBOX=local` forces this path, and the test config sets it.

On Windows without Docker Desktop running, **every run is on the host**.

**Why it's vulnerable:** The only barriers are "be logged in" and "have a candidate profile". Registration is self-service: you only need to verify an email address you control.

**Attack scenario:**

1. The attacker registers and uploads any resume.
2. They open DSA practice and submit code that calls `open()` on the project's `.env` or `data/app.db`, or uses `os`, `subprocess` or `socket`.
3. The code runs as the Flask process user. It can exfiltrate secrets over the network (not blocked locally), spawn a background process that survives the timeout, or modify the application's files.

**Impact:**

- Full compromise of the host and the application.
- Theft of the Groq API key, database credentials, the Gmail app password (usable to send mail as you) and every user's resume PII.

**Evidence:** In `_run_case`, the host branch is `subprocess.run([sys.executable, script_path], ..., timeout=timeout, env={"PATH": ...})`. The `docker run ... --network none --read-only --cap-drop ALL ...` branch applies only when the daemon responds.

**Recommended fix:**

1. Never fall back silently. If no sandbox is available, **refuse to run code** (return "Code runner unavailable"), and allow a local run only when an explicit `PREPWISE_ALLOW_UNSAFE_LOCAL_RUNNER=1` is set for development.
2. In production, use the Docker path, or a dedicated execution service (Judge0 or piston) on a separate host.
3. In the Docker path, add `--name` plus a `docker kill` on timeout (see L-07), and pin the image by digest.

**Priority:** Phase 1 (immediate).

---

### C-02: Hardcoded fallback `SECRET_KEY` is active, enabling session forgery

| Field | Value |
|---|---|
| Severity | **Critical** |
| Confidence | **Confirmed** (key name absent from `.env`; fallback literal present in code) |
| Category | Cryptographic failure / Broken authentication (OWASP A02, A07) |
| File | `app.py` line 42; `auth.py` `_secret()` line ~78 |
| Endpoint | All authenticated routes |

**Description:** The code uses `app.secret_key = os.getenv("SECRET_KEY") or "<hardcoded literal>"`. The `.env` defines GROQ_API_KEY, DATABASE_URL, MAIL_USERNAME, MAIL_PASSWORD, MAIL_SERVER, MAIL_PORT and EMAIL_FROM, but **no `SECRET_KEY`**. The public fallback string therefore signs every session cookie. The same fallback is the HMAC key for OTP hashes.

**Why it's vulnerable:** Flask sessions are client-side cookies signed with this key. Flask-Login trusts `session["_user_id"]`.

**Attack scenario:** An attacker reads the literal from the source (the repo is on GitHub). They use `itsdangerous` or `flask-unsign` to sign `{"_user_id": "1", "_fresh": true}` and set it as the `session` cookie. They are now logged in as user 1, or as any user id, which are sequential integers. No password or OTP is needed.

**Impact:**

- Complete authentication bypass for every account.
- Anyone who obtains a DB dump can brute-force OTP HMACs offline (low value, since codes expire in 10 minutes).

**Evidence:** `app.py:42` and `auth.py:78` both read `os.getenv("SECRET_KEY") or "dev-secret-…"` (literal truncated here). `SECRET_KEY` is absent from the `.env` key list.

**Recommended fix:**

1. Generate a key with `python -c "import secrets; print(secrets.token_urlsafe(64))"` and put it in `.env` as `SECRET_KEY`.
2. Remove the fallback. At startup, fail if `SECRET_KEY` is missing or shorter than 32 bytes. A dev-only random key can be allowed when `FLASK_ENV=development`.
3. Consider a separate `OTP_HMAC_KEY` so the two uses are independent.

Changing the key logs everyone out once, which is expected.

**Priority:** Phase 1 (immediate).

---

### H-01: Path traversal / arbitrary file write in public `/upload`

| Field | Value |
|---|---|
| Severity | **High** |
| Confidence | **Confirmed** (static; `pathlib` join semantics) |
| Category | Path traversal / Unrestricted file upload (OWASP A01, A04) |
| File | `app.py` `upload()` lines 506–532 |
| Endpoint | `POST /upload` (**unauthenticated**, listed in `PUBLIC_ENDPOINTS`) |

**Description:** The code does `save_path = UPLOAD_DIR / file.filename` and then `file.save(save_path)`. Werkzeug's `FileStorage.filename` is the raw client-supplied value. Browsers strip directories from it, but `curl` or a script does not. The only check is that the name ends in `.pdf` or `.docx`.

**Attack scenario:**

- `filename="../static/x.pdf"` writes attacker content into `static/`, served from your origin at `/static/x.pdf`.
- `filename="../sample_resume.pdf"` overwrites project files.
- An absolute name such as `/tmp/x.pdf` or `C:\...\x.pdf` makes `pathlib` **discard** `UPLOAD_DIR` entirely.
- `filename="resume.pdf"` silently overwrites another visitor's resume that had the same name.

The file is saved **before** parsing. A malformed file raises during parsing (a 500 error, which debug mode turns into a debugger page), but the file stays on disk.

**Impact:** Write/overwrite of any `.pdf`/`.docx` path the process can reach, hosting of attacker-controlled files on your domain, and loss or tampering of users' resumes. None of this requires authentication.

**Recommended fix:**

1. Never use the client name for storage. Use `stored = UPLOAD_DIR / f"{uuid4().hex}{ext}"`, and keep `secure_filename(file.filename)` only as display metadata.
2. Also verify magic bytes (`%PDF-`, or a ZIP header for `.docx`).
3. Set `MAX_CONTENT_LENGTH`.
4. Delete the file after parsing unless it is needed.
5. `reupload_resume` already uses `Path(...).name`. Switch it to a UUID name for consistency.

**Priority:** Phase 1.

---

### H-02: OTP brute force via race condition plus no rate limiting → account takeover through password reset

| Field | Value |
|---|---|
| Severity | **High** |
| Confidence | **Likely** (the race needs runtime verification; missing rate limits are Confirmed) |
| Category | Broken authentication (OWASP A07) |
| File | `auth.py` `verify_otp()` ~152–176; `database.py` `store_otp()` / `increment_otp_attempts()`; `app.py` `reset_password()`, `forgot_password()`, `resend_code()` |
| Endpoints | `POST /forgot-password`, `POST /reset-password`, `POST /resend-code`, `POST /verify-email` |

**Description:** `verify_otp` reads `otp_attempts`, compares the code, and *then* increments the counter in a separate statement. There is no row lock or atomic `UPDATE … WHERE otp_attempts < 5 RETURNING`. Parallel requests all see the same attempt count, so a burst of N concurrent guesses gets N comparisons instead of 5. Each new code also resets attempts to 0 (`store_otp`), and new codes can be requested every 60 seconds.

**Attack scenario:**

1. The attacker requests a reset for victim@x.com.
2. They fire ~200 concurrent `POST /reset-password` requests with different 6-digit codes and a password of their choice.
3. They repeat every 60 seconds with a fresh code.

Even without the race, 5 guesses per minute is about 7,200 guesses per day against a 10⁶ space, which is roughly a 0.7% chance of success per victim per day. With the race it grows by orders of magnitude.

**Impact:** Takeover of any account whose email is known. A successful reset also marks the account as verified.

**Recommended fix:**

1. Make the attempt check atomic:

   ```sql
   UPDATE app_users SET otp_attempts = otp_attempts + 1
   WHERE id = %s AND otp_attempts < 5 RETURNING otp_code, otp_expires_at
   ```

   Compare only when a row is returned.
2. Add Flask-Limiter: per IP and per email on `/login`, `/reset-password`, `/verify-email`, `/resend-code`, `/forgot-password`, `/register`.
3. Cap the number of codes per account per hour (for example 5), and invalidate on too many failed codes.

**Priority:** Phase 1.

---

### H-03: Werkzeug debugger enabled (`debug=True`)

| Field | Value |
|---|---|
| Severity | **High** (Critical if the port is ever exposed) |
| Confidence | **Confirmed** config; exposure is **Potential** |
| Category | Security misconfiguration (OWASP A05) |
| File | `app.py` line 1087 `app.run(debug=True, port=5000)`; `start.ps1` / `start.bat` run `python app.py` |

**Description:** Any unhandled exception renders the interactive debugger. That includes the parser errors H-01 can trigger. The debugger is PIN-protected, but the PIN is derivable from machine data an attacker can obtain through file-read bugs or C-01. It also discloses source code, stack traces and local variables, including config values.

The default bind is 127.0.0.1. However, running with `--host 0.0.0.0`, putting it behind a tunnel (ngrok) or deploying with `python app.py` makes it reachable.

**Attack scenario:** Trigger a 500 on `/upload` with a corrupt PDF. The response shows the traceback, and possibly a console.

**Recommended fix:** Use `app.run(debug=os.getenv("FLASK_DEBUG") == "1")`. In production, run gunicorn/waitress, not `app.run`. Add generic 404/500 error handlers.

**Priority:** Phase 1.

---

## 3. Findings Table

| ID | Title | Severity | Confidence | Category | Location |
|---|---|---|---|---|---|
| C-01 | Unsandboxed host execution of user code | Critical | Confirmed | RCE | `modules/coding/runner.py` `_run_case` |
| C-02 | Hardcoded fallback SECRET_KEY active → session forgery | Critical | Confirmed | Crypto / AuthN | `app.py:42`, `auth.py:78` |
| H-01 | Path traversal / arbitrary write in public upload | High | Confirmed | File upload | `app.py` `upload()` |
| H-02 | OTP race + no rate limit → reset takeover | High | Likely | AuthN | `auth.py` `verify_otp`, reset routes |
| H-03 | Werkzeug debugger enabled | High | Confirmed (exposure Potential) | Misconfig | `app.py:1087` |
| M-01 | No rate limiting anywhere (login, register, email send, LLM, code run) | Medium | Confirmed | Abuse / DoS | all routes |
| M-02 | No CSRF protection on form POSTs | Medium | Likely (browser-dependent) | CSRF | all HTML forms |
| M-03 | Sessions not revoked after password reset/change | Medium | Confirmed | Session mgmt | `reset_password`, `change_password` |
| M-04 | Live credentials in `.env` were distributed in the project zip | Medium | Confirmed | Secrets | `.env` (keys: GROQ_API_KEY, DATABASE_URL, MAIL_USERNAME, MAIL_PASSWORD) |
| M-05 | Real resumes + user DB distributed in zip | Medium | Confirmed | Data exposure | `uploads/` (5 PDFs), `data/app.db` |
| M-06 | Resume PII stored in client-readable session cookie | Medium | Confirmed | Info disclosure | `app.py` `upload()` → `session["pending_profile"]` |
| M-07 | Unbounded uploads/parsing: no size limit, disk fill, parser DoS | Medium | Confirmed | DoS | `upload()`, `extract_text.py` |
| M-08 | LLM cost abuse via unthrottled AI endpoints | Medium | Confirmed | AI / Abuse | `/questions/evaluate`, `/coding/problems/generate`, `/dsa/<id>/generate`, `/practice` |
| M-09 | Prompt injection can steer LLM reference code that the server executes | Medium | Likely | AI → RCE chain | `problem_generator.verify_llm_problem`, `/coding/problems/generate` |
| M-10 | Missing security headers & cookie hardening | Medium | Confirmed | Misconfig | app-wide |
| M-11 | Account/email enumeration | Medium | Confirmed | AuthN | `register`, `verify_email`, `resend_code`, `login` timing |
| L-01 | Unverified-account password overwrite (pre-verification hijack) | Low | Confirmed | AuthN | `register()` |
| L-02 | OTP codes printed to console; emails in logs | Low | Confirmed | Logging / PII | `auth.send_otp_email`, `auth.py` logs |
| L-03 | Unpinned dependencies (CVE status needs verification) | Low | Confirmed (unpinned) / Potential (CVEs) | Supply chain | `requirements.txt` |
| L-04 | `joblib.load` (pickle) of model files | Low | Potential | Insecure deserialisation | `modules/evaluation/ml_adapter.py:56,60` |
| L-05 | `/api/profile` PUT stores arbitrary, unbounded JSON | Low | Confirmed | Mass assignment | `app.py` `profile_api` |
| L-06 | DB TLS not enforced | Low | Potential | Transport | `database.py` `DB_CONFIG` |
| L-07 | Docker sandbox: container outlives timeout; image tag unpinned | Low | Potential | Sandbox / DoS | `runner.py` docker branch |
| L-08 | Logout via GET (CSRF logout) | Low | Confirmed | CSRF | `app.py` `/logout` |
| L-09 | Weak password policy, no breached-password check | Low | Confirmed | AuthN | `auth.password_problem` |
| L-10 | Grader prompt injection for answers ≥12 words (own score only) | Low | Likely | AI integrity | `evaluator.py` guard, `llm_service.grade_answer` |
| L-11 | Default/example DB credentials in scripts (placeholder, localhost) | Low | Confirmed | Config | `start.ps1:20`, `.env.example:8`, `README.md:37` |
| I-01 | No deployment config (Dockerfile, gunicorn conf, CI) to review | Info | n/a | Deployment | repo |

---

## 4. Attack Surface Overview

### Endpoint inventory

| Endpoint | Method | Auth | Ownership check | Notes |
|---|---|---|---|---|
| `/` | GET | Public | n/a | landing |
| `/upload` | POST | **Public** | n/a | H-01, M-06, M-07 |
| `/register` | GET/POST | Public | n/a | sends email; M-11, L-01 |
| `/verify-email` | GET/POST | Public | by email | H-02 |
| `/resend-code` | POST | Public | by email | sends email; M-01 |
| `/login` | GET/POST | Public | n/a | no lockout; M-01 |
| `/forgot-password` | GET/POST | Public | n/a | sends email; generic message ✔ |
| `/reset-password` | GET/POST | Public | OTP | H-02 |
| `/account/password` | GET/POST | Login | self | requires current password ✔ |
| `/logout` | GET | Login | self | L-08 |
| `/verify-profile/<id>` | GET/POST | Login | guard ✔ | CSRF (M-02) |
| `/profile/<id>/reupload` | POST | Login | guard ✔ | M-07 |
| `/dashboard/<id>`, `/api/dashboard/<id>` | GET | Login | guard ✔ | |
| `/api/profile/<id>` | GET/PUT | Login | guard ✔ | L-05 |
| `/api/resume-feedback/<id>` | GET | Login | guard ✔ | |
| `/practice/<id>` (+`/skip`, `/submit`) | GET/POST | Login | guard ✔ | server-side question ✔ |
| `/questions/generate` | POST | Login | guard ✔ | client-supplied profile → LLM |
| `/questions/evaluate` | POST | Login | none needed | LLM per call; M-08 |
| `/dsa/<id>` (+`/generate`, `/run`, `/submit`) | GET/POST | Login | guard ✔ | **C-01** |
| `/coding/problems/generate` | POST | Login | guard ✔ | M-08, M-09 |
| `/coding/run`, `/coding/submit` | POST | Login | stored-problem owner ✔ | **C-01** |
| `/performance`, `/skill-gaps` | GET | Login | guard ✔ | |
| `/static/*` | GET | Public | n/a | H-01 can write here |

### Trust boundaries

- Browser → Flask (cookie session).
- Flask → PostgreSQL/SQLite.
- Flask → Groq API (profile/resume text and answers leave your system).
- Flask → Gmail SMTP.
- Flask → **code runner (host process or Docker)**.
- Flask → filesystem (`uploads/`, `logs/`).

### Files that handle untrusted input

- `app.py` (all routes)
- `extract_text.py`, which parses PDF/DOCX
- `modules/profile_parsing/parser.py`
- `modules/coding/runner.py`
- `services/llm_service.py`
- `modules/evaluation/evaluator.py`

---

## 5. Authentication Findings

- **C-02:** forged sessions via the fallback key.
- **H-02:** the OTP race, plus no rate limits.
- **M-03:** sessions survive a password reset. Flask cookie sessions are stateless, and Flask-Login has no session version or token. After a victim resets their password, an attacker who already holds a valid session cookie stays logged in. **Fix:** store `session_version` (or the password-hash fingerprint) on the user, embed it in `get_id()` or check it in `user_loader`, and bump it on password reset/change.
- **M-11:** enumeration. The system reveals whether an account exists in four places:
  - `/register` says "An account with this email already exists".
  - `/verify-email` says "We couldn't find that account".
  - `/resend-code` (verify) says "Nothing to resend".
  - `/login` runs bcrypt only when the user exists, which is a *timing* oracle (Likely).

  **Fix:** return generic messages, and run a dummy bcrypt check when the user is missing.
- **L-01:** `register()` overwrites the password of an existing *unverified* account. An attacker can pre-register a victim's email and reset its password repeatedly. The impact is low, because verification still needs the inbox.
- **L-09:** the policy is 8 characters with a letter and a digit. Consider 10 or more characters and a breached-password check (the HIBP k-anonymity API).
- ✔ bcrypt, `compare_digest`, single-use OTP, 10-minute TTL, 60 s resend cooldown, generic forgot-password message, current password required for change, safe `next` redirect.

## 6. Authorization Findings

- ✔ The central `_access_guard` enforces login and candidate ownership for every non-public endpoint (URL, query, form or JSON `candidate_id`). DSA and coding endpoints look up the **stored** problem and check its owner. Question grading uses the server-side issued question. No IDOR was found in the current code.
- **L-05:** `PUT /api/profile/<id>` accepts any keys and any size (owner only). Store only whitelisted fields, and cap list lengths and string sizes.
- **Hardening:** the guard allows the endpoint if `request.endpoint` is `None`. That is safe today (the result is a 404), but add an explicit test that every registered route is either in `PUBLIC_ENDPOINTS` or guarded.

## 7. API Security Findings

- **M-01:** no rate limiting.
- **M-02:** no CSRF tokens.

  JSON APIs are effectively protected because `get_json(silent=True)` requires `Content-Type: application/json`, which triggers a CORS preflight, and there is no CORS configuration. **Form** endpoints are exposed if the browser doesn't apply SameSite=Lax by default (Safari, older browsers):

  - `/verify-profile/<id>` (profile edit)
  - `/profile/<id>/reupload`
  - `/practice/<id>/submit` and `/skip`
  - `/dsa/<id>/generate`, `/run`, `/submit`
  - `/login` (login CSRF)

  **Fix:** add Flask-WTF `CSRFProtect` and set `SESSION_COOKIE_SAMESITE="Lax"` explicitly.
- **M-07:** no `MAX_CONTENT_LENGTH`. Arbitrarily large bodies or files are read into memory or onto disk.
- **Info disclosure:** there are no custom 404/500 handlers, so with debug on (H-03) tracebacks leak. `/questions/evaluate` echoes the answer back as `improved_answer`. That is harmless but misleading.
- **CORS:** not configured, so the same-origin default applies. ✔

## 8. Dependency Findings

`requirements.txt` is **entirely unpinned**: flask, pdfplumber, python-docx, groq, python-dotenv, scikit-learn, joblib, pyarrow, psycopg[binary], flask-login, flask-mail, itsdangerous, gunicorn, bcrypt. Builds are not reproducible, and a compromised or broken future release would be installed automatically.

- **CVE status: requires verification.** I cannot determine installed versions from the repo alone, so I am not listing specific CVEs. Run `pip-audit -r requirements.txt` (or `pip-audit` inside `.venv`) to check.
- Packages historically worth watching:
  - **pdfminer.six/pdfplumber:** parser resource exhaustion on crafted PDFs.
  - **Werkzeug/Flask:** debugger and multipart parsing issues in older versions.
  - **joblib/scikit-learn:** pickle loading.
- `flask-mail` and `itsdangerous` appear unused directly (SMTP goes through `smtplib`). Remove unused packages.
- **Fix:** pin with `pip freeze > requirements.lock` or pip-tools, and add `pip-audit` to CI (Phase 2).

## 9. Secrets Findings

| File | Key(s) | Status |
|---|---|---|
| `.env` | GROQ_API_KEY, DATABASE_URL, MAIL_USERNAME, MAIL_PASSWORD, MAIL_SERVER, MAIL_PORT, EMAIL_FROM | **Real values present: REDACTED.** Correctly gitignored and **never committed** (all 4 commits in the original history checked; no Groq-format keys in any diff). **However, the file was included in the project zip** shared for this review (M-04). |
| `app.py:42`, `auth.py:78` | fallback secret literal | Hardcoded; active because `SECRET_KEY` is missing (C-02) |
| `start.ps1:20`, `.env.example:8`, `README.md:37` | DB URL with placeholder password (e.g. `postgres:<placeholder>@localhost`) | Placeholder only; localhost (L-11) |
| `data/app.db` (zip) | user emails + bcrypt hashes | Not in git; distributed in zip (M-05) |

**Recommendation (M-04):**

1. Treat the Gmail app password, Groq key and DB password as **exposed**, and rotate them. Revoke the app password in your Google account, regenerate the Groq key, and change the DB password.
2. In future, share the project with `git archive` or a zip that excludes `.env`, `.venv`, `data/`, `uploads/` and `logs/`.

## 10. Infrastructure Findings

- **I-01:** there is no Dockerfile, compose file, gunicorn config, reverse-proxy config or CI pipeline in the repo, so deployment security **cannot be assessed statically**. The only runtime entry points are `python app.py` (debug) via `start.ps1` / `start.bat`.
- **H-03:** debug mode.
- **L-06:** there is no `sslmode` in the psycopg connection. A remote DB (Supabase, Neon, RDS) defaults to `prefer`, which can be downgraded. Use `sslmode=require` (or `verify-full`) in `DATABASE_URL`.
- **L-07:** in the Docker runner, when `subprocess.run(timeout=3)` fires it kills the `docker` CLI, **not the container**. A `while True` submission keeps a container alive, limited only by `--cpus 0.5` and its memory cap (Potential; verify at runtime). `python:3.13-slim` is pulled by tag rather than digest.
- **Hardening:** the app writes `logs/app_metrics.jsonl` and `uploads/` with no retention or rotation.

## 11. AI Security Findings

- **M-08: cost abuse.** Each call to `/questions/evaluate`, `/coding/problems/generate`, `/dsa/<id>/generate` or `/practice` can trigger a Groq call, with no per-user quota. **Fix:** a per-user daily quota (a DB counter) plus Flask-Limiter; cache generated questions.
- **M-09: prompt injection → executed code (Likely).** `/coding/problems/generate` accepts a client-supplied `profile` (and resume text flows into prompts elsewhere). Injected text can ask the model to emit a `reference_solution` with a malicious payload. `verify_llm_problem()` *executes* that code through the same runner to validate it, so on the host path this is an indirect RCE. In Docker the sandbox contains it. **Fix:** fix C-01 first; build the prompt from the server-stored profile only; strip or limit the free-text profile fields sent to the LLM.
- **L-10: grader manipulation.** The injection guard falls back to rubric scoring when the AI score exceeds the rubric by more than 60 points *and* the answer has fewer than 12 words. A longer answer with embedded instructions can still inflate the user's **own** score. **Fix:** always cap the AI score at rubric + X, and add a canary instruction check.
- **Data privacy:** resume content and answers are sent to Groq (a third party). Add a privacy notice or consent, and send only needed fields.
- ✔ LLM output is schema-validated and length-limited; questions and problems are stored server-side; the grader delimits the answer as data.

## 12. Hardening Recommendations

### Security headers

| Header | Current | Recommended |
|---|---|---|
| Content-Security-Policy | ❌ missing | `default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` (move inline scripts to files, or use nonces) |
| Strict-Transport-Security | ❌ missing | `max-age=31536000; includeSubDomains` (HTTPS deployments only) |
| X-Frame-Options | ❌ missing | `DENY` (or CSP `frame-ancestors 'none'`) |
| X-Content-Type-Options | ❌ missing | `nosniff` |
| Referrer-Policy | ❌ missing | `strict-origin-when-cross-origin` |
| Permissions-Policy | ❌ missing | `camera=(), microphone=(), geolocation=()` |
| Cross-Origin-Opener-Policy | ❌ missing | `same-origin` |
| Session cookie `Secure` | ❌ not set | `SESSION_COOKIE_SECURE=True` (HTTPS) |
| Session cookie `HttpOnly` | ✔ Flask default | keep |
| Session cookie `SameSite` | ⚠ unset (browser default) | `Lax` explicitly |
| `MAX_CONTENT_LENGTH` | ❌ unset | 5 MB |

Flask-Talisman can apply most of these in one place.

### Other hardening

- Generic error pages.
- Log rotation.
- A retention job for `uploads/`.
- Pin the Docker image by digest.
- Run the app as a low-privilege OS user.
- Add `pip-audit` and `bandit` to CI.
- Add a route-coverage test for the access guard.

## 13. Positive Security Controls

- ✔ **bcrypt** password hashing; `check_password` handles malformed hashes.
- ✔ **Parameterised SQL** throughout `database.py`. The only f-string DDL uses internal constants. No SQL injection found.
- ✔ **OTP design:** CSPRNG codes, stored as an HMAC (never plaintext), `compare_digest`, single use, 10-minute expiry, 5-attempt lockout, 60 s resend cooldown, purpose-bound (verify vs reset).
- ✔ **Central access guard**, with ownership checks on every candidate-scoped request (the earlier IDOR is fixed); denials are logged.
- ✔ **Server-side question and problem storage.** Clients can't supply their own answer keys or test cases; issued questions are single-use.
- ✔ **Safe post-login redirect** (`_safe_next` blocks `//` and `\`).
- ✔ **Jinja autoescaping**; no `|safe` in templates. DSA output is escaped with `esc()` before `innerHTML`.
- ✔ **Docker sandbox flags** are strong when used: `--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, non-root user, memory and PID limits.
- ✔ **LLM output validation** (schema, lengths); LLM-generated problems are accepted only if their reference solution passes their own tests.
- ✔ **Secrets hygiene in git:** `.env`, `uploads/`, `*.db`, `logs/` and `reports/` are all gitignored; history is clean.
- ✔ **Test isolation:** tests use a temp SQLite DB and blank credentials, so they never touch real secrets or send mail.
- ✔ Enumeration-safe `/forgot-password` message.

## 14. OWASP Top 10 (2021) Mapping

| OWASP | Findings |
|---|---|
| A01 Broken Access Control | H-01, M-02, L-05, L-08 (IDOR ✔ fixed) |
| A02 Cryptographic Failures | C-02, L-06, M-06 |
| A03 Injection | M-09, L-10 (SQLi ✔ none; XSS ✔ none found) |
| A04 Insecure Design | C-01, H-02, M-07, M-08 |
| A05 Security Misconfiguration | H-03, M-10, I-01 |
| A06 Vulnerable & Outdated Components | L-03 (verification required) |
| A07 Identification & Authentication Failures | C-02, H-02, M-03, M-11, L-01, L-09 |
| A08 Software & Data Integrity Failures | L-04, L-07 (image not pinned), L-03 |
| A09 Logging & Monitoring Failures | L-02 (PII/OTP in logs); no alerting on repeated OTP failures |
| A10 SSRF | None found: no user-controlled outbound URLs |

## 15. Risk Summary (counts)

| Severity | Count |
|---|---|
| Critical | 2 |
| High | 3 |
| Medium | 11 |
| Low | 11 |
| Informational | 1 |

---

## 16. Remediation Plan

### Phase 1: Immediate (before anyone else uses the app)

1. **C-02:** add `SECRET_KEY` to `.env` and remove the fallback (fail fast if it is missing).
2. **C-01:** disable the unsandboxed local runner unless it is explicitly enabled for dev; require Docker (or a remote judge) otherwise.
3. **H-01:** store uploads under UUID names, validate magic bytes, set `MAX_CONTENT_LENGTH`.
4. **H-03:** drive debug from an env var; add generic error handlers.
5. **H-02:** make the OTP attempt counter atomic; add Flask-Limiter to the auth and OTP routes.
6. **M-04/M-05:** rotate the Gmail app password, Groq key and DB password; delete the shared zip copies containing `.env`, resumes and `app.db`.

### Phase 2: Short term (within a sprint)

7. **M-02:** add CSRFProtect; set explicit cookie flags (**M-10**); move `/logout` to POST (**L-08**).
8. **M-03:** revoke sessions on password change and reset via a session version.
9. **M-01/M-08:** add rate limits and per-user LLM quotas on the AI and code-run endpoints.
10. **M-06:** store the pending profile server-side (DB row plus opaque id) instead of in the cookie.
11. **M-11/L-01:** generic auth messages and a dummy bcrypt; stop overwriting unverified accounts' passwords.
12. **M-09:** build prompts from server-stored data only.
13. **L-03:** pin dependencies; run `pip-audit` and fix what it reports.
14. **L-02:** stop printing OTPs unless `FLASK_DEBUG=1`; mask emails in logs.

### Phase 3: Hardening

15. Security headers via Talisman (CSP with nonces).
16. Docker runner: kill the container on timeout, pin the image digest (**L-07**).
17. DB `sslmode=require` (**L-06**).
18. `/api/profile` field whitelist and size caps (**L-05**).
19. Model integrity: SHA-256 check before `joblib.load` (**L-04**).
20. Stronger password policy and a breached-password check (**L-09**); tighten the grader cap (**L-10**).
21. Upload and log retention jobs; CI with `pip-audit`, `bandit` and a route-guard coverage test; a production deployment config (gunicorn behind a TLS reverse proxy).

---

### Items that need runtime verification

- The actual concurrency gain of the H-02 race.
- Whether the Docker containers outlive the timeout (L-07).
- Dependency CVEs (L-03).
- How each browser's SameSite default affects CSRF (M-02).
- The login timing oracle (M-11).
- The actual deployment and network exposure (H-03, I-01).
