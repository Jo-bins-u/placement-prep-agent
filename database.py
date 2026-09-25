"""PostgreSQL / SQLite storage layer for the placement-prep application."""

import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DB_DIR = Path(__file__).parent / "data"
DB_DIR.mkdir(exist_ok=True)
SQLITE_DB_PATH = DB_DIR / "app.db"

_USE_SQLITE = False

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5433")),
    "dbname": os.getenv("PGDATABASE", "placement_prep"),
    "user": os.getenv("PGUSER", "postgres"),
}
if os.getenv("PGPASSWORD"):
    DB_CONFIG["password"] = os.environ["PGPASSWORD"]
if os.getenv("DATABASE_URL"):
    DB_CONFIG = {"conninfo": os.environ["DATABASE_URL"]}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
_STRONG_SSLMODES = {"require", "verify-ca", "verify-full"}


def _is_local(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    return host in _LOCAL_HOSTS or host.startswith("/")  # "/..." = local Unix socket


def _require_tls(config: dict) -> dict:
    """A database on another machine must be reached over TLS: add sslmode=require unless a
    stronger mode is already set. Local databases are left alone. Handles URL and key=value
    connection strings, ?host= overrides and multi-host lists."""
    config = dict(config)
    if "conninfo" in config:
        try:
            from psycopg.conninfo import conninfo_to_dict, make_conninfo
            params = conninfo_to_dict(config["conninfo"])
        except Exception:
            return config  # unparsable: psycopg will report the problem when connecting
        hosts = [h for h in str(params.get("host") or "").split(",")] + [h for h in str(params.get("hostaddr") or "").split(",") if h]
        if any(not _is_local(h) for h in hosts if h) and params.get("sslmode") not in _STRONG_SSLMODES:
            config["conninfo"] = make_conninfo(config["conninfo"], sslmode="require")
    elif not _is_local(str(config.get("host", ""))) and config.get("sslmode") not in _STRONG_SSLMODES:
        config["sslmode"] = "require"
    return config


DB_CONFIG = _require_tls(DB_CONFIG)


def _remote_postgres_configured(config: dict) -> bool:
    """True when the configured PostgreSQL lives on another machine. Then a failed connection
    is an error, not a reason to quietly switch to a local SQLite file."""
    try:
        if "conninfo" in config:
            from psycopg.conninfo import conninfo_to_dict
            params = conninfo_to_dict(config["conninfo"])
            hosts = str(params.get("host") or "").split(",") + str(params.get("hostaddr") or "").split(",")
        else:
            hosts = [str(config.get("host", ""))]
    except Exception:
        return bool(os.getenv("DATABASE_URL"))
    return any(h and not _is_local(h) for h in hosts)


_POSTGRES_CONFIGURED = _remote_postgres_configured(DB_CONFIG)


class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    def __iter__(self):
        for row in self._cursor.fetchall():
            yield dict(row)


class SQLiteConnectionWrapper:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def execute(self, query: str, params=None):
        sql_query = query.replace("%s", "?")
        cur = self._conn.cursor()
        if params is None:
            if ";" in sql_query and not sql_query.strip().startswith("SELECT"):
                cur.executescript(sql_query)
            else:
                cur.execute(sql_query)
        else:
            cur.execute(sql_query, params)
        return SQLiteCursorWrapper(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    global _USE_SQLITE
    if not _USE_SQLITE:
        try:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg.connect(**DB_CONFIG, row_factory=dict_row, connect_timeout=10)
        except Exception as e:
            if _POSTGRES_CONFIGURED and os.getenv("PREPWISE_ALLOW_SQLITE_FALLBACK") != "1":
                # A configured database is unreachable (or refused TLS). Don't silently switch to a
                # local SQLite file - that would split users' data between two databases.
                raise RuntimeError(f"Could not connect to the configured (remote) PostgreSQL database: {type(e).__name__}. "
                                   "Check DATABASE_URL and your network (set PREPWISE_ALLOW_SQLITE_FALLBACK=1 "
                                   "to fall back to a local SQLite file instead).") from e
            print(f"[DATABASE] PostgreSQL not available ({type(e).__name__}). Using SQLite at {SQLITE_DB_PATH}")
            _USE_SQLITE = True

    return SQLiteConnectionWrapper(SQLITE_DB_PATH)


# Columns added after the first release. Applied on every start, safely.
EXTRA_COLUMNS = [
    ("app_users", "otp_purpose", "TEXT"),            # "verify" (sign-up) or "reset" (forgot password)
    ("app_users", "otp_attempts", "INTEGER DEFAULT 0"),
    ("app_users", "otp_sent_at", "TEXT"),
    ("attempts", "difficulty", "TEXT"),              # used by the skill-proficiency metric
    ("app_users", "pending_password_hash", "TEXT"),  # re-sign-up password, applied only once the email is verified
    ("app_users", "pending_password_nonce", "TEXT"), # ...and only in the browser session that chose it
    ("app_users", "session_version", "INTEGER DEFAULT 0"),  # bumped on logout: invalidates copied cookies
]


ISSUED_QUESTIONS_DDL = """
    CREATE TABLE IF NOT EXISTS issued_questions (
        id TEXT PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        question_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL,
        closed_at TEXT
    )
"""


# Resume parsed before sign-in: kept here (not in the browser cookie) until the visitor logs in.
PENDING_UPLOADS_DDL = """
    CREATE TABLE IF NOT EXISTS pending_uploads (
        id TEXT PRIMARY KEY,
        profile_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""
PENDING_UPLOAD_TTL_HOURS = 24


def _apply_extra_columns():
    conn = get_conn()
    for name, ddl in (("issued_questions", ISSUED_QUESTIONS_DDL), ("pending_uploads", PENDING_UPLOADS_DDL)):
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception as exc:  # pragma: no cover
            print(f"[DATABASE] Could not create {name}: {exc}")
    for table, column, ddl in EXTRA_COLUMNS:
        try:
            if _USE_SQLITE:
                existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            else:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
            conn.commit()
        except Exception as exc:  # pragma: no cover - logged, never fatal
            print(f"[DATABASE] Could not add {table}.{column}: {exc}")
    conn.close()


def init_db():
    conn = get_conn()
    if _USE_SQLITE:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                otp_code TEXT,
                otp_expires_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES app_users(id),
                name TEXT,
                email TEXT,
                phone TEXT,
                profile_json TEXT NOT NULL,
                resume_feedback_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                answer_text TEXT,
                score REAL NOT NULL,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );

            CREATE TABLE IF NOT EXISTS coding_problems (
                id TEXT PRIMARY KEY,
                candidate_id INTEGER,
                title TEXT NOT NULL,
                difficulty TEXT,
                topic TEXT,
                language TEXT,
                problem_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );

            CREATE TABLE IF NOT EXISTS coding_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                problem_id TEXT NOT NULL,
                code TEXT NOT NULL,
                passed_tests INTEGER,
                total_tests INTEGER,
                score REAL,
                execution_time_ms REAL,
                memory_usage_mb REAL,
                status TEXT,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );
        """)
        conn.commit()
        conn.close()

        conn = get_conn()
        try:
            conn.execute("ALTER TABLE candidates ADD COLUMN resume_feedback_json TEXT")
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE candidates ADD COLUMN user_id INTEGER REFERENCES app_users(id)")
            conn.commit()
        except Exception:
            pass
        conn.close()
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                otp_code TEXT,
                otp_expires_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES app_users(id),
                name TEXT,
                email TEXT,
                phone TEXT,
                profile_json TEXT NOT NULL,
                resume_feedback_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id BIGSERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                answer_text TEXT,
                score REAL NOT NULL,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );

            CREATE TABLE IF NOT EXISTS coding_problems (
                id TEXT PRIMARY KEY,
                candidate_id INTEGER,
                title TEXT NOT NULL,
                difficulty TEXT,
                topic TEXT,
                language TEXT,
                problem_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );

            CREATE TABLE IF NOT EXISTS coding_submissions (
                id BIGSERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                problem_id TEXT NOT NULL,
                code TEXT NOT NULL,
                passed_tests INTEGER,
                total_tests INTEGER,
                score REAL,
                execution_time_ms REAL,
                memory_usage_mb REAL,
                status TEXT,
                feedback TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            );
        """)
        conn.commit()
        conn.close()

        conn = get_conn()
        conn.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS resume_feedback_json TEXT")
        conn.execute("ALTER TABLE candidates ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES app_users(id)")
        # Older databases created candidates.user_id pointing at a legacy "users" table.
        # CREATE TABLE IF NOT EXISTS never updates that, so repoint the foreign key to app_users.
        # NOT VALID keeps any legacy rows (whose ids refer to the old table) instead of failing.
        conn.execute("""
            DO $$
            DECLARE r record;
            BEGIN
                FOR r IN
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_attribute att
                      ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
                    WHERE con.contype = 'f'
                      AND con.conrelid = 'candidates'::regclass
                      AND att.attname = 'user_id'
                      AND con.confrelid <> 'app_users'::regclass
                LOOP
                    EXECUTE format('ALTER TABLE candidates DROP CONSTRAINT %I', r.conname);
                END LOOP;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint con
                    JOIN pg_attribute att
                      ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
                    WHERE con.contype = 'f'
                      AND con.conrelid = 'candidates'::regclass
                      AND att.attname = 'user_id'
                      AND con.confrelid = 'app_users'::regclass
                ) THEN
                    ALTER TABLE candidates
                        ADD CONSTRAINT candidates_user_id_app_users_fkey
                        FOREIGN KEY (user_id) REFERENCES app_users(id) NOT VALID;
                END IF;
            END $$;
        """)
        conn.commit()
        conn.close()
    _apply_extra_columns()


def create_user(email: str, password_hash: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO app_users (email, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
        (email, password_hash, datetime.utcnow().isoformat())
    )
    user_id = cur.fetchone()["id"]  # fetch before commit (SQLite can't commit mid-statement)
    conn.commit()
    conn.close()
    return user_id


def get_user_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM app_users WHERE LOWER(email) = LOWER(%s)", ((email or "").strip(),)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM app_users WHERE id = %s", (user_id,)).fetchone()
    conn.close()
    return row


def store_otp(user_id: int, otp_hash: str, purpose: str, expires_at: str, sent_at: str) -> None:
    """Save a freshly issued one-time code (hashed) and reset the attempt counter."""
    conn = get_conn()
    conn.execute(
        "UPDATE app_users SET otp_code = %s, otp_purpose = %s, otp_expires_at = %s, otp_sent_at = %s, otp_attempts = 0 WHERE id = %s",
        (otp_hash, purpose, expires_at, sent_at, user_id),
    )
    conn.commit()
    conn.close()


def increment_otp_attempts(user_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE app_users SET otp_attempts = COALESCE(otp_attempts, 0) + 1 WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()


def consume_otp_attempt(user_id: int, purpose: str, max_attempts: int):
    """Atomically use up one attempt on the active code. Returns {'otp_code', 'otp_expires_at'}
    or None when there is no active code for this purpose or its attempts are exhausted.
    Single UPDATE ... RETURNING, so parallel guesses can't all read the same counter."""
    conn = get_conn()
    row = conn.execute(
        "UPDATE app_users SET otp_attempts = COALESCE(otp_attempts, 0) + 1 "
        "WHERE id = %s AND otp_code IS NOT NULL AND otp_purpose = %s AND COALESCE(otp_attempts, 0) < %s "
        "RETURNING otp_code, otp_expires_at",
        (user_id, purpose, max_attempts),
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def consume_otp_code(user_id: int, otp_hash: str) -> bool:
    """Clear the code only if it is still the one that was checked; True for exactly one caller."""
    conn = get_conn()
    row = conn.execute(
        "UPDATE app_users SET otp_code = NULL, otp_purpose = NULL, otp_expires_at = NULL, otp_attempts = 0 "
        "WHERE id = %s AND otp_code = %s RETURNING id",
        (user_id, otp_hash),
    ).fetchone()
    conn.commit()
    conn.close()
    return row is not None


def clear_otp(user_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE app_users SET otp_code = NULL, otp_purpose = NULL, otp_expires_at = NULL, otp_attempts = 0 WHERE id = %s",
        (user_id,),
    )
    conn.commit()
    conn.close()


def mark_user_verified(user_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE app_users SET is_verified = TRUE WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()


def update_password(user_id: int, password_hash: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE app_users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
    conn.commit()
    conn.close()


def get_candidates_by_user(user_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM candidates WHERE user_id = %s ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return rows


def save_candidate(user_id: int, profile) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO candidates (user_id, name, email, phone, profile_json, created_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, profile.contact.name, profile.contact.email, profile.contact.phone,
         profile.to_json(), datetime.utcnow().isoformat())
    )
    candidate_id = cur.fetchone()["id"]  # fetch before commit (SQLite can't commit mid-statement)
    conn.commit()
    conn.close()
    return candidate_id


def get_candidate(candidate_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,)).fetchone()
    conn.close()
    return row


def update_candidate_profile(candidate_id: int, profile: dict) -> bool:
    contact = profile.get("contact") or {}
    conn = get_conn()
    cur = conn.execute(
        # Clearing resume_feedback_json makes the dashboard re-score the edited profile.
        "UPDATE candidates SET name = %s, email = %s, phone = %s, profile_json = %s, resume_feedback_json = NULL WHERE id = %s",
        (
            contact.get("name"),
            contact.get("email"),
            contact.get("phone"),
            json.dumps(profile, indent=2),
            candidate_id,
        ),
    )
    conn.commit()
    updated = cur.rowcount == 1
    conn.close()
    return updated


def save_resume_feedback(candidate_id: int, feedback: dict) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE candidates SET resume_feedback_json = %s WHERE id = %s",
        (json.dumps(feedback, indent=2), candidate_id),
    )
    conn.commit()
    updated = cur.rowcount == 1
    conn.close()
    return updated


def get_resume_feedback(candidate_id: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT resume_feedback_json FROM candidates WHERE id = %s",
        (candidate_id,),
    ).fetchone()
    conn.close()
    if not row or not row["resume_feedback_json"]:
        return None
    return json.loads(row["resume_feedback_json"])


def save_attempt(candidate_id: int, question_id: str, topic: str, answer_text: str,
                  score: float, feedback: str, difficulty: str = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO attempts (candidate_id, question_id, topic, answer_text, score, feedback, created_at, difficulty) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (candidate_id, question_id, topic, answer_text, score, feedback, datetime.utcnow().isoformat(), difficulty)
    )
    conn.commit()
    conn.close()


def get_attempts(candidate_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE candidate_id = %s ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()
    conn.close()
    return rows


def save_coding_problem(problem_id: str, candidate_id: int, problem: dict) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO coding_problems (id, candidate_id, title, difficulty, topic, language, problem_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET candidate_id = EXCLUDED.candidate_id, title = EXCLUDED.title, difficulty = EXCLUDED.difficulty, topic = EXCLUDED.topic, language = EXCLUDED.language, problem_json = EXCLUDED.problem_json, created_at = EXCLUDED.created_at",
        (problem_id, candidate_id, problem.get("title"), problem.get("difficulty"), problem.get("topic"), problem.get("language"), json.dumps(problem), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_coding_problem(problem_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM coding_problems WHERE id = %s", (problem_id,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result["problem"] = json.loads(result.pop("problem_json"))
    return result


def get_recent_coding_hashes(candidate_id: int, topic: str, difficulty: str, limit: int = 30) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT problem_json FROM coding_problems WHERE candidate_id = %s AND topic = %s AND difficulty = %s ORDER BY created_at DESC LIMIT %s",
        (candidate_id, topic, difficulty, limit),
    ).fetchall()
    conn.close()
    hashes = []
    for row in rows:
        try:
            problem = json.loads(row["problem_json"])
        except (TypeError, ValueError):
            continue
        if problem.get("canonical_hash"):
            hashes.append(problem["canonical_hash"])
    return hashes


def save_coding_submission(candidate_id: int, problem_id: str, code: str, passed_tests: int, total_tests: int, score: float, execution_time_ms: float, memory_usage_mb: float, status: str, feedback: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO coding_submissions (candidate_id, problem_id, code, passed_tests, total_tests, score, execution_time_ms, memory_usage_mb, status, feedback, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (candidate_id, problem_id, code, passed_tests, total_tests, score, execution_time_ms, memory_usage_mb, status, feedback, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_coding_submissions(candidate_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM coding_submissions WHERE candidate_id = %s ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()
    conn.close()
    return rows


def get_dsa_performance(candidate_id: int) -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.problem_id, p.difficulty, p.topic, s.score, s.passed_tests, s.total_tests, "
        "s.status, s.execution_time_ms, s.created_at "
        "FROM coding_submissions s LEFT JOIN coding_problems p ON p.id = s.problem_id "
        "WHERE s.candidate_id = %s ORDER BY s.created_at ASC",
        (candidate_id,),
    ).fetchall()
    conn.close()

    submissions = [dict(row) for row in rows]
    attempted = len(submissions)
    solved = sum(1 for row in submissions if row["status"] == "correct" or float(row["score"] or 0) >= 100)
    scores = [float(row["score"] or 0) for row in submissions]
    by_difficulty = {}
    topic_scores = {}
    for row in submissions:
        difficulty = row["difficulty"] or "unknown"
        topic = row["topic"] or "unknown"
        by_difficulty.setdefault(difficulty, []).append(float(row["score"] or 0))
        topic_scores.setdefault(topic, []).append(float(row["score"] or 0))

    average_by_difficulty = {
        key: round(sum(values) / len(values), 1)
        for key, values in by_difficulty.items()
    }
    average_by_topic = {
        key: round(sum(values) / len(values), 1)
        for key, values in topic_scores.items()
    }
    return {
        "attempted": attempted,
        "solved": solved,
        "average_score": round(sum(scores) / attempted, 1) if attempted else 0,
        "best_score": round(max(scores), 1) if scores else 0,
        "success_rate": round((solved / attempted) * 100, 1) if attempted else 0,
        "by_difficulty": average_by_difficulty,
        "topic_scores": average_by_topic,
        "trend": [
            {"attempt": index, "score": row["score"], "created_at": row["created_at"]}
            for index, row in enumerate(submissions, start=1)
        ],
        "submissions": [
            {"topic": row["topic"], "difficulty": row["difficulty"], "score": float(row["score"] or 0),
             "created_at": row["created_at"]}
            for row in submissions
        ],
    }


def get_answered_question_ids(candidate_id: int) -> set:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT question_id FROM attempts WHERE candidate_id = %s", (candidate_id,)
    ).fetchall()
    conn.close()
    return {r["question_id"] for r in rows}


# ---------------------------------------------------------------------------
# Issued interview questions (kept server-side so answers/rubrics never reach the browser)
# ---------------------------------------------------------------------------
def save_issued_question(issue_id: str, candidate_id: int, question: dict) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO issued_questions (id, candidate_id, question_json, status, created_at) VALUES (%s, %s, %s, 'open', %s)",
        (issue_id, candidate_id, json.dumps(question), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_issued_question(issue_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM issued_questions WHERE id = %s", (issue_id,)).fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    row["question"] = json.loads(row["question_json"])
    return row


def get_open_issued_question(candidate_id: int, max_age_hours: int = 24):
    """The candidate's most recent unanswered question, so refreshing the page doesn't reroll it."""
    since = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM issued_questions WHERE candidate_id = %s AND status = 'open' AND created_at >= %s "
        "ORDER BY created_at DESC LIMIT 1",
        (candidate_id, since),
    ).fetchone()
    conn.close()
    if not row:
        return None
    row = dict(row)
    row["question"] = json.loads(row["question_json"])
    return row


def close_issued_question(issue_id: str, status: str) -> bool:
    """Mark answered/skipped. Returns False if it was already closed (prevents double submission)."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE issued_questions SET status = %s, closed_at = %s WHERE id = %s AND status = 'open'",
        (status, datetime.utcnow().isoformat(), issue_id),
    )
    conn.commit()
    changed = cur.rowcount == 1
    conn.close()
    return changed


def get_recent_question_prompts(candidate_id: int, limit: int = 40) -> list:
    """Prompts already shown to this candidate (newest first) — used to avoid repeats."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT question_json FROM issued_questions WHERE candidate_id = %s ORDER BY created_at DESC LIMIT %s",
        (candidate_id, limit),
    ).fetchall()
    conn.close()
    prompts = []
    for row in rows:
        try:
            prompts.append(json.loads(row["question_json"]).get("prompt") or "")
        except (TypeError, ValueError):
            continue
    return [p for p in prompts if p]


# ---------------------------------------------------------------------------
# Pending (pre-login) resume uploads
# ---------------------------------------------------------------------------
def save_pending_upload(profile_json: str) -> str:
    """Store a parsed resume for a visitor who hasn't signed in yet; returns an opaque id.
    Also deletes pending uploads older than PENDING_UPLOAD_TTL_HOURS."""
    import secrets
    now = datetime.utcnow()
    upload_id = secrets.token_urlsafe(24)
    conn = get_conn()
    conn.execute("DELETE FROM pending_uploads WHERE created_at < %s",
                 ((now - timedelta(hours=PENDING_UPLOAD_TTL_HOURS)).isoformat(),))
    conn.execute("INSERT INTO pending_uploads (id, profile_json, created_at) VALUES (%s, %s, %s)",
                 (upload_id, profile_json, now.isoformat()))
    conn.commit()
    conn.close()
    return upload_id


def pop_pending_upload(upload_id: str):
    """Return and delete a pending upload's profile JSON (None if missing or expired)."""
    if not upload_id:
        return None
    cutoff = (datetime.utcnow() - timedelta(hours=PENDING_UPLOAD_TTL_HOURS)).isoformat()
    conn = get_conn()
    row = conn.execute(
        "DELETE FROM pending_uploads WHERE id = %s RETURNING profile_json, created_at", (upload_id,)
    ).fetchone()
    conn.commit()
    conn.close()
    if not row or str(row["created_at"]) < cutoff:
        return None
    return row["profile_json"]


def set_pending_password(user_id: int, password_hash, nonce_hash=None) -> None:
    """Remember a password chosen by re-signing up (or clear it with None). `nonce_hash` ties
    it to the browser session that chose it."""
    conn = get_conn()
    conn.execute("UPDATE app_users SET pending_password_hash = %s, pending_password_nonce = %s WHERE id = %s",
                 (password_hash, nonce_hash if password_hash else None, user_id))
    conn.commit()
    conn.close()


def apply_pending_password(user_id: int, nonce_hash) -> bool:
    """Called after the email code is verified. The pending password takes effect only if the
    verifying browser is the one that chose it; either way the pending value is then cleared.
    (Otherwise someone could re-register a victim's unverified email and have *their*
    password applied when the victim enters their own code.)"""
    conn = get_conn()
    applied = False
    if nonce_hash:
        row = conn.execute(
            "UPDATE app_users SET password_hash = pending_password_hash WHERE id = %s "
            "AND pending_password_hash IS NOT NULL AND pending_password_nonce = %s RETURNING id",
            (user_id, nonce_hash),
        ).fetchone()
        applied = row is not None
    conn.execute("UPDATE app_users SET pending_password_hash = NULL, pending_password_nonce = NULL WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    return applied


def bump_session_version(user_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE app_users SET session_version = COALESCE(session_version, 0) + 1 WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
