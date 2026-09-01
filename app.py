"""
Main app — wires M1 (parsing) -> M2 (question selection) -> M3 (evaluation)
-> M4 (analytics) -> dashboard, behind a minimal Flask frontend.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "modules" / "profile_parsing"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "question_generation"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "evaluation"))
sys.path.insert(0, str(Path(__file__).parent / "modules" / "analytics"))

import json
from flask import Flask, render_template, request, redirect, url_for, flash

import database as db
from extract_text import extract_text
from parser import parse_resume
import generator
import evaluator
import analytics

app = Flask(__name__)
app.secret_key = "dev-secret-change-this-for-real-deployment"

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(Path(__file__).parent / "data").mkdir(exist_ok=True)

db.init_db()


@app.route("/")
def home():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("resume")
    if not file or file.filename == "":
        flash("Please choose a resume file (.pdf or .docx).")
        return redirect(url_for("home"))

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        flash("Only .pdf and .docx resumes are supported right now.")
        return redirect(url_for("home"))

    save_path = UPLOAD_DIR / file.filename
    file.save(save_path)

    raw_text = extract_text(str(save_path))
    profile = parse_resume(raw_text, source_file=file.filename)
    candidate_id = db.save_candidate(profile)

    return redirect(url_for("dashboard", candidate_id=candidate_id))


@app.route("/dashboard/<int:candidate_id>")
def dashboard(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)

    topic_scores = analytics.compute_topic_scores(attempts)
    weak_topics = analytics.get_weak_topics(topic_scores)
    strong_topics = analytics.get_strong_topics(topic_scores)
    recommendations = analytics.recommend_next_steps(weak_topics, topic_scores)

    avg_score = round(sum(topic_scores.values()) / len(topic_scores), 1) if topic_scores else 0

    return render_template(
        "dashboard.html",
        candidate=candidate,
        profile=profile,
        attempts=attempts,
        topic_scores=topic_scores,
        weak_topics=weak_topics,
        strong_topics=strong_topics,
        recommendations=recommendations,
        avg_score=avg_score,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/practice/<int:candidate_id>")
def practice(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    topic_scores = analytics.compute_topic_scores(attempts)
    weak_topics = analytics.get_weak_topics(topic_scores)
    answered_ids = db.get_answered_question_ids(candidate_id)

    question = generator.pick_next_question(
        profile_skills=profile.get("skills", []),
        weak_topics=weak_topics,
        answered_ids=answered_ids,
    )

    if not question:
        flash("You've answered every question in the bank — nice work. Check your dashboard.")
        return redirect(url_for("dashboard", candidate_id=candidate_id))

    import json as _json
    return render_template(
        "practice.html",
        candidate_id=candidate_id,
        question=question,
        question_json=_json.dumps(question),
        candidate_id_for_nav=candidate_id,
    )


@app.route("/practice/<int:candidate_id>/submit", methods=["POST"])
def submit_answer(candidate_id):
    question_id = request.form.get("question_id")
    answer_text = request.form.get("answer_text", "")

    # Try the static bank first; fall back to the embedded JSON payload
    # (used for LLM-generated questions that aren't stored in the bank).
    question = generator.get_question_by_id(question_id)
    if not question:
        question_json_str = request.form.get("question_json", "")
        if question_json_str:
            try:
                question = json.loads(question_json_str)
            except (ValueError, TypeError):
                question = None

    if not question:
        flash("That question could not be found.")
        return redirect(url_for("practice", candidate_id=candidate_id))

    score, feedback = evaluator.evaluate_answer(question, answer_text)
    db.save_attempt(candidate_id, question_id, question["topic"], answer_text, score, feedback)

    return render_template(
        "result.html",
        candidate_id=candidate_id,
        question=question,
        answer_text=answer_text,
        score=score,
        feedback=feedback,
        candidate_id_for_nav=candidate_id,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
