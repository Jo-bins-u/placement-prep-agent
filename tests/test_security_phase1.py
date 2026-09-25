"""Regression tests for the Phase 1 security fixes (audit IDs C-01, C-02, H-01, H-02, H-03)."""
import io
import os
import threading
import unittest
from datetime import datetime, timedelta
from unittest import mock

import auth
import database as db
from app import app, UPLOAD_DIR
from modules.coding import runner
from services import security

PDF = b"%PDF-1.4\n%fake\n"


class SecretKeyTests(unittest.TestCase):  # C-02
    def test_missing_or_weak_key_is_fatal(self):
        for value in ("", "short", "dev-secret-change-this-for-real-deployment"):
            with mock.patch.dict(os.environ, {"SECRET_KEY": value}):
                with self.assertRaises(RuntimeError):
                    security.get_secret_key()

    def test_no_hardcoded_fallback_in_code(self):
        for path in ("app.py", "auth.py"):
            with open(path, encoding="utf-8") as fh:
                self.assertNotIn("dev-secret-change-this", fh.read())

    def test_strong_key_accepted(self):
        with mock.patch.dict(os.environ, {"SECRET_KEY": "x" * 40}):
            self.assertEqual(security.get_secret_key(), "x" * 40)


class SandboxTests(unittest.TestCase):  # C-01
    PROBLEM = {"function_signature": {"name": "solve", "parameters": [{"name": "n"}]},
               "visible_test_cases": [{"args": [1], "expected": 1}],
               "hidden_test_cases": [{"args": [1], "expected": 1}]}

    def test_code_is_not_executed_without_a_sandbox(self):
        marker = os.path.join(UPLOAD_DIR.parent, "data", "sandbox_probe.txt")
        code = f"open({marker!r}, 'w').write('ran')\ndef solve(n):\n    return n\n"
        with mock.patch.dict(os.environ, {"PREPWISE_SANDBOX": ""}), \
                mock.patch.dict(runner._DOCKER_STATE, {"path": None}):
            run = runner.run_candidate_code(self.PROBLEM, code)
            submit = runner.evaluate_submission(self.PROBLEM, code)
        self.assertEqual(run["status"], "unavailable")
        self.assertEqual(submit["status"], "unavailable")
        self.assertFalse(os.path.exists(marker))

    def test_explicit_local_opt_in_still_runs(self):
        with mock.patch.dict(os.environ, {"PREPWISE_SANDBOX": "local"}):
            result = runner.run_candidate_code(self.PROBLEM, "def solve(n):\n    return n\n")
        self.assertEqual(result["status"], "passed")

    def test_local_run_gets_no_app_secrets(self):
        code = "import os\ndef solve(n):\n    return os.environ.get('SECRET_KEY', 'none')\n"
        problem = dict(self.PROBLEM, visible_test_cases=[{"args": [1], "expected": "none"}])
        with mock.patch.dict(os.environ, {"PREPWISE_SANDBOX": "local"}):
            self.assertEqual(runner.run_candidate_code(problem, code)["status"], "passed")


class UploadTests(unittest.TestCase):  # H-01
    def setUp(self):
        self.client = app.test_client()

    def _post(self, name, content=PDF):
        return self.client.post("/upload", data={"resume": (io.BytesIO(content), name)},
                                content_type="multipart/form-data")

    def test_traversal_filename_cannot_escape_uploads(self):
        before = set(os.listdir(UPLOAD_DIR))
        for name in ("../escape_probe.pdf", "..\\escape_probe.pdf", "/tmp/escape_probe.pdf"):
            self._post(name)
        self.assertFalse((UPLOAD_DIR.parent / "escape_probe.pdf").exists())
        self.assertFalse(os.path.exists("/tmp/escape_probe.pdf"))
        self.assertEqual(set(os.listdir(UPLOAD_DIR)), before)  # parsed then deleted

    def test_wrong_file_type_or_fake_content_rejected(self):
        for name, content in (("cv.exe", PDF), ("cv.pdf", b"MZ not a pdf"), ("cv.docx", PDF)):
            resp = self._post(name, content)
            self.assertEqual(resp.status_code, 302)
            with self.client.session_transaction() as sess:
                self.assertNotIn("pending_profile", sess)

    def test_oversized_upload_rejected(self):
        resp = self._post("big.pdf", PDF + b"0" * (6 * 1024 * 1024))
        self.assertEqual(resp.status_code, 302)


class OtpRaceTests(unittest.TestCase):  # H-02
    def setUp(self):
        email = "otp-race@example.com"
        row = db.get_user_by_email(email)
        self.uid = row["id"] if row else db.create_user(email, auth.hash_password("secret123"))
        self.code = "123456"
        expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        db.store_otp(self.uid, auth.hash_otp(self.uid, auth.PURPOSE_RESET, self.code), auth.PURPOSE_RESET,
                     expires, datetime.utcnow().isoformat())

    def test_parallel_guesses_cannot_exceed_attempt_limit(self):
        results = []
        guesses = [f"{i:06d}" for i in range(200000, 200040)]

        def guess(code):
            results.append(auth.verify_otp(self.uid, code, auth.PURPOSE_RESET))

        threads = [threading.Thread(target=guess, args=(g,)) for g in guesses]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        evaluated = sum(r == auth.OTP_INVALID for r in results)
        self.assertLessEqual(evaluated, auth.OTP_MAX_ATTEMPTS - 1)
        self.assertLessEqual(int(db.get_user_by_id(self.uid)["otp_attempts"]), auth.OTP_MAX_ATTEMPTS)
        # The right code no longer works once the attempts are used up.
        self.assertEqual(auth.verify_otp(self.uid, self.code, auth.PURPOSE_RESET), auth.OTP_LOCKED)

    def test_correct_code_works_once(self):
        self.assertEqual(auth.verify_otp(self.uid, self.code, auth.PURPOSE_RESET), auth.OTP_OK)
        self.assertEqual(auth.verify_otp(self.uid, self.code, auth.PURPOSE_RESET), auth.OTP_MISSING)


class RateLimitTests(unittest.TestCase):  # H-02 / M-01
    def setUp(self):
        security.limiter.reset()
        self.env = mock.patch.dict(os.environ, {"PREPWISE_RATELIMIT": "on"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        security.limiter.reset()

    def test_login_is_throttled_per_email(self):
        client = app.test_client()
        codes = [client.post("/login", data={"email": "victim@example.com", "password": "wrong1234"}).status_code
                 for _ in range(12)]
        self.assertIn(429, codes)
        self.assertEqual(codes[:10], [401] * 10)

    def test_reset_password_is_throttled(self):
        client = app.test_client()
        codes = [client.post("/reset-password", data={"email": "victim@example.com", "otp": "000000",
                                                      "password": "newpass123", "confirm_password": "newpass123"}).status_code
                 for _ in range(12)]
        self.assertEqual(codes[-1], 429)

    def test_otp_issue_cap_per_account(self):
        row = db.get_user_by_email("otp-cap@example.com")
        uid = row["id"] if row else db.create_user("otp-cap@example.com", auth.hash_password("secret123"))
        results = [auth.issue_otp(db.get_user_by_id(uid), auth.PURPOSE_RESET, force=True).ok for _ in range(8)]
        self.assertEqual(results.count(True), auth.OTP_MAX_CODES_PER_HOUR)

    def test_limiter_window_expires(self):
        lim = security.RateLimiter()
        self.assertEqual(lim.hit("k", 2, 10, now=0), 0)
        self.assertEqual(lim.hit("k", 2, 10, now=1), 0)
        self.assertGreater(lim.hit("k", 2, 10, now=2), 0)
        self.assertEqual(lim.hit("k", 2, 10, now=11), 0)


class ErrorPageTests(unittest.TestCase):  # H-03
    def test_debug_off_and_errors_are_generic(self):
        self.assertFalse(app.debug)
        with open("app.py", encoding="utf-8") as fh:
            self.assertNotIn("debug=True", fh.read())

        def boom():
            raise RuntimeError("internal detail that must not leak")

        with mock.patch.dict(app.view_functions, {"home": boom}), \
                mock.patch.dict(app.config, {"TESTING": False}), \
                mock.patch.dict(app.config, {"PROPAGATE_EXCEPTIONS": False}):
            resp = app.test_client().get("/")
        body = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("internal detail", body)
        self.assertNotIn("Traceback", body)

    def test_404_page(self):
        resp = app.test_client().get("/definitely-not-here")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Page not found", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
