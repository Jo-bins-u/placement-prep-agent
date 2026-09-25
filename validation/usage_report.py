"""
Usage report — numbers from the running application (database + runtime metrics log).

    python -m validation.usage_report              # everything recorded so far
    python -m validation.usage_report --days 7     # only the last 7 days of metric events

Reads the app's configured database (PostgreSQL or the SQLite fallback) and
logs/app_metrics.jsonl, logs a numeric summary and writes
reports/usage_<timestamp>.md and .json.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation import metrics as M  # noqa: E402

log = logging.getLogger("prepwise.usage")


def _setup_logging(stamp: str):
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(ROOT / "logs" / f"usage_{stamp}.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)


def _events(since: datetime | None) -> list:
    from services.metrics_log import metric_files
    events = []
    for path in metric_files():  # rotated files first, then the current one
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since and record.get("ts", "") < since.isoformat():
                continue
            events.append(record)
    return events


def _database_numbers() -> dict:
    import database as db

    conn = db.get_conn()
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
    users = q("SELECT is_verified FROM app_users")
    candidates = q("SELECT profile_json FROM candidates")
    attempts = q("SELECT topic, score FROM attempts")
    submissions = q("SELECT s.status, s.score, s.passed_tests, s.total_tests, p.difficulty FROM coding_submissions s "
                    "LEFT JOIN coding_problems p ON p.id = s.problem_id")
    conn.close()

    profiles = [json.loads(row["profile_json"]) for row in candidates if row.get("profile_json")]
    topic_scores = collections.defaultdict(list)
    for row in attempts:
        topic_scores[row["topic"]].append(float(row["score"] or 0))
    by_difficulty = collections.defaultdict(list)
    for row in submissions:
        by_difficulty[row.get("difficulty") or "unknown"].append(row)

    return {
        "users": len(users),
        "verified_users": sum(1 for u in users if u["is_verified"]),
        "profiles": len(profiles),
        "profiles_with_internships": sum(1 for p in profiles if p.get("internships")),
        "avg_projects_per_profile": M.mean([len(p.get("projects") or []) for p in profiles]),
        "avg_internships_per_profile": M.mean([len(p.get("internships") or []) for p in profiles]),
        "avg_skills_per_profile": M.mean([len(p.get("skills") or []) for p in profiles]),
        "answers": len(attempts),
        "answer_mean_score": M.mean([float(a["score"] or 0) for a in attempts]),
        "answers_by_topic": {t: {"count": len(v), "mean": M.mean(v)} for t, v in sorted(topic_scores.items())},
        "code_submissions": len(submissions),
        "code_accepted_rate": M.mean([1.0 if s["status"] == "correct" else 0.0 for s in submissions]),
        "code_mean_score": M.mean([float(s["score"] or 0) for s in submissions]),
        "code_by_difficulty": {d: {"count": len(v), "accepted_rate": M.mean([1.0 if s["status"] == "correct" else 0.0 for s in v])}
                               for d, v in sorted(by_difficulty.items())},
    }


def _event_numbers(events: list) -> dict:
    by = collections.defaultdict(list)
    for e in events:
        by[e["event"]].append(e)

    requests = by["http_request"]
    endpoints = collections.defaultdict(list)
    for r in requests:
        endpoints[r.get("endpoint")].append(float(r.get("ms") or 0))
    parsed = by["resume_parsed"]
    answers = by["answer_evaluated"]
    runs, subs = by["code_run"], by["code_submitted"]
    issued, verified = by["otp_issued"], by["otp_verified"]
    verify_results = collections.Counter(v.get("result") for v in verified)

    return {
        "events": len(events),
        "first_event": events[0]["ts"] if events else None,
        "last_event": events[-1]["ts"] if events else None,
        "requests": len(requests),
        "server_error_rate": M.mean([1.0 if int(r.get("status") or 0) >= 500 else 0.0 for r in requests]),
        "latency_ms_by_endpoint": {
            ep: {"count": len(v), "p50": M.percentile(v, 0.5), "p95": M.percentile(v, 0.95)}
            for ep, v in sorted(endpoints.items(), key=lambda kv: -len(kv[1]))
        },
        "resumes_parsed": len(parsed),
        "resume_parse_failures": len(by["resume_parse_failed"]),
        "parse_ms": {"mean": M.mean([p["ms"] for p in parsed]), "p95": M.percentile([p["ms"] for p in parsed], 0.95)},
        "parse_avg_fields": {k: M.mean([float(p.get(k) or 0) for p in parsed]) for k in ("skills", "projects", "internships", "education")},
        "parse_email_found_rate": M.mean([1.0 if p.get("has_email") else 0.0 for p in parsed]),
        "answers_evaluated": len(answers),
        "answer_score_mean": M.mean([float(a.get("score") or 0) for a in answers]),
        "answer_score_valid_rate": M.mean([1.0 if a.get("valid") else 0.0 for a in answers]),
        "answer_eval_ms_mean": M.mean([float(a.get("ms") or 0) for a in answers]),
        "code_runs": len(runs),
        "code_run_status": dict(collections.Counter(r.get("status") for r in runs)),
        "code_submissions": len(subs),
        "code_submission_status": dict(collections.Counter(s.get("status") for s in subs)),
        "code_judge_ms_mean": M.mean([float(s.get("ms") or 0) for s in runs + subs]),
        "otp_issued": len(issued),
        "otp_email_delivery_rate": M.mean([1.0 if i.get("delivered") else 0.0 for i in issued if i.get("mail_configured")]) if any(i.get("mail_configured") for i in issued) else None,
        "otp_verify_attempts": len(verified),
        "otp_verify_results": dict(verify_results),
        "otp_success_rate": verify_results.get("ok", 0) / len(verified) if verified else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Summarise real usage from the database and metrics log.")
    parser.add_argument("--days", type=int, help="only include metric events from the last N days")
    args = parser.parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _setup_logging(stamp)
    since = datetime.utcnow() - timedelta(days=args.days) if args.days else None

    db_numbers = _database_numbers()
    ev_numbers = _event_numbers(_events(since))

    log.info("=" * 70)
    log.info("PREPWISE USAGE REPORT%s", f" (last {args.days} days of events)" if args.days else "")
    log.info("=" * 70)
    log.info("Users %d (verified %d) | profiles %d (%d with internships)", db_numbers["users"], db_numbers["verified_users"],
             db_numbers["profiles"], db_numbers["profiles_with_internships"])
    log.info("Per profile: %.1f skills, %.1f projects, %.1f internships", db_numbers["avg_skills_per_profile"],
             db_numbers["avg_projects_per_profile"], db_numbers["avg_internships_per_profile"])
    log.info("Interview answers %d | mean score %.1f", db_numbers["answers"], db_numbers["answer_mean_score"])
    log.info("Code submissions %d | accepted %.1f%% | mean score %.1f", db_numbers["code_submissions"],
             db_numbers["code_accepted_rate"] * 100, db_numbers["code_mean_score"])
    log.info("Metric events %d | HTTP requests %d | server error rate %.2f%%", ev_numbers["events"], ev_numbers["requests"],
             ev_numbers["server_error_rate"] * 100)
    log.info("Resume parsing: %d parsed, %d failed | %.0f ms mean (p95 %.0f) | email found %.0f%%", ev_numbers["resumes_parsed"],
             ev_numbers["resume_parse_failures"], ev_numbers["parse_ms"]["mean"], ev_numbers["parse_ms"]["p95"],
             ev_numbers["parse_email_found_rate"] * 100)
    log.info("Answers evaluated %d | mean %.1f | valid score range %.0f%% | %.1f ms mean", ev_numbers["answers_evaluated"],
             ev_numbers["answer_score_mean"], ev_numbers["answer_score_valid_rate"] * 100, ev_numbers["answer_eval_ms_mean"])
    log.info("Code runs %d %s | submissions %d %s | %.0f ms mean", ev_numbers["code_runs"], ev_numbers["code_run_status"],
             ev_numbers["code_submissions"], ev_numbers["code_submission_status"], ev_numbers["code_judge_ms_mean"])
    log.info("OTP issued %d | verify attempts %d %s | success rate %s", ev_numbers["otp_issued"], ev_numbers["otp_verify_attempts"],
             ev_numbers["otp_verify_results"], "n/a" if ev_numbers["otp_success_rate"] is None else f"{ev_numbers['otp_success_rate'] * 100:.0f}%")
    for ep, v in list(ev_numbers["latency_ms_by_endpoint"].items())[:10]:
        log.info("  %-24s n=%-5d p50 %6.1f ms  p95 %6.1f ms", ep, v["count"], v["p50"], v["p95"])

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    payload = {"generated": stamp, "database": db_numbers, "runtime": ev_numbers}
    (out / f"usage_{stamp}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = [f"# Prepwise usage report", "", f"Generated {stamp}", "", "## Database", ""]
    md += [f"* **{k.replace('_', ' ')}**: {round(v, 2) if isinstance(v, float) else v}" for k, v in db_numbers.items() if not isinstance(v, dict)]
    md += ["", "## Runtime (metrics log)", ""]
    md += [f"* **{k.replace('_', ' ')}**: {round(v, 3) if isinstance(v, float) else v}" for k, v in ev_numbers.items() if not isinstance(v, dict) or k in ("code_run_status", "code_submission_status", "otp_verify_results")]
    md += ["", "| Endpoint | Requests | p50 ms | p95 ms |", "|---|---:|---:|---:|"]
    md += [f"| {ep} | {v['count']} | {v['p50']:.1f} | {v['p95']:.1f} |" for ep, v in ev_numbers["latency_ms_by_endpoint"].items()]
    (out / f"usage_{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log.info("Report written: reports/usage_%s.md and .json", stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
