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
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

import database as db
from extract_text import extract_text
from parser import parse_resume
import generator
import evaluator
import analytics
from services.resume_feedback import analyze_resume_feedback
from modules.coding.problem_generator import generate_dsa_problem, validate_problem_schema, public_problem
from modules.coding.runner import run_candidate_code, evaluate_submission

app = Flask(__name__)
app.secret_key = "dev-secret-change-this-for-real-deployment"

import auth

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return auth.User.get(int(user_id))

@app.template_filter("topic")
def format_topic(value):
    """Display helper: 'dynamic_programming' -> 'Dynamic Programming', but keep 'SQL' / 'System Design' as-is."""
    text = str(value or "").replace("_", " ").strip()
    return text.title() if text.islower() else text


@app.template_filter("as_json")
def as_json(value):
    """Readable JSON for display (autoescaped by Jinja, unlike |tojson which emits \\u0027 etc.)."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


@app.context_processor
def static_version():
    """Cache-bust static assets: the URL changes whenever style.css changes."""
    def asset_version(filename):
        try:
            return int((Path(app.static_folder) / filename).stat().st_mtime)
        except OSError:
            return 0
    return {"asset_version": asset_version}


UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
(Path(__file__).parent / "data").mkdir(exist_ok=True)

db.init_db()


def _restore_and_save_profile(profile_data, user_id: int) -> int:
    """Deserialise a CandidateProfile that was serialised to the session as JSON
    and save it as a new candidate row, returning the candidate_id."""
    import json as _json
    from modules.profile_parsing.schema import CandidateProfile, ContactInfo, Education, Project

    if isinstance(profile_data, str):
        profile_data = _json.loads(profile_data)

    # Reconstruct nested dataclasses from dicts
    raw = profile_data
    contact = raw.get("contact", {})
    if isinstance(contact, dict):
        raw["contact"] = ContactInfo(**{k: v for k, v in contact.items() if k in ContactInfo.__dataclass_fields__})
    education = raw.get("education", [])
    raw["education"] = [
        Education(**{k: v for k, v in e.items() if k in Education.__dataclass_fields__})
        if isinstance(e, dict) else e
        for e in education
    ]
    projects = raw.get("projects", [])
    raw["projects"] = [
        Project(**{k: v for k, v in p.items() if k in Project.__dataclass_fields__})
        if isinstance(p, dict) else p
        for p in projects
    ]
    allowed = CandidateProfile.__dataclass_fields__
    profile = CandidateProfile(**{k: v for k, v in raw.items() if k in allowed})
    return db.save_candidate(user_id, profile)


@app.route("/")
def home():
    return render_template("upload.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Guard: already-logged-in users have nothing to do here
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))
            
        existing = db.get_user_by_email(email)
        if existing:
            flash("Email already registered.", "error")
            return redirect(url_for("register"))
            
        hashed = auth.hash_password(password)
        user_id = db.create_user(email, hashed)
        
        otp = auth.generate_otp()
        expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        db.set_user_otp(user_id, otp, expires)
        auth.send_otp_email(email, otp)
        
        return redirect(url_for("verify_email", user_id=user_id, email=email))
    return render_template("auth/register.html")


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    user_id = request.args.get("user_id", type=int)
    email = request.args.get("email", "")

    if request.method == "POST":
        user_id = request.form.get("user_id", user_id, type=int)
        email = request.form.get("email", email)
        otp = request.form.get("otp", "").strip()
        if not user_id or not otp:
            flash("Invalid request.", "error")
            return redirect(url_for("register"))
        if db.verify_user_otp(user_id, otp):
            user_row = db.get_user_by_id(user_id)
            user = auth.User(user_row)
            login_user(user)
            if "pending_profile" in session:
                profile_data = session.pop("pending_profile")
                candidate_id = _restore_and_save_profile(profile_data, user.id)
                return redirect(url_for("verify_profile", candidate_id=candidate_id))
            flash("Email verified! You are now logged in.", "success")
            return redirect(url_for("home"))
        else:
            flash("Invalid or expired code. Please try again.", "error")
            return render_template("auth/verify_email.html", user_id=user_id, email=email)

    return render_template("auth/verify_email.html", user_id=user_id, email=email)


@app.route("/login", methods=["GET", "POST"])
def login():
    # Guard: already-logged-in users should not see the login page
    if current_user.is_authenticated:
        return redirect(request.args.get("next") or url_for("home"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        next_url = request.form.get("next") or url_for("home")
        user_row = db.get_user_by_email(email)
        if user_row and auth.check_password(password, user_row["password_hash"]):
            if not user_row["is_verified"]:
                flash("Please verify your email first.", "error")
                return redirect(url_for("verify_email", user_id=user_row["id"], email=email))
            user = auth.User(user_row)
            login_user(user)
            if "pending_profile" in session:
                profile_data = session.pop("pending_profile")
                candidate_id = _restore_and_save_profile(profile_data, user.id)
                return redirect(url_for("verify_profile", candidate_id=candidate_id))
            return redirect(next_url)
        flash("Invalid email or password.", "error")
    return render_template("auth/login.html", next=request.args.get("next", ""))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


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
    
    if current_user.is_authenticated:
        candidate_id = db.save_candidate(current_user.id, profile)
        return redirect(url_for("verify_profile", candidate_id=candidate_id))
    else:
        session["pending_profile"] = profile.to_json()
        flash("Please sign up or log in to view your resume analysis.", "success")
        return redirect(url_for("register"))


@app.route("/verify-profile/<int:candidate_id>", methods=["GET", "POST"])
@login_required
def verify_profile(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate["user_id"] != current_user.id:
        flash("Candidate not found or unauthorized.", "error")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])

    if request.method == "POST":
        # Contact
        profile["contact"]["name"] = request.form.get("contact_name")
        profile["contact"]["email"] = request.form.get("contact_email")
        profile["contact"]["phone"] = request.form.get("contact_phone")

        # Skills
        skills_raw = request.form.get("skills", "")
        profile["skills"] = [s.strip() for s in skills_raw.split(",") if s.strip()]

        # Education
        education = []
        for key in request.form:
            if key.startswith("edu_institution_"):
                idx = key.split("_")[-1]
                education.append({
                    "institution": request.form.get(f"edu_institution_{idx}"),
                    "degree": request.form.get(f"edu_degree_{idx}"),
                    "field_of_study": request.form.get(f"edu_field_{idx}"),
                })
        profile["education"] = education

        # Projects
        projects = []
        for key in request.form:
            if key.startswith("proj_title_"):
                idx = key.split("_")[-1]
                tech_raw = request.form.get(f"proj_tech_{idx}", "")
                projects.append({
                    "title": request.form.get(f"proj_title_{idx}"),
                    "description": request.form.get(f"proj_desc_{idx}"),
                    "tech_stack": [t.strip() for t in tech_raw.split(",") if t.strip()]
                })
        profile["projects"] = projects

        db.update_candidate_profile(candidate_id, profile)
        return redirect(url_for("dashboard", candidate_id=candidate_id))

    return render_template("verify_profile.html", candidate=candidate, profile=profile)


@app.route("/dashboard/<int:candidate_id>")
@login_required
def dashboard(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    resume_feedback = db.get_resume_feedback(candidate_id)

    if resume_feedback is None:
        parsed_profile = parse_resume(extract_text(str(Path(__file__).parent / "uploads" / (candidate["name"] or "resume.txt"))), source_file="stored_profile") if False else None
        try:
            resume_feedback = analyze_resume_feedback(profile)
            db.save_resume_feedback(candidate_id, resume_feedback)
        except Exception:
            resume_feedback = {
                "overall_score": 0,
                "category_scores": {},
                "strengths": [],
                "weaknesses": ["Resume analysis could not be generated."],
                "suggestions": ["Reupload the resume to regenerate the review."],
                "summary": "Resume analysis needs regeneration.",
            }

    interview_scores = analytics.compute_topic_scores(attempts)
    topic_scores = analytics.combine_practice_scores(interview_scores, dsa_performance["topic_scores"])
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
        dsa_performance=dsa_performance,
        resume_feedback=resume_feedback,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/api/dashboard/<int:candidate_id>")
def dashboard_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    interview_scores = analytics.compute_topic_scores(attempts)
    dsa_performance = db.get_dsa_performance(candidate_id)
    topic_scores = analytics.combine_practice_scores(interview_scores, dsa_performance["topic_scores"])
    return jsonify({
        "profile": profile,
        "projects": profile.get("projects", []),
        "skills": profile.get("skills", []),
        "experience": profile.get("experience", []),
        "internships": profile.get("internships", []),
        "research_experience": [entry for entry in profile.get("experience", []) if entry.get("type") == "research"],
        "education": profile.get("education", []),
        "interview": {
            "attempted": len(attempts),
            "average_score": round(sum(topic_scores.values()) / len(topic_scores), 1) if topic_scores else 0,
        },
        "dsa": dsa_performance,
        "skill_gaps": topic_scores,
    })


@app.route("/api/profile/<int:candidate_id>", methods=["GET", "PUT"])
def profile_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404

    if request.method == "GET":
        return jsonify(json.loads(candidate["profile_json"]))

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Profile JSON object is required."}), 400
    contact = payload.get("contact")
    if not isinstance(contact, dict):
        return jsonify({"error": "Profile contact object is required."}), 400
    if not isinstance(payload.get("skills", []), list):
        return jsonify({"error": "Profile skills must be a list."}), 400
    if not db.update_candidate_profile(candidate_id, payload):
        return jsonify({"error": "Candidate not found."}), 404
    return jsonify(payload)


@app.route("/api/resume-feedback/<int:candidate_id>")
def resume_feedback_api(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404

    feedback = db.get_resume_feedback(candidate_id)
    if feedback is None:
        profile = json.loads(candidate["profile_json"])
        feedback = analyze_resume_feedback(profile)
        db.save_resume_feedback(candidate_id, feedback)
    return jsonify(feedback)


@app.route("/practice/<int:candidate_id>")
@login_required
def practice(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))

    profile = json.loads(candidate["profile_json"])
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    topic_scores = analytics.combine_practice_scores(
        analytics.compute_topic_scores(attempts),
        dsa_performance["topic_scores"],
    )
    weak_topics = analytics.get_weak_topics(topic_scores)
    answered_ids = db.get_answered_question_ids(candidate_id)

    question = generator.pick_next_question(
        profile_skills=profile.get("skills", []),
        weak_topics=weak_topics,
        answered_ids=answered_ids,
        profile=profile,
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
@login_required
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


@app.route("/questions/generate", methods=["POST"])
def generate_question_api():
    payload = request.get_json(silent=True) or {}
    profile = payload.get("profile") or {}
    skills = profile.get("skills") or []
    weak_topics = payload.get("weak_topics") or []
    answered_ids = payload.get("answered_ids") or []
    question = generator.pick_next_question(skills, weak_topics, set(answered_ids), profile=profile)
    if question is None:
        return jsonify({"error": "No question available."}), 404
    return jsonify(question)


@app.route("/questions/evaluate", methods=["POST"])
def evaluate_question_api():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question") or {}
    answer_text = payload.get("answer_text") or ""
    score, feedback = evaluator.evaluate_answer(question, answer_text)
    return jsonify({
        "score": score,
        "feedback": feedback,
        "strengths": ["Clear explanation", "Good project context"] if score >= 70 else ["Need more depth"],
        "weaknesses": ["Could be more specific"] if score < 70 else [],
        "improved_answer": answer_text,
    })


@app.route("/dsa/<int:candidate_id>")
@login_required
def dsa_practice(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        flash("Candidate not found.")
        return redirect(url_for("home"))
    return render_template(
        "dsa_practice.html",
        candidate_id=candidate_id,
        problem=None,
        dsa_performance=db.get_dsa_performance(candidate_id),
        candidate_id_for_nav=candidate_id,
    )


@app.route("/dsa/<int:candidate_id>/generate", methods=["POST"])
@login_required
def generate_dsa(candidate_id):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    profile = json.loads(candidate["profile_json"])
    difficulty = (request.form.get("difficulty") or "medium").lower()
    topic = (request.form.get("topic") or "arrays").lower()
    language = request.form.get("language") or "Python"
    previous_hashes = db.get_recent_coding_hashes(candidate_id, topic, difficulty)
    problem = generate_dsa_problem(profile, difficulty, topic, language, previous_hashes=previous_hashes)
    if not validate_problem_schema(problem):
        flash("The generated problem failed validation. Please try again.")
        return redirect(url_for("dsa_practice", candidate_id=candidate_id))
    db.save_coding_problem(problem["id"], candidate_id, problem)
    problem_for_view = public_problem(problem)
    return render_template(
        "dsa_practice.html",
        candidate_id=candidate_id,
        problem=problem_for_view,
        dsa_performance=db.get_dsa_performance(candidate_id),
        candidate_id_for_nav=candidate_id,
    )


def _stored_problem(problem_id: str, candidate_id: int):
    stored = db.get_coding_problem(problem_id)
    if not stored or stored["candidate_id"] != candidate_id:
        return None
    return stored["problem"]


@app.route("/dsa/<int:candidate_id>/run", methods=["POST"])
def run_dsa(candidate_id):
    problem_id = request.form.get("problem_id")
    problem = _stored_problem(problem_id, candidate_id) if problem_id else None
    if not problem:
        return jsonify({"error": "Problem not found."}), 404
    return jsonify(run_candidate_code(problem, request.form.get("code", "")))


@app.route("/dsa/<int:candidate_id>/submit", methods=["POST"])
def submit_dsa(candidate_id):
    problem_id = request.form.get("problem_id")
    problem = _stored_problem(problem_id, candidate_id) if problem_id else None
    if not problem:
        flash("That coding problem could not be found.")
        return redirect(url_for("dsa_practice", candidate_id=candidate_id))
    result = evaluate_submission(problem, request.form.get("code", ""))
    db.save_coding_submission(
        candidate_id,
        problem_id,
        request.form.get("code", ""),
        result.get("passed_tests", 0),
        result.get("total_tests", 0),
        result.get("coding_score", 0),
        result.get("execution_time", 0),
        result.get("memory_usage", 0),
        result.get("status", "incorrect"),
        result.get("feedback", ""),
    )
    return render_template(
        "dsa_result.html",
        candidate_id=candidate_id,
        problem=problem,
        result=result,
        candidate_id_for_nav=candidate_id,
    )


@app.route("/coding/problems/generate", methods=["POST"])
def generate_coding_problem_api():
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id")
    profile = payload.get("profile") or {}
    difficulty = (payload.get("difficulty") or "medium").lower()
    topic = (payload.get("topic") or "arrays").lower()
    language = (payload.get("language") or profile.get("preferred_language") or "python").lower()
    previous_hashes = db.get_recent_coding_hashes(candidate_id, topic, difficulty) if candidate_id is not None else []
    problem = generate_dsa_problem(profile=profile, difficulty=difficulty, topic=topic, language=language, previous_hashes=previous_hashes)
    if not validate_problem_schema(problem):
        return jsonify({"error": "Generated problem failed validation."}), 400
    if candidate_id is not None:
        db.save_coding_problem(problem["id"], candidate_id, problem)
    public = public_problem(problem)
    return jsonify({"problem": public, "problem_id": problem["id"]})


@app.route("/coding/run", methods=["POST"])
@login_required
def run_coding_api():
    payload = request.get_json(silent=True) or {}
    problem = payload.get("problem") or {}
    code = payload.get("code") or ""
    result = run_candidate_code(problem, code)
    return jsonify(result)


@app.route("/coding/submit", methods=["POST"])
@login_required
def submit_coding_api():
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id")
    problem_id = payload.get("problem_id")
    problem = payload.get("problem") or {}
    if problem_id and not problem:
        conn = db.get_conn()
        row = conn.execute("SELECT problem_json FROM coding_problems WHERE id = %s", (problem_id,)).fetchone()
        conn.close()
        if row:
            problem = json.loads(row["problem_json"])
    code = payload.get("code") or ""
    result = evaluate_submission(problem, code)
    if candidate_id is not None and problem_id:
        db.save_coding_submission(candidate_id, problem_id, code, result.get("passed_tests", 0), result.get("total_tests", 0), result.get("coding_score", 0), result.get("execution_time", 0), result.get("memory_usage", 0), result.get("status", "incorrect"), result.get("feedback", ""))
    return jsonify(result)


@app.route("/performance")
def performance_api():
    candidate_id = request.args.get("candidate_id", type=int)
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    topic_scores = analytics.combine_practice_scores(
        analytics.compute_topic_scores(attempts),
        dsa_performance["topic_scores"],
    )
    return jsonify({
        "candidate_id": candidate_id,
        "overall_score": round(sum(topic_scores.values()) / len(topic_scores), 1) if topic_scores else 0,
        "topic_scores": topic_scores,
        "attempt_count": len(attempts),
    })


@app.route("/skill-gaps")
def skill_gaps_api():
    candidate_id = request.args.get("candidate_id", type=int)
    if candidate_id is None:
        return jsonify({"error": "candidate_id is required."}), 400
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found."}), 404
    attempts = db.get_attempts(candidate_id)
    dsa_performance = db.get_dsa_performance(candidate_id)
    topic_scores = analytics.combine_practice_scores(
        analytics.compute_topic_scores(attempts),
        dsa_performance["topic_scores"],
    )
    weak_topics = analytics.get_weak_topics(topic_scores)
    strong_topics = analytics.get_strong_topics(topic_scores)
    recommendations = analytics.recommend_next_steps(weak_topics, topic_scores)
    return jsonify({
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "recommended_learning": recommendations,
        "topic_scores": topic_scores,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
