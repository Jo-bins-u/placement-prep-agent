"""Data retention clean-up. Shows what it would delete unless you pass --apply.

    python -m tools.cleanup                 # dry run: list resumes/logs older than 30 days
    python -m tools.cleanup --days 14 --apply

New resume uploads are already deleted right after parsing; this removes files left in
uploads/ by older versions, old log/report files, and expired pre-login resume records.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGETS = [
    ("uploads", ["*.pdf", "*.docx", "*.doc"]),
    ("logs", ["*.log", "*.log.*", "*.jsonl.*"]),
    ("reports", ["*.json", "*.md"]),
]


def old_files(days: int) -> list:
    cutoff = time.time() - days * 86400
    found = []
    for folder, patterns in TARGETS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for pattern in patterns:
            for path in base.glob(pattern):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    found.append(path)
    return sorted(set(found))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="delete files older than this many days (default 30)")
    parser.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    args = parser.parse_args(argv)

    files = old_files(max(args.days, 1))
    for path in files:
        print(("deleting " if args.apply else "would delete ") + str(path.relative_to(ROOT)))
        if args.apply:
            path.unlink(missing_ok=True)

    import database as db
    cutoff = (datetime.utcnow() - timedelta(hours=db.PENDING_UPLOAD_TTL_HOURS)).isoformat()
    conn = db.get_conn()
    count = conn.execute("SELECT COUNT(*) AS n FROM pending_uploads WHERE created_at < %s", (cutoff,)).fetchone()["n"]
    if args.apply:
        conn.execute("DELETE FROM pending_uploads WHERE created_at < %s", (cutoff,))
        conn.commit()
    conn.close()
    print(f"{'deleted' if args.apply else 'would delete'} {count} expired pre-login resume record(s)")
    if not args.apply:
        print("Dry run only. Re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
