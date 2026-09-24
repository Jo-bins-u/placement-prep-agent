"""PostgreSQL / SQLite storage layer for the placement-prep application."""

import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime

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
            print(f"[DATABASE] Connection to PostgreSQL failed ({e}). Falling back to SQLite at {SQLITE_DB_PATH}")
            _USE_SQLITE = True

    return SQLiteConnectionWrapper(SQLITE_DB_PATH)


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
        conn.commit()
        conn.close()


def create_user(email: str, password_hash: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO app_users (email, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
        (email, password_hash, datetime.utcnow().isoformat())
    )
    conn.commit()
    user_id = cur.fetchone()["id"]
    conn.close()
    return user_id


def get_user_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM app_users WHERE email = %s", (email,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM app_users WHERE id = %s", (user_id,)).fetchone()
    conn.close()
    return row


def set_user_otp(user_id: int, otp_code: str, expires_at: str):
    conn = get_conn()
    conn.execute(
        "UPDATE app_users SET otp_code = %s, otp_expires_at = %s WHERE id = %s",
        (otp_code, expires_at, user_id)
    )
    conn.commit()
    conn.close()


def verify_user_otp(user_id: int, otp_code: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM app_users WHERE id = %s AND otp_code = %s",
        (user_id, otp_code)
    ).fetchone()
    if row:
        expires_at = datetime.fromisoformat(row["otp_expires_at"])
        if datetime.utcnow() <= expires_at:
            conn.execute("UPDATE app_users SET is_verified = TRUE, otp_code = NULL, otp_expires_at = NULL WHERE id = %s", (user_id,))
            conn.commit()
            conn.close()
            return True
    conn.close()
    return False


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
    conn.commit()
    candidate_id = cur.fetchone()["id"]
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
        "UPDATE candidates SET name = %s, email = %s, phone = %s, profile_json = %s WHERE id = %s",
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
                  score: float, feedback: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO attempts (candidate_id, question_id, topic, answer_text, score, feedback, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (candidate_id, question_id, topic, answer_text, score, feedback, datetime.utcnow().isoformat())
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
    }


def get_answered_question_ids(candidate_id: int) -> set:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT question_id FROM attempts WHERE candidate_id = %s", (candidate_id,)
    ).fetchall()
    conn.close()
    return {r["question_id"] for r in rows}

