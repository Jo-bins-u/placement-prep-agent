# ⚡ Prepwise: AI Placement Preparation Agent

Prepwise is a web application that helps students prepare for campus placements.
A student uploads a resume. Prepwise turns it into a profile and then offers
three kinds of practice, all tied to that profile:

- **Interview** questions about the student's own projects, internships and skills, plus behavioural/HR questions.
- **Technical** concept questions across 11 core CS topics.
- **DSA** coding problems, run in a sandbox.

Every answer is scored with clear, point-by-point feedback. A dashboard tracks strengths and weak areas over time and links straight to targeted practice.

> **Team:** Joyal Binsu (M1) · Aiswarya K V (M2) · Nihal Gireesh (M3) · Pulikanti Gowtham Roy (M4, M5)
> **Guided by:** Prof. Chaitra P C

---

## Contents

1. [Features](#features)
2. [Modules and completion status](#modules-and-completion-status)
3. [Tech stack](#tech-stack)
4. [Prerequisites](#prerequisites)
5. [Setup and execution](#setup-and-execution)
6. [Configuration reference (`.env`)](#configuration-reference-env)
7. [Testing and validation](#testing-and-validation)
8. [Running in production](#running-in-production)
9. [Project structure](#project-structure)
10. [Security](#security)
11. [Troubleshooting](#troubleshooting)
12. [Future scope](#future-scope)

---

## Features

- **Resume parsing.**
  - Accepts PDF or DOCX files.
  - Extracts contact details, skills, education, projects and internships into a profile the student can review and edit.
  - Resume feedback scores each section and suggests improvements.
- **Interview mode.**
  - Personalised questions such as "Walk me through project X", "Why did you pick Flask?" and "What would break at 100× users?".
  - Also covers internship questions, skill-depth questions and STAR-style behavioural questions.
  - Focus options: *Mixed*, *Behavioral & HR*, *Skills on my resume*, or one specific project or internship.
- **Technical mode.**
  - Concept questions in 11 topics: Data Structures, Algorithms, Dynamic Programming, DBMS, Operating Systems, Computer Networks, OOP, System Design, Python, Machine Learning and Web Development.
  - Pick one topic, or choose *Recommended* to see weak areas first.
- **DSA mode.**
  - 57 verified coding problems with an in-browser editor.
  - *Run* checks your code against sample tests; *Submit* checks it against hidden tests.
  - Code runs in a locked-down Docker sandbox.
- **AI questions.**
  - With a Groq API key, questions come from Llama 3.3 70B and are personalised to the resume.
  - Every AI question is validated before it is shown.
  - Anything that fails validation falls back to the curated banks: 74 technical questions, 12 behavioural questions and resume templates.
- **Fair answer scoring.**
  - Each key point accepts synonyms, and small typos are tolerated.
  - A point mentioned but not explained gets partial credit.
  - The answer is also compared in meaning with a model answer, so a correct answer in the student's own words still scores well.
  - Anti-gaming checks catch buzzword lists, copies of the question's own wording, and instructions aimed at the grader.
  - An optional AI grader is blended with the rubric.
- **Feedback page.**
  - Each key point is marked covered ✓, partial ~ or missing ✗.
  - Shows "What you did well", "How to improve" and a model answer.
- **Analytics dashboard.**
  - Proficiency per topic uses a Bayesian-smoothed, recency-weighted score.
  - Shows focus areas, suggested practice with one-click links, DSA statistics and resume feedback.
- **Accounts.**
  - Email and password sign-up, verified with a 6-digit code.
  - Forgot, reset and change password.
  - A display name, used only for display.
- **UI.**
  - Responsive and card-based.
  - Lightning-bolt branding with an animated intro that respects the system's "reduce motion" setting.

---

## Modules and completion status

The project is split into five modules. All five are **implemented, integrated and tested**. The table shows what each covers. The checklist after it tracks the remaining project work.

| Module | Owner | Code | What it does | Status |
|---|---|---|---|---|
| **M1: Resume / Profile Parsing** | Joyal Binsu | `modules/profile_parsing/`, `services/safe_parse.py`, `services/resume_worker.py`, `services/profile_sanitize.py` | Reads text from PDF/DOCX. A rule-based parser plus a skills taxonomy extracts the profile. The Verify/Edit page and resume feedback build on it. Parsing runs in a sandboxed worker. | ✅ Complete (macro-F1 0.977) |
| **M2: Question Generation** | Aiswarya K V | `modules/question_generation/generator.py`, `services/llm_service.py`, `data/*.json`, `tools/build_*_bank.py` | Separate Interview and Technical modes with a topic/focus picker. Uses LLM questions with validation and falls back to the curated banks. Picks topics by weakness. | ✅ Complete |
| **M3: Evaluation & Feedback** | Nihal Gireesh | `modules/evaluation/evaluator.py`, `modules/evaluation/ml_adapter.py`, `services/llm_service.py` | Scores against a concept rubric (synonyms, typos, partial credit) and meaning similarity (TF-IDF), optionally blended with an AI grader. Includes anti-gaming checks and structured feedback. | ✅ Complete (94.7% band accuracy) |
| **M4: Analytics & Recommendation** | Pulikanti Gowtham Roy | `modules/analytics/analytics.py` | Computes Bayesian-smoothed, recency-weighted proficiency. Finds weak and strong topics, combines interview and DSA scores, and gives recommendations. | ✅ Complete |
| **M5: Dashboard, DSA & Integration** | Pulikanti Gowtham Roy | `app.py`, `templates/`, `static/`, `modules/coding/`, `modules/dsa_engine.py` | Covers the Flask app, dashboard and UI, and the DSA bank, generator and Docker judge. Also covers accounts and security hardening. | ✅ Complete (judge accuracy 100%) |

### Remaining work checklist

- [x] M1 through M5 implemented
- [x] Integration and end-to-end testing (184 automated tests)
- [x] Numeric validation suite (`python -m validation.run`)
- [x] Security audit and hardening (4 phases)
- [ ] **Final documentation**: project report and this README (in progress)
- [ ] **Demo preparation**: demo script, sample accounts and sample resumes (`sample_resume.pdf` / `.docx`)
- [ ] Deploy a demo instance behind HTTPS (see [Running in production](#running-in-production))
- [ ] Enable CI on GitHub: CI config is included (see [Testing and validation](#testing-and-validation))
- [ ] Short user trial with classmates to collect feedback

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask, Flask-Login, Jinja2 |
| Database | PostgreSQL (Supabase or local) via psycopg 3; SQLite fallback for local development |
| Resume parsing | pdfplumber, python-docx, rule-based parser + skills taxonomy |
| AI | Groq API: `llama-3.3-70b-versatile` (question generation and grading) |
| Scoring | Concept rubric + scikit-learn TF-IDF (char n-grams) + optional AI grader |
| Code execution | Docker sandbox (no network, read-only, non-root, CPU/memory/PID limits) |
| Auth | bcrypt, HMAC-hashed one-time codes, Gmail SMTP |
| Production server | waitress, behind an HTTPS reverse proxy (e.g. Caddy) |
| Frontend | Server-rendered HTML, CSS, small vanilla JavaScript |

---

## Prerequisites

| Requirement | Needed for | Notes |
|---|---|---|
| **Python 3.10 or newer** | everything | Tested on 3.11–3.13. On Windows, tick "Add Python to PATH" during install. |
| **Git** (optional) | cloning the repo | You can also download the ZIP. |
| **PostgreSQL database** (optional) | persistent multi-user data | A free [Supabase](https://supabase.com) project or a local PostgreSQL. Without one, a local SQLite file is used. |
| **Groq API key** (optional) | AI questions and AI grading | Free key from [console.groq.com](https://console.groq.com). Without it, the curated question banks and rubric scoring are used. |
| **Gmail account + App Password** (optional) | emailing verification codes | Needs 2-Step Verification enabled. Without it, codes can be printed in the console for local testing. |
| **Docker Desktop** (recommended) | DSA *Run* / *Submit* | Code only runs inside Docker by default. |

---

## Setup and execution

### Option A: Windows quick start (recommended)

1. Open **PowerShell** in the project folder. If PowerShell blocks the script, double-click `start.bat` instead, or run once:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
2. Start the app:
   ```powershell
   .\start.ps1
   ```
   You can also double-click `start.bat`. The script does the following:
   - creates a `.venv` virtual environment and installs `requirements.txt`;
   - copies `.env.example` to `.env` if there is no `.env` yet;
   - generates a strong `SECRET_KEY` into `.env`;
   - checks that Docker is running and pins the sandbox image;
   - starts the app.
3. The first time, stop the app with **Ctrl+C** and edit `.env` with your own values (see [Configure `.env`](#configure-env)). Then run `.\start.ps1` again.
4. Open **http://127.0.0.1:5000** in your browser.

### Option B: Manual setup (Windows, macOS, Linux)

```bash
# 1. Get the code
git clone <repository-url> placement-prep-agent
cd placement-prep-agent

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):  .\.venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create your configuration
cp .env.example .env          # Windows: copy .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env

# 5. Edit .env (next section), then run
python app.py
```

Open **http://127.0.0.1:5000**.

### Configure `.env`

Open `.env` in a text editor and replace the placeholders with **your own** values:

```dotenv
# Required: signs sessions and codes (start.ps1 fills this in for you)
SECRET_KEY=<long random string, 32+ characters>

# Database: pick ONE of the options below
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>?sslmode=require

# Optional: AI questions and grading
GROQ_API_KEY=<your Groq API key>

# Optional: email verification codes
MAIL_USERNAME=<your gmail address>
MAIL_PASSWORD=<16-character Gmail app password>
```

> ⚠️ **Never commit or share `.env`.** It holds your database password and API keys. It is listed in `.gitignore`. Share `.env.example` instead.

**Database options**

| Option | What to set | Notes |
|---|---|---|
| **Supabase (cloud)** | `DATABASE_URL` from *Project Settings → Database → Connection string* (use the **pooler** URI), with `?sslmode=require` | Remote databases must use TLS. If a remote DB is unreachable, the app stops with a clear message instead of silently using SQLite. |
| **Local PostgreSQL** | `DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db>` | Create the database first. Tables are created automatically on first start. |
| **SQLite (zero setup)** | Leave `DATABASE_URL` pointing at an unavailable local server, or remove it | Used automatically for local development. Data lives in a local file. |

**Email codes without Gmail (local testing only).** Remove or comment out the `MAIL_*` lines. Then add `PREPWISE_PRINT_OTP=1`, or `FLASK_DEBUG=1`, to `.env`. The 6-digit codes are then printed in the terminal. Never do this on a shared server.

**Gmail App Password.**
1. Go to Google Account → Security and turn on 2-Step Verification.
2. Open **App passwords** and create one for "Mail".
3. Put the 16-character password in `MAIL_PASSWORD`.

**DSA sandbox.** Keep Docker Desktop running. The first code run pulls `python:3.13-slim`. Only on a private development machine without Docker, you can set `PREPWISE_SANDBOX=local` to run code directly. Never do this on a server.

### Using the app

1. On the home page, upload a resume (PDF or DOCX, max 5 MB). You can try `sample_resume.pdf`.
2. Sign up with your email and a display name. Enter the 6-digit code.
3. Check the parsed profile on **Verify profile**, fix anything, and save.
4. On the **Dashboard**, pick a practice mode:
   - **Interview**: choose a focus (Mixed, Behavioral, Skills, or a project/internship).
   - **Technical**: choose a topic or *Recommended*.
   - **DSA**: choose a problem, write code, then click *Run* or *Submit*.
5. Read the feedback. The dashboard updates your topic proficiency and suggestions.

---

## Configuration reference (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | **required** | 32+ random characters. The app refuses to start without it. |
| `DATABASE_URL` | none | PostgreSQL URI. Remote hosts need `sslmode=require`. |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | none | Alternative to `DATABASE_URL`. |
| `GROQ_API_KEY` | none | Enables AI questions and grading. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | none | SMTP login for verification emails. Both must be set. |
| `MAIL_SERVER`, `MAIL_PORT`, `EMAIL_FROM` | Gmail SMTP | Other SMTP providers. |
| `FLASK_DEBUG` | off | `1` enables the debugger. **Development only.** |
| `PREPWISE_PRINT_OTP` | off | `1` prints codes in the console. Development only. |
| `PREPWISE_SANDBOX` | `docker` | `local` runs code without Docker. Private dev machines only. |
| `PREPWISE_SANDBOX_IMAGE` | `python:3.13-slim` | Docker image for code runs. `start.ps1` pins it by digest. |
| `PREPWISE_MAX_CODE_JOBS` | `4` | Concurrent code runs across all users. |
| `PREPWISE_HTTPS` | off | `1` sets Secure cookies and HSTS. Use behind HTTPS. |
| `PREPWISE_TRUST_PROXY` | off | `1` reads the real client IP from the reverse proxy. |
| `PREPWISE_HIBP` | `on` | Breached-password check. `off` disables it. |
| `PREPWISE_ALLOW_SQLITE_FALLBACK` | off | `1` allows the SQLite fallback even for a remote DB. |
| `PREPWISE_RATELIMIT`, `PREPWISE_CSRF` | `on` | Keep on. Tests may switch them off. |
| `PREPWISE_METRICS` | `on` | Writes metrics to `logs/app_metrics.jsonl`. |
| `HOST`, `PORT`, `THREADS` | `127.0.0.1`, `8000`, `8` | Settings for `serve.py`. |

---

## Testing and validation

```bash
pip install pytest
python -m pytest                    # 184 automated tests: unit, security regression, end-to-end
python -m pytest tests/test_practice_modes.py -v   # a single file
```

Numeric validation reports go to the console, `logs/` and `reports/`:

```bash
python -m validation.run            # every component against labelled data (~20 s)
python -m validation.run --quick    # faster, fewer samples
python -m validation.usage_report   # real usage from the database + logs/app_metrics.jsonl
```

| Metric | Result |
|---|---|
| Resume parser macro-F1 (PDF / DOCX) | 0.977 / 0.977 |
| Internship / project extraction F1 | 1.000 / 1.000 |
| Skill extraction F1 | 0.909 |
| Answer scoring: realistic answers in the correct band | **94.7%** (old keyword method: 36.8%) |
| Answer scoring: synthetic band accuracy / Spearman ρ | 95.1% / 0.951 |
| DSA judge accuracy | 100% |
| Skill metric: false "weak" flags after one attempt | 0% (plain average: 20.3%) |
| Security / score-integrity checks | 11 / 11 |

`validation.run` exits non-zero if any metric falls below its target, so it can gate CI. The CI workflow is in `ci/github-actions-ci.yml`. To enable it on GitHub, move it to `.github/workflows/ci.yml`; it then runs on every push. It runs the tests, the validation suite, `pip-audit` (dependency vulnerabilities) and `bandit` (static security scan).

---

## Running in production

`python app.py` is the **development** server. To host the app for other people:

1. In `.env`, set a strong `SECRET_KEY`, your `DATABASE_URL` and mail settings. Do **not** set `FLASK_DEBUG` or `PREPWISE_SANDBOX=local`.
2. Keep Docker running for the DSA sandbox.
3. Start the production server:
   ```bash
   python serve.py        # waitress on 127.0.0.1:8000
   ```
4. Put an HTTPS reverse proxy in front. For example, a [Caddy](https://caddyserver.com) `Caddyfile`:
   ```
   prep.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```
   Then add `PREPWISE_HTTPS=1` and `PREPWISE_TRUST_PROXY=1` to `.env`.
5. Run it under a normal (non-administrator) account.
6. Schedule the clean-up weekly. Without `--apply`, the command only lists resumes and logs older than 30 days; with `--apply` it deletes them:
   ```bash
   python -m tools.cleanup --apply
   ```
7. Rate limits are kept in memory, which suits a single `serve.py` process. For several processes or servers, move them to Redis.

---

## Project structure

```
app.py                     Flask app: routes, access control, security middleware
auth.py                    Passwords, one-time codes, email, user sessions
database.py                PostgreSQL / SQLite access and schema migrations
serve.py                   Production server (waitress)
start.ps1 / start.bat      Windows one-step setup and launch
requirements.txt           Pinned dependencies
.env.example               Configuration template (placeholders only)
modules/
  profile_parsing/         M1 – text extraction, parser, schema, skills taxonomy
  question_generation/     M2 – Interview / Technical question selection
  evaluation/              M3 – rubric, meaning similarity, AI blend, feedback
  analytics/               M4 – proficiency metric and recommendations
  coding/                  M5 – DSA bank, problem generator, sandboxed runner
  dsa_engine.py            DSA scoring / progress helpers
services/
  llm_service.py           Groq calls: question generation and grading (validated)
  security.py              CSRF, rate limiting, session fingerprints, job slots
  safe_parse.py            Sandboxed resume parsing (+ resume_worker.py)
  profile_sanitize.py      Profile whitelist and size limits
  metrics_log.py           Structured JSONL metrics with rotation
data/                      question_bank.json (technical), interview_bank.json
templates/, static/        Jinja2 pages, CSS, logo
tests/                     Automated tests (pytest)
validation/                Validation suites, labelled datasets, report generator
tools/                     Question-bank builders, data clean-up
logs/, reports/, uploads/  Runtime output (not committed)
```

---

## Security

The project went through a full security audit and four rounds of fixes. Each fix has a regression test. Highlights:

- **Authentication.**
  - Requires a strong `SECRET_KEY`.
  - bcrypt password hashes.
  - Password rules: minimum length, a common-password blocklist, and a breached-password check through the Have I Been Pwned k-anonymity API.
  - Sessions are tied to the password and to logout, and expire after 7 days.
- **Verification codes.**
  - Stored hashed and expire after 10 minutes.
  - 5 attempts per code, counted atomically.
  - Per-account and per-IP rate limits.
  - Responses don't reveal whether an email is registered.
- **Web protections.**
  - CSRF tokens on every form.
  - A Content-Security-Policy with per-request script nonces.
  - `X-Frame-Options: DENY`, `nosniff` and `no-store` on signed-in pages.
  - Safe redirects, and only `http(s)` links are shown.
- **Access control.** Every profile, question and problem is checked against the logged-in owner.
- **Untrusted input.**
  - Uploads are checked by file signature, capped at 5 MB, stored under random names and deleted after parsing.
  - Parsing runs in a time- and memory-limited child process.
- **Code execution.**
  - Docker only, with no network, a read-only filesystem, a non-root user, and CPU, memory and PID limits.
  - One job per user and 64 KB of output.
- **AI safety.**
  - Prompts use only the server-side profile, with no contact details, and mark resume text as untrusted data.
  - LLM output is validated.
  - Answers aimed at manipulating the grader are capped.
  - Questions and answer keys stay on the server.
- **Operations.**
  - TLS is enforced for remote databases.
  - Emails are masked in logs, and logs rotate.
  - Dependencies are pinned.

To report a vulnerability, contact the team privately. Please don't open a public issue.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SECRET_KEY is not set (or is shorter than 32 characters)` | Run `.\start.ps1`, or add the generated `SECRET_KEY=...` line to `.env` (see Option B, step 4). |
| `failed to resolve host '...pooler.supabase.com'` / database unreachable | This is a network or DNS problem, not a code problem. Check your internet connection, VPN or firewall, and whether the Supabase project is paused (free projects pause after inactivity). Check the host in `DATABASE_URL`. For offline work, set `PREPWISE_ALLOW_SQLITE_FALLBACK=1`. |
| Verification email never arrives | `MAIL_USERNAME` or `MAIL_PASSWORD` still hold the placeholder values, or `MAIL_PASSWORD` is not a Gmail App Password. Fix them, or comment them out and use `PREPWISE_PRINT_OTP=1` locally. |
| DSA *Run* says the sandbox is unavailable | Start Docker Desktop and wait until it says "running". Then retry. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Questions look generic / no AI feedback | `GROQ_API_KEY` is not set or is invalid, or the daily AI budget is used up. The curated bank is used instead. |
| `pip install` fails on `psycopg` | Upgrade pip (`pip install --upgrade pip`) and use Python 3.10+ (64-bit). |
| "Too many requests" | Rate limits are working. Wait a minute, or an hour for code requests. |

---

## Future scope

- **Agentic mock interviews.** A multi-turn interviewer that asks follow-up questions based on the student's previous answers, keeps context across a session and ends with an overall debrief.
- **Voice answers.** Speech-to-text for interview practice, with feedback on pace, filler words and clarity.
- **More DSA languages.** Java, C++ and JavaScript in the sandbox, plus complexity analysis of submissions.
- **Learning resources per weak topic.** Curated notes, videos and practice sets linked from each focus area, and a study plan that adapts after each session.
- **Company-specific preparation.** Question sets and difficulty tuned to target companies and roles, and matching of job descriptions to the resume.
- **Resume improvement assistant.** Rewrite suggestions for weak bullet points and an ATS-compatibility check.
- **Peer and mentor mode.** Shareable progress reports for placement cells and faculty, plus mentor review of answers.
- **Scalable cloud deployment.** Containerised deployment behind HTTPS, Redis-backed rate limits and job queues, and background workers for AI and code runs.
- **Better models.** Fine-tuned answer-scoring models trained on collected (consented) answers, and multilingual support.
- **Mobile app / PWA.** Offline question practice and reminders.
- **User study.** Measure how practice with Prepwise affects mock-interview and placement outcomes.

---

## License and acknowledgements

This is an academic project developed as part of the course project review. The question banks and datasets included here were written for this project. Third-party libraries are used under their own licenses (see `requirements.txt`).
