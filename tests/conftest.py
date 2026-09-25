"""Test isolation: every test run uses a throwaway SQLite database and no real
credentials, so tests can never touch the real PostgreSQL database, send email,
call the LLM API or write to the production metrics log."""
import os
import tempfile
from pathlib import Path

# Empty (not missing) so python-dotenv does not load real values from .env.
for _key in ("MAIL_USERNAME", "MAIL_PASSWORD", "GROQ_API_KEY"):
    os.environ[_key] = ""
os.environ["PREPWISE_METRICS"] = "off"
os.environ["PREPWISE_SANDBOX"] = os.environ.get("PREPWISE_SANDBOX", "local")
os.environ["PREPWISE_RATELIMIT"] = "off"  # the security tests turn these back on where needed
os.environ["PREPWISE_CSRF"] = "off"
os.environ["PREPWISE_HIBP"] = "off"  # no network calls from tests
os.environ["PREPWISE_SYNC_EMAIL"] = "1"  # send (mocked) emails inline so tests can read them
os.environ["SECRET_KEY"] = "test-only-" + "k" * 40

import database as db  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="prepwise_tests_")
db._USE_SQLITE = True
db.SQLITE_DB_PATH = Path(_TMP) / "test.db"
db.init_db()
