"""OTP generator, OTP lifecycle, and the full sign-up / forgot / reset / change-password flows."""
import collections
import math
import os
import re
import unittest
from datetime import datetime, timedelta
from unittest import mock

import database as db

# Database / credential isolation is set up in tests/conftest.py.
import auth  # noqa: E402
import app as app_module  # noqa: E402

db.init_db()


class Mailbox:
    """Captures codes instead of emailing them."""

    def __init__(self):
        self.sent = []

    def __call__(self, email, code, purpose="verify"):
        self.sent.append((email, code, purpose))
        return False  # same as "mail not configured" in development

    def last(self, email=None, purpose=None):
        for sent_email, code, sent_purpose in reversed(self.sent):
            if (email is None or sent_email == email) and (purpose is None or sent_purpose == purpose):
                return code
        return None


def _new_user(email="u@example.com", password="secret123", verified=False):
    user_id = db.create_user(email, auth.hash_password(password))
    if verified:
        db.mark_user_verified(user_id)
    return db.get_user_by_id(user_id)


class OtpGeneratorTests(unittest.TestCase):
    def test_codes_are_six_digits(self):
        for _ in range(2000):
            code = auth.generate_otp()
            self.assertRegex(code, r"^\d{6}$")

    def test_digits_are_uniform(self):
        counts = collections.Counter("".join(auth.generate_otp() for _ in range(5000)))
        expected = 30000 / 10
        chi2 = sum((counts[str(d)] - expected) ** 2 / expected for d in range(10))
        # 9 degrees of freedom: chi2 > 27.88 would be p < 0.001
        self.assertLess(chi2, 27.88, f"digit distribution looks biased (chi2={chi2:.2f})")

    def test_codes_rarely_repeat(self):
        codes = [auth.generate_otp() for _ in range(3000)]
        self.assertGreater(len(set(codes)) / len(codes), 0.99)

    def test_uses_secure_randomness(self):
        with mock.patch("auth.secrets.randbelow", return_value=7) as fake:
            self.assertEqual(auth.generate_otp(), "777777")
            self.assertEqual(fake.call_count, 6)

    def test_hash_is_bound_to_user_and_purpose(self):
        h = auth.hash_otp(1, "verify", "123456")
        self.assertNotEqual(h, auth.hash_otp(2, "verify", "123456"))
        self.assertNotEqual(h, auth.hash_otp(1, "reset", "123456"))
        self.assertNotIn("123456", h)


class OtpLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.mail = Mailbox()
        patcher = mock.patch("auth.send_otp_email", self.mail)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = _new_user(f"life{datetime.utcnow().timestamp()}@example.com")

    def issue(self, purpose="verify", **kw):
        result = auth.issue_otp(db.get_user_by_id(self.user["id"]), purpose, **kw)
        return result, self.mail.last(self.user["email"], purpose)

    def test_code_is_stored_hashed(self):
        _, code = self.issue()
        stored = db.get_user_by_id(self.user["id"])["otp_code"]
        self.assertNotEqual(stored, code)
        self.assertEqual(len(stored), 64)

    def test_correct_code_verifies_once(self):
        _, code = self.issue()
        self.assertEqual(auth.verify_otp(self.user["id"], code, "verify"), auth.OTP_OK)
        self.assertEqual(auth.verify_otp(self.user["id"], code, "verify"), auth.OTP_MISSING)

    def test_spaces_and_dashes_in_code_are_ignored(self):
        _, code = self.issue()
        self.assertEqual(auth.verify_otp(self.user["id"], f" {code[:3]}-{code[3:]} ", "verify"), auth.OTP_OK)

    def test_wrong_code_then_lockout(self):
        _, code = self.issue()
        wrong = "000000" if code != "000000" else "111111"
        results = [auth.verify_otp(self.user["id"], wrong, "verify") for _ in range(auth.OTP_MAX_ATTEMPTS)]
        self.assertEqual(results[:-1], [auth.OTP_INVALID] * (auth.OTP_MAX_ATTEMPTS - 1))
        self.assertEqual(results[-1], auth.OTP_LOCKED)
        # even the right code is refused once locked
        self.assertEqual(auth.verify_otp(self.user["id"], code, "verify"), auth.OTP_LOCKED)

    def test_expired_code(self):
        _, code = self.issue()
        later = datetime.utcnow() + timedelta(minutes=auth.OTP_TTL_MINUTES + 1)
        self.assertEqual(auth.verify_otp(self.user["id"], code, "verify", now=later), auth.OTP_EXPIRED)

    def test_code_for_one_purpose_fails_for_another(self):
        _, code = self.issue("verify")
        self.assertEqual(auth.verify_otp(self.user["id"], code, "reset"), auth.OTP_MISSING)

    def test_resend_cooldown_and_new_code_replaces_old(self):
        _, first = self.issue()
        blocked, _ = self.issue()
        self.assertFalse(blocked.ok)
        self.assertGreater(blocked.wait_seconds, 0)
        later = datetime.utcnow() + timedelta(seconds=auth.OTP_RESEND_SECONDS + 1)
        again, second = self.issue(now=later)
        self.assertTrue(again.ok)
        if first != second:
            self.assertEqual(auth.verify_otp(self.user["id"], first, "verify"), auth.OTP_INVALID)
        self.assertEqual(auth.verify_otp(self.user["id"], second, "verify"), auth.OTP_OK)

    def test_new_code_resets_attempts(self):
        _, code = self.issue()
        for _ in range(auth.OTP_MAX_ATTEMPTS):
            auth.verify_otp(self.user["id"], "999999" if code != "999999" else "888888", "verify")
        _, fresh = self.issue(force=True)
        self.assertEqual(auth.verify_otp(self.user["id"], fresh, "verify"), auth.OTP_OK)


class EmailDeliveryTests(unittest.TestCase):
    def test_smtp_message_and_subject(self):
        env = {"MAIL_USERNAME": "me@example.com", "MAIL_PASSWORD": "app pass", "MAIL_SERVER": "smtp.test", "MAIL_PORT": "587"}
        with mock.patch.dict(os.environ, env), mock.patch("auth.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            self.assertTrue(auth.send_otp_email("to@example.com", "123456", "reset"))
            smtp.assert_called_once_with("smtp.test", 587, timeout=15)
            server.starttls.assert_called_once()
            server.login.assert_called_once_with("me@example.com", "apppass")
            msg = server.send_message.call_args[0][0]
            self.assertEqual(msg["To"], "to@example.com")
            self.assertIn("Reset", msg["Subject"])
            self.assertIn("123456", msg.get_payload()[0].get_payload())

    def test_smtp_failure_is_reported(self):
        env = {"MAIL_USERNAME": "me@example.com", "MAIL_PASSWORD": "x"}
        with mock.patch.dict(os.environ, env), mock.patch("auth.smtplib.SMTP", side_effect=OSError("down")):
            self.assertFalse(auth.send_otp_email("to@example.com", "123456"))

    def test_issue_fails_loudly_when_configured_mail_cannot_send(self):
        user = _new_user(f"mailfail{datetime.utcnow().timestamp()}@example.com")
        env = {"MAIL_USERNAME": "me@example.com", "MAIL_PASSWORD": "x"}
        with mock.patch.dict(os.environ, env), mock.patch("auth.smtplib.SMTP", side_effect=OSError("down")):
            result = auth.issue_otp(user, "verify")
        self.assertFalse(result.ok)
        self.assertIn("couldn't send", result.message)


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        self.mail = Mailbox()
        patcher = mock.patch("auth.send_otp_email", self.mail)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.email = f"flow{datetime.utcnow().timestamp()}@example.com"

    def register(self, password="secret123", confirm=None):
        return self.client.post("/register", data={"email": self.email, "password": password,
                                                    "confirm_password": confirm or password})

    def logged_in(self):
        return b"Log out" in self.client.get("/").data

    def test_signup_verify_and_login(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/verify-email", resp.headers["Location"])
        code = self.mail.last(self.email, "verify")
        self.assertIsNotNone(code)
        resp = self.client.post("/verify-email", data={"email": self.email, "otp": code})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.logged_in())
        self.client.post("/logout")
        resp = self.client.post("/login", data={"email": self.email.upper(), "password": "secret123"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.logged_in())

    def test_weak_or_mismatched_password_rejected(self):
        self.assertEqual(self.register("short1").status_code, 400)
        self.assertEqual(self.register("allletters").status_code, 400)
        self.assertEqual(self.register("secret123", "secret124").status_code, 400)
        self.assertIsNone(db.get_user_by_email(self.email))

    def test_wrong_code_does_not_verify(self):
        self.register()
        code = self.mail.last(self.email)
        wrong = "000000" if code != "000000" else "111111"
        resp = self.client.post("/verify-email", data={"email": self.email, "otp": wrong})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(db.get_user_by_email(self.email)["is_verified"])

    def test_unverified_user_can_sign_up_again(self):
        self.register()
        with mock.patch("auth.OTP_RESEND_SECONDS", 0):
            resp = self.register("newpass99")
        self.assertIn("/verify-email", resp.headers["Location"])
        code = self.mail.last(self.email)
        self.client.post("/verify-email", data={"email": self.email, "otp": code})
        self.client.post("/logout")
        self.client.post("/login", data={"email": self.email, "password": "newpass99"})
        self.assertTrue(self.logged_in())

    def test_unverified_login_sends_a_code(self):
        self.register()
        before = len(self.mail.sent)
        with mock.patch("auth.OTP_RESEND_SECONDS", 0):
            resp = self.client.post("/login", data={"email": self.email, "password": "secret123"})
        self.assertIn("/verify-email", resp.headers["Location"])
        self.assertEqual(len(self.mail.sent), before + 1)
        self.assertFalse(self.logged_in())

    def test_resend_code_respects_cooldown(self):
        self.register()
        before = len(self.mail.sent)
        resp = self.client.post("/resend-code", data={"email": self.email, "purpose": "verify"}, follow_redirects=True)
        self.assertEqual(len(self.mail.sent), before)
        self.assertIn(b"re-sent once a minute", resp.data)  # generic: no account probing
        with mock.patch("auth.OTP_RESEND_SECONDS", 0):
            self.client.post("/resend-code", data={"email": self.email, "purpose": "verify"})
        self.assertEqual(len(self.mail.sent), before + 1)

    def test_forgot_and_reset_password(self):
        _new_user(self.email, "oldpass11", verified=True)
        resp = self.client.post("/forgot-password", data={"email": self.email})
        self.assertIn("/reset-password", resp.headers["Location"])
        code = self.mail.last(self.email, "reset")
        self.assertIsNotNone(code)
        # weak new password is refused and the code is NOT consumed
        self.assertEqual(self.client.post("/reset-password", data={
            "email": self.email, "otp": code, "password": "weak", "confirm_password": "weak"}).status_code, 400)
        resp = self.client.post("/reset-password", data={
            "email": self.email, "otp": code, "password": "newpass22", "confirm_password": "newpass22"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])
        self.client.post("/login", data={"email": self.email, "password": "oldpass11"})
        self.assertFalse(self.logged_in())
        self.client.post("/login", data={"email": self.email, "password": "newpass22"})
        self.assertTrue(self.logged_in())

    def test_reset_code_cannot_be_reused(self):
        _new_user(self.email, "oldpass11", verified=True)
        self.client.post("/forgot-password", data={"email": self.email})
        code = self.mail.last(self.email, "reset")
        data = {"email": self.email, "otp": code, "password": "newpass22", "confirm_password": "newpass22"}
        self.assertEqual(self.client.post("/reset-password", data=data).status_code, 302)
        data.update(password="another33", confirm_password="another33")
        self.assertEqual(self.client.post("/reset-password", data=data).status_code, 400)

    def test_forgot_password_does_not_reveal_accounts(self):
        known = self.client.post("/forgot-password", data={"email": self.email}, follow_redirects=True)
        _new_user(self.email, "oldpass11", verified=True)
        self.client.post("/forgot-password", data={"email": self.email}, follow_redirects=True)
        self.assertIn(b"If an account exists", known.data)

    def test_verify_code_cannot_reset_password(self):
        self.register()
        verify_code = self.mail.last(self.email, "verify")
        resp = self.client.post("/reset-password", data={
            "email": self.email, "otp": verify_code, "password": "newpass22", "confirm_password": "newpass22"})
        self.assertEqual(resp.status_code, 400)

    def test_change_password(self):
        _new_user(self.email, "oldpass11", verified=True)
        self.client.post("/login", data={"email": self.email, "password": "oldpass11"})
        bad = self.client.post("/account/password", data={
            "current_password": "wrong", "password": "newpass22", "confirm_password": "newpass22"})
        self.assertEqual(bad.status_code, 400)
        same = self.client.post("/account/password", data={
            "current_password": "oldpass11", "password": "oldpass11", "confirm_password": "oldpass11"})
        self.assertEqual(same.status_code, 400)
        ok = self.client.post("/account/password", data={
            "current_password": "oldpass11", "password": "newpass22", "confirm_password": "newpass22"})
        self.assertEqual(ok.status_code, 302)
        self.client.post("/logout")
        self.client.post("/login", data={"email": self.email, "password": "newpass22"})
        self.assertTrue(self.logged_in())

    def test_change_password_requires_login(self):
        resp = self.client.get("/account/password")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_login_ignores_external_next_url(self):
        _new_user(self.email, "oldpass11", verified=True)
        resp = self.client.post("/login", data={"email": self.email, "password": "oldpass11", "next": "https://evil.example"})
        self.assertNotIn("evil", resp.headers["Location"])


if __name__ == "__main__":
    unittest.main()
