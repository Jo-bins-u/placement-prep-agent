"""Interview vs Technical practice modes, topic choice, the upgraded answer scoring/feedback,
display names and the logo."""
import html
import json
import re
import unittest
from datetime import datetime
from unittest import mock

import auth
import database as db
from app import app
from modules.evaluation import evaluator
from modules.profile_parsing.schema import CandidateProfile, ContactInfo, Internship, Project
from tests.test_auth_otp import Mailbox


def _user(tag, **profile):
    email = f"{tag}{datetime.utcnow().timestamp()}@example.com"
    uid = db.create_user(email, auth.hash_password("secret123"), "Test Person")
    db.mark_user_verified(uid)
    prof = CandidateProfile(contact=ContactInfo(name="T", email=email), skills=profile.get("skills", ["Python", "SQL"]),
                            projects=profile.get("projects", [Project(title="Chat App", tech_stack=["Flask", "Redis"])]),
                            internships=profile.get("internships", [Internship(role="Backend Intern", company="Acme")]))
    cid = db.save_candidate(uid, prof)
    client = app.test_client()
    client.post("/login", data={"email": email, "password": "secret123"})
    return client, cid


def _issued(cid):
    return db.get_open_issued_question(cid)["question"]


BANK_TOPICS = {q["topic"] for q in json.load(open("data/question_bank.json"))}


class ModeTests(unittest.TestCase):
    def test_interview_and_technical_questions_are_different_kinds(self):
        client, cid = _user("modes")
        client.get(f"/practice/{cid}?mode=technical&topic=recommended")
        technical = _issued(cid)
        client.get(f"/practice/{cid}?mode=interview&topic=mixed")
        interview = _issued(cid)
        self.assertEqual(technical["mode"], "technical")
        self.assertIn(technical["topic"], BANK_TOPICS)
        self.assertEqual(interview["mode"], "interview")
        self.assertIn(interview["topic"], {"Behavioral", "Projects", "Internships", "Resume Skills"})
        self.assertNotEqual(technical["prompt"], interview["prompt"])

    def test_technical_topic_choice(self):
        client, cid = _user("topic")
        for topic in ("DBMS", "Operating Systems", "Web Development"):
            page = client.get(f"/practice/{cid}?mode=technical&topic={topic}").get_data(as_text=True)
            self.assertEqual(_issued(cid)["topic"], topic)
            self.assertIn(f'<option value="{topic}" selected>', page)

    def test_interview_topic_choice_uses_the_resume(self):
        client, cid = _user("focus")
        page = html.unescape(client.get(f"/practice/{cid}?mode=interview&topic=project:0").get_data(as_text=True))
        self.assertIn("Chat App", _issued(cid)["prompt"])
        self.assertIn("Chat App", page)  # listed in the picker
        client.get(f"/practice/{cid}?mode=interview&topic=internship:0")
        self.assertEqual(_issued(cid)["topic"], "Internships")
        client.get(f"/practice/{cid}?mode=interview&topic=behavioral")
        self.assertEqual(_issued(cid)["topic"], "Behavioral")

    def test_switching_topic_replaces_question_without_counting_it(self):
        client, cid = _user("switch")
        client.get(f"/practice/{cid}?mode=technical&topic=DBMS")
        first = db.get_open_issued_question(cid)["id"]
        client.get(f"/practice/{cid}?mode=technical&topic=Python")
        self.assertNotEqual(db.get_open_issued_question(cid)["id"], first)
        self.assertEqual(db.get_issued_question(first)["status"], "switched")
        self.assertEqual(db.get_attempts(cid), [])

    def test_choice_is_remembered_and_refresh_keeps_question(self):
        client, cid = _user("remember")
        client.get(f"/practice/{cid}?mode=technical&topic=OOP")
        first = db.get_open_issued_question(cid)["id"]
        client.get(f"/practice/{cid}")  # e.g. "Next question" / refresh without parameters
        self.assertEqual(db.get_open_issued_question(cid)["id"], first)

    def test_bad_topic_values_fall_back_safely(self):
        client, cid = _user("badtopic")
        for url in ("?mode=technical&topic=<script>", "?mode=interview&topic=project:99", "?mode=nope"):
            self.assertEqual(client.get(f"/practice/{cid}{url}").status_code, 200, url)

    def test_answer_key_never_on_practice_page(self):
        client, cid = _user("leak")
        page = client.get(f"/practice/{cid}?mode=technical&topic=DBMS").get_data(as_text=True)
        question = _issued(cid)
        if question.get("ideal_answer"):
            self.assertNotIn(question["ideal_answer"][:40], html.unescape(page))

    def test_dashboard_practice_links_target_the_topic(self):
        from app import practice_url
        with app.test_request_context():
            self.assertIn("mode=technical", practice_url(1, "DBMS"))
            self.assertIn("topic=DBMS", practice_url(1, "DBMS"))
            self.assertIn("mode=interview", practice_url(1, "Behavioral"))


class ScoringTests(unittest.TestCase):
    Q = next(q for q in json.load(open("data/question_bank.json")) if q["id"] == "q013")

    def test_synonyms_and_typos_are_accepted(self):
        answer = ("TCP is conection oriented and relaible, it does a handshake and resends lost packets in order; "
                  "UDP is conectionless with no garantees but faster, so it's used for streaming and games.")
        self.assertGreaterEqual(evaluator.rubric_details(self.Q, answer)["score"], 75)

    def test_wrong_answer_stays_low(self):
        self.assertLess(evaluator.rubric_details(self.Q, "TCP is for sending text and UDP is for sending pictures.")["score"], 40)

    def test_realistic_answer_set(self):
        from validation.datasets.answers import ANSWERS
        bank = {q["id"]: q for q in json.load(open("data/question_bank.json"))}
        band = lambda s: "high" if s >= 75 else ("mid" if s >= 40 else "low")  # noqa: E731
        hits = sum(band(evaluator.rubric_details(bank[q], a)["score"]) == b for q, b, a in ANSWERS)
        self.assertGreaterEqual(hits / len(ANSWERS), 0.85)

    def test_partial_credit_and_feedback_parts(self):
        result = evaluator.evaluate_answer_detailed(self.Q, "TCP is reliable and ordered, UDP is not, but it has lower latency.")
        self.assertTrue(result["model_answer"])
        self.assertTrue(result["improvements"])
        self.assertTrue(result["missing"])

    def test_question_echo_is_not_credit(self):
        q = next(q for q in json.load(open("data/question_bank.json")) if q["id"] == "q002")
        self.assertLess(evaluator.rubric_details(q, "Hash tables never have collisions because every key is unique.")["score"], 40)

    def test_result_page_shows_key_points_and_model_answer(self):
        client, cid = _user("result")
        client.get(f"/practice/{cid}?mode=technical&topic=Computer Networks")
        issue = db.get_open_issued_question(cid)
        while issue["question"].get("type") == "mcq":
            client.post(f"/practice/{cid}/skip", data={"issue_id": issue["id"]})
            client.get(f"/practice/{cid}")
            issue = db.get_open_issued_question(cid)
        page = client.post(f"/practice/{cid}/submit", data={"issue_id": issue["id"], "answer_text": "It uses packets and a handshake."}).get_data(as_text=True)
        self.assertIn("concept-chips", page)
        self.assertIn("Model answer", page)
        self.assertIn("How to improve", page)

    def test_ai_grader_prompt_includes_alternatives_and_reference(self):
        from services import llm_service
        seen = {}

        def fake(system, user, **_):
            seen["system"], seen["user"] = system, user
            return {"score": 80, "feedback": "Good.", "covered": ["reliable"], "partial": [], "missing": [],
                    "strengths": ["Clear"], "improvements": ["Add ordering"], "incorrect": ["UDP is reliable"]}

        with mock.patch.object(llm_service, "_get_client", return_value=object()), \
                mock.patch.object(llm_service, "request_json", side_effect=fake):
            graded = llm_service.grade_answer(self.Q, "some answer")
        self.assertIn("also acceptable", seen["user"])
        self.assertIn("Reference answer", seen["user"])
        self.assertIn("partial credit", seen["system"])
        self.assertTrue(graded["improvements"][0].startswith("Check this"))


class DisplayNameTests(unittest.TestCase):
    def setUp(self):
        self.mail = Mailbox()
        patcher = mock.patch("auth.send_otp_email", self.mail)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_name_asked_at_sign_up_and_shown(self):
        email = f"named{datetime.utcnow().timestamp()}@example.com"
        client = app.test_client()
        self.assertIn(b'name="display_name"', client.get("/register").data)
        client.post("/register", data={"display_name": "  Amal   T ", "email": email,
                                       "password": "maple7orbit", "confirm_password": "maple7orbit"})
        client.post("/verify-email", data={"email": email, "otp": self.mail.last(email, "verify")})
        self.assertEqual(db.get_user_by_email(email)["display_name"], "Amal T")
        self.assertIn(b"Amal T", client.get("/").data)

    def test_invalid_names_rejected(self):
        for bad in ("A", "x" * 60, "<script>alert(1)</script>", "Bob​"):
            name, problem = auth.clean_display_name(bad)
            if bad == "Bob​":
                self.assertEqual(name, "Bob")
            else:
                self.assertIsNotNone(problem, bad)

    def test_name_can_be_changed_and_is_not_a_login(self):
        client, _ = _user("rename")
        client.post("/account/name", data={"display_name": "New Name"})
        self.assertIn(b"New Name", client.get("/").data)
        self.assertEqual(app.test_client().post("/login", data={"email": "New Name", "password": "secret123"}).status_code, 401)

    def test_users_without_a_name_are_nudged(self):
        email = f"noname{datetime.utcnow().timestamp()}@example.com"
        uid = db.create_user(email, auth.hash_password("secret123"))
        db.mark_user_verified(uid)
        client = app.test_client()
        client.post("/login", data={"email": email, "password": "secret123"})
        self.assertIn(b"Add your name", client.get("/").data)


class LogoTests(unittest.TestCase):
    def test_lightning_logo_and_favicon(self):
        page = app.test_client().get("/login").get_data(as_text=True)
        self.assertIn('class="brand-mark"', page)
        self.assertIn("pw-bolt", page)
        self.assertIn('rel="icon"', page)
        self.assertEqual(app.test_client().get("/static/logo.svg").status_code, 200)


if __name__ == "__main__":
    unittest.main()
