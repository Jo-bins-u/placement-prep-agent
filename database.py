"""
Storage layer. SQLite for the prototype — swap for MySQL/Postgres/Mongo
later per the PRD's tech stack without changing the rest of the app,
as long as these function signatures stay the same.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "data" / "app.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            profile_json TEXT NOT NULL,
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
    """)
    conn.commit()
    conn.close()


def save_candidate(profile) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO candidates (name, email, phone, profile_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (profile.contact.name, profile.contact.email, profile.contact.phone,
         profile.to_json(), datetime.utcnow().isoformat())
    )
    conn.commit()
    candidate_id = cur.lastrowid
    conn.close()
    return candidate_id


def get_candidate(candidate_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    conn.close()
    return row


def save_attempt(candidate_id: int, question_id: str, topic: str, answer_text: str,
                  score: float, feedback: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO attempts (candidate_id, question_id, topic, answer_text, score, feedback, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (candidate_id, question_id, topic, answer_text, score, feedback, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_attempts(candidate_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE candidate_id = ? ORDER BY created_at DESC", (candidate_id,)
    ).fetchall()
    conn.close()
    return rows


def get_answered_question_ids(candidate_id: int) -> set:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT question_id FROM attempts WHERE candidate_id = ?", (candidate_id,)
    ).fetchall()
    conn.close()
    return {r["question_id"] for r in rows}
