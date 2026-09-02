# Placement Prep Prototype

An AI-powered placement preparation tool that personalises technical interview practice to a candidate's resume. Upload your resume, get questions matched to your skills and weak areas, answer them, and track your progress on a live dashboard.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Modules — What Is Implemented](#modules--what-is-implemented)
   - [M1 — Profile Parsing](#m1--profile-parsing)
   - [M2 — Question Generation](#m2--question-generation)
   - [M3 — Evaluation & Feedback](#m3--evaluation--feedback-current-stand-in)
   - [M4 — Analytics & Recommendations](#m4--analytics--recommendations)
4. [M3 Upgrade — ML Training Workspace](#m3-upgrade--ml-training-workspace)
5. [Storage Layer](#storage-layer)
6. [Frontend](#frontend)
7. [Question Bank](#question-bank)
8. [Quick Start](#quick-start)
9. [Environment Variables](#environment-variables)
10. [Project File Map](#project-file-map)
11. [Limitations & Known Issues](#limitations--known-issues)
12. [Roadmap — What Is Left](#roadmap--what-is-left)

---

## Project Overview

This is a **Final Year Project** prototype demonstrating an end-to-end AI pipeline for placement preparation:

- A student uploads their **resume (PDF or DOCX)**
- The system **parses** it to extract their skills, education, and projects
- It **generates personalised interview questions** — via the Groq API (LLaMA3-70B, tailored to the candidate's profile) or a curated static question bank as fallback
- The student **answers** questions in a web interface
- Their answers are **evaluated** and scored with feedback
- A **dashboard** tracks topic-level performance, identifies weak areas, and recommends what to practice next

**Stack:** Python 3.10, Flask, SQLite, Groq API (LLaMA3-70B), Anthropic API (training data generation only), scikit-learn, HuggingFace Transformers (T5), PyTorch.

---

## System Architecture

```
+-------------+     +------------------+     +----------------------+
|   Resume    |---->|  M1: Profile     |---->|  M2: Question        |
|  (PDF/DOCX) |     |  Parsing         |     |  Generation          |
+-------------+     |  (regex + LLM)   |     |  (Groq LLM + bank)   |
                    +------------------+     +-----------+----------+
                                                         |
                                                         v (question)
                    +------------------+     +----------------------+
                    |  M4: Analytics   |<----|  M3: Evaluation      |
                    |  & Dashboard     |     |  (keyword rubric now;|
                    |                  |     |  ML model planned)   |
                    +------------------+     +----------------------+
                             |
                    +---------v--------+
                    |  SQLite Database |
                    |  candidates +    |
                    |  attempts tables |
                    +------------------+
```

All modules are wired together in `app.py`, a Flask app exposing five routes:
`/`, `/upload`, `/dashboard/<id>`, `/practice/<id>`, `/practice/<id>/submit`.

---

## Modules — What Is Implemented

### M1 — Profile Parsing

**Location:** `modules/profile_parsing/`

Turns a raw resume file into a structured `CandidateProfile` object.

#### Files

| File | Purpose |
|------|---------|
| `extract_text.py` | Reads PDF (via `pdfminer`) and DOCX (via `python-docx`), returns plain text |
| `parser.py` | Main parsing logic — section splitting, field extraction |
| `schema.py` | Dataclass definitions: `CandidateProfile`, `ContactInfo`, `Education`, `Project` |
| `skills_taxonomy.py` | 60+ canonical skills across 5 categories for keyword matching |

#### How parsing works

1. **Contact extraction** — regex scans the first 15 lines for email and phone; name is inferred from the first 2–4-word capitalised line
2. **Section splitting** — identifies headers (`Education`, `Skills`, `Projects`, `Experience`) and assigns lines to the correct bucket
3. **Skill extraction** — word-boundary regex scan of the full resume against `ALL_SKILLS` (languages, frameworks, databases, tools, CS fundamentals)
4. **Project extraction**:
   - *Primary:* Calls Groq LLM to parse the projects section into structured `{title, description, tech_stack}` JSON
   - *Fallback:* Heuristic block-splitter (short line = title, rest = description)
5. **Confidence scoring** — `ContactInfo` carries a `confidence` float (0–1); uncertain fields go into `profile.needs_review`

#### Output schema

```
CandidateProfile
  contact:        ContactInfo     # name, email, phone, confidence
  skills:         List[str]       # e.g. ["Python", "Flask", "MySQL"]
  education:      List[Education] # institution, degree, cgpa, raw_text
  projects:       List[Project]   # title, description, tech_stack, llm_extracted
  experience_raw: List[str]       # raw lines (unstructured)
  needs_review:   List[str]       # field names parser was unsure about
```

---

### M2 — Question Generation

**Location:** `modules/question_generation/generator.py`

Selects or generates the next question for the candidate to answer.

#### Primary path — Groq LLM (llama3-70b-8192)

When `GROQ_API_KEY` is set, the module sends the candidate's skills, weak topics, and already-answered topics to the LLM, which returns a personalised question:

```json
{
  "id": "gen-abc12345-1725000000",
  "topic": "Python",
  "type": "short_answer",
  "difficulty": "medium",
  "prompt": "Explain how Python's GIL affects multi-threaded programs.",
  "keywords": ["global interpreter lock", "thread", "CPU-bound", "I/O-bound", "multiprocessing"]
}
```

The LLM is prompted to prioritise weak topics, avoid already-covered topics, and always output strict JSON.

#### Fallback path — Static question bank

If no API key is present or the call fails, picks from `data/question_bank.json` by priority:
1. Weak-topic questions first
2. Skill-matched questions
3. Any unanswered question

#### Public API (stable — signature must not change)

```python
pick_next_question(profile_skills, weak_topics, answered_ids) -> dict | None
get_question_by_id(question_id) -> dict | None
```

LLM-generated questions (IDs start with `gen-`) are ephemeral — not in the bank — but the full question JSON is embedded in the practice form and retrieved on submission.

---

### M3 — Evaluation & Feedback *(current stand-in)*

**Location:** `modules/evaluation/evaluator.py`

Evaluates a candidate's answer and returns a score and feedback string.

#### MCQ (exact match)
```
Score = 100.0 if answer matches exactly, else 0.0
```

#### Short answer (keyword-overlap rubric)
Each question in the bank has a `keywords` list (4–7 key concepts). The evaluator counts how many appear in the candidate's answer:

```
Score = (matched keywords / total keywords) x 100
```

Feedback = verdict (Strong / Partially correct / Missing most concepts) + up to 4 missing keywords as improvement hints.

#### Stable return signature
```python
evaluate_answer(question: dict, answer_text: str) -> (score: float, feedback: str)
```

> This is a deliberate stand-in. The keyword rubric is fast and explainable but will miss paraphrased correct answers. `m3_upgrade/` contains the ML replacement.

---

### M4 — Analytics & Recommendations

**Location:** `modules/analytics/analytics.py`

Pure functions over attempt data — no database access, fully testable in isolation.

| Function | What it does |
|----------|-------------|
| `compute_topic_scores(attempts)` | Averages all scores per topic |
| `get_weak_topics(topic_scores)` | Topics below 50% average |
| `get_strong_topics(topic_scores)` | Topics above 75% average |
| `recommend_next_steps(weak_topics, topic_scores)` | One actionable recommendation per weak topic |

The dashboard shows these alongside the attempt history and overall average score.

---

## M3 Upgrade — ML Training Workspace

**Location:** `m3_upgrade/`

An **offline training workspace** that will replace the keyword-rubric evaluator with two trained ML models. Nothing here runs at inference time — only the saved model files it produces get loaded by `evaluator.py` after training.

### What gets replaced

- Keyword-overlap scorer → **trained regression model** (predicts score from question + answer semantically)
- Template feedback string → **fine-tuned T5 model** (generates natural-language feedback)

### Training data schema

```jsonl
{"question": "...", "answer": "...", "score": 8.5, "max_score": 10.0, "band": "excellent", "feedback": "..."}
```

Four bands: `poor` (0–3.5), `needs_improvement` (4–6), `good` (6.5–8), `excellent` (8.5–10).

### Components

#### `data/seed_dataset.jsonl`
24 hand-written training examples covering 7 topics across all 4 quality bands. Used for smoke-testing without API credits.

#### `data_generation/generate_dataset.py`
Uses the Anthropic API (Claude) to bootstrap synthetic training data at scale.
Needs `ANTHROPIC_API_KEY` and internet access. Target: 500–1000 rows in `feedback_dataset.jsonl`.

#### `scorer/train_scorer.py`
Trains a score-prediction model.

| Backend | Description | Status |
|---------|-------------|--------|
| `tfidf` | TF-IDF (1–2gram) + Ridge regression. No internet. **Baseline.** | Smoke-tested: Pearson r = 0.63 on seed |
| `embeddings` | `all-MiniLM-L6-v2` sentence embeddings + Ridge. **Main model.** | Needs internet (~90MB download) |

Reports **Pearson r** and **Quadratic Weighted Kappa (QWK)** — standard ASAG metrics.

#### `feedback_generator/train_feedback_model.py`
Fine-tunes T5-small (60M params) to generate feedback text.

| Backend | Description |
|---------|-------------|
| `pretrained` | Fine-tunes `t5-small`. Recommended. Coherent output from a few hundred examples. |
| `scratch` | Trains from random init. More generic output. Good comparison baseline for the report. |

#### `shared/metrics.py`
- `pearson_correlation` — linear score tracking
- `quadratic_weighted_kappa` — standard competition metric, penalises large misses
- `rouge_l` — LCS-based F1 for evaluating generated feedback

#### `feedback_generator/smoke_test_pipeline.py`
Torch-free pipeline validator — checks data loading, formatting, tokenizer training, and ROUGE-L without needing a working PyTorch install.

---

## Storage Layer

**File:** `database.py`

SQLite at `data/app.db`. Two tables:

```sql
candidates (id, name, email, phone, profile_json, created_at)
attempts   (id, candidate_id, question_id, topic, answer_text, score, feedback, created_at)
```

| Function | Description |
|----------|-------------|
| `init_db()` | Creates tables on startup |
| `save_candidate(profile)` | Inserts candidate, returns ID |
| `get_candidate(id)` | Fetches candidate by ID |
| `save_attempt(...)` | Records one answered question |
| `get_attempts(candidate_id)` | All attempts, newest first |
| `get_answered_question_ids(candidate_id)` | Set of answered question IDs |

---

## Frontend

**Location:** `templates/`

Flask/Jinja2 HTML templates. All pages extend `base.html`.

| Template | Route | Description |
|----------|-------|-------------|
| `upload.html` | `/` | Resume upload form (PDF / DOCX) |
| `dashboard.html` | `/dashboard/<id>` | Topic scores, weak/strong areas, history, recommendations |
| `practice.html` | `/practice/<id>` | Question display with answer input |
| `result.html` | after submit | Score, feedback, next-question link |

---

## Question Bank

**File:** `data/question_bank.json`

20 questions across 8 topics:

**Topics:** Data Structures, Dynamic Programming, DBMS, OOP, Operating Systems, System Design, Computer Networks, Python, Machine Learning

**Types:**
- `short_answer` — free text, scored by keyword rubric (or ML model after upgrade)
- `mcq` — multiple choice with a single correct answer

Each question: `id`, `topic`, `type`, `difficulty` (easy/medium/hard), `prompt`, and either `keywords` (short answer) or `options` + `answer` (MCQ).

---

## Quick Start

```bash
# 1. Navigate to the project
cd prototype

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Groq API key (optional — app works without it)
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# 4. Run
python app.py

# 5. Open http://127.0.0.1:5000
```

Use `sample_resume.pdf` or `sample_resume.docx` (included) to test the full flow.

---

## Environment Variables

| Variable | File | Required | Purpose |
|----------|------|----------|---------|
| `GROQ_API_KEY` | `prototype/.env` | No | LLM question generation and project parsing. Fallback works without it. |
| `ANTHROPIC_API_KEY` | Shell env | Only for training data | Used by `m3_upgrade/data_generation/generate_dataset.py`. Never needed at runtime. |

---

## Project File Map

```
prototype/
|
+-- app.py                          Main Flask app — all 5 routes wired
+-- database.py                     SQLite storage layer
+-- requirements.txt                Runtime dependencies
+-- .env                            GROQ_API_KEY (gitignored)
+-- .env.example                    Template for .env
+-- sample_resume.pdf / .docx       Test resumes
|
+-- data/
|   +-- question_bank.json          20 static fallback questions
|   +-- app.db                      Live SQLite database (gitignored)
|
+-- modules/
|   +-- profile_parsing/            M1
|   |   +-- extract_text.py         PDF/DOCX -> plain text
|   |   +-- parser.py               Text -> CandidateProfile (regex + LLM)
|   |   +-- schema.py               CandidateProfile dataclass
|   |   +-- skills_taxonomy.py      60+ skills, 5 categories
|   |
|   +-- question_generation/        M2
|   |   +-- generator.py            Groq LLM + static bank fallback
|   |
|   +-- evaluation/                 M3 (stand-in)
|   |   +-- evaluator.py            Keyword-overlap -> (score, feedback)
|   |
|   +-- analytics/                  M4
|       +-- analytics.py            Topic scores, weak/strong, recommendations
|
+-- templates/
|   +-- base.html / upload.html / dashboard.html / practice.html / result.html
|
+-- uploads/                        Uploaded resumes (gitignored)
|
+-- m3_upgrade/                     Offline ML training workspace
    +-- README.md                   Detailed plan + 2-week timeline
    +-- requirements.txt            Training deps (torch, transformers, etc.)
    |
    +-- data/
    |   +-- seed_dataset.jsonl      24 hand-written training examples
    |
    +-- data_generation/
    |   +-- generate_dataset.py     Anthropic API -> synthetic training data
    |
    +-- scorer/
    |   +-- train_scorer.py         TF-IDF / embeddings + Ridge scorer
    |   +-- scorer_model.joblib     (after training)
    |
    +-- feedback_generator/
    |   +-- train_feedback_model.py T5 fine-tuning
    |   +-- smoke_test_pipeline.py  Torch-free pipeline validator
    |
    +-- shared/
        +-- metrics.py              Pearson r, QWK, ROUGE-L
```

---

## Limitations & Known Issues

| Area | Limitation |
|------|-----------|
| M3 Evaluator | Keyword-overlap misses paraphrased correct answers — primary motivation for `m3_upgrade` |
| M1 Parser | Name detection is heuristic; education parsing stores raw lines without structured institution/degree |
| Question bank | Only 20 static questions; LLM generation compensates but depends on API availability |
| Analytics | Recommendations are rule-based; no resource links or learning paths |
| Frontend | Templates are functional but unstyled |
| PyTorch on Windows | `c10.dll` DLL error with some torch versions — see fix below |

---

## Roadmap — What Is Left

### Phase 1 — M3 Model Training

| # | Step |
|---|------|
| 1 | Smoke test scorer — DONE (Pearson r = 0.63 on seed) |
| 2 | Smoke test feedback pipeline (torch-free) — DONE |
| 3 | Expand QUESTIONS in `generate_dataset.py` to 25–40 |
| 4 | Run `generate_dataset.py` with ANTHROPIC_API_KEY (target 500–1000 rows) |
| 5 | Spot-check 30 generated examples manually |
| 6 | Train scorer (TF-IDF baseline): `python train_scorer.py --backend tfidf --data ../feedback_dataset.jsonl` |
| 7 | Train scorer (embeddings): `python train_scorer.py --backend embeddings --data ../feedback_dataset.jsonl` |
| 8 | Compare Pearson r and QWK between backends — ML story for the report |
| 9 | Error analysis on scorer |
| 10 | Train feedback generator: `python train_feedback_model.py --backend pretrained --epochs 6` |
| 11 | Evaluate feedback: ROUGE-L + qualitative read of 10–15 generations |

### Phase 2 — Integration

| # | Step |
|---|------|
| 12 | Update `evaluator.py` to load trained models. Keep `(score, feedback)` return signature. |
| 13 | End-to-end test through the full app |

### Phase 3 — Polish

| # | Step |
|---|------|
| 14 | Expand question bank to 50+ questions |
| 15 | Frontend UI improvements |
| 16 | Merge training requirements into root `requirements.txt` |
| 17 | Report write-up: model comparison, feedback generator ceiling, honest limitations |

---

## Fix PyTorch on Windows

If you see `OSError: [WinError 1114] ... c10.dll`:

```bash
# 1. Install Visual C++ 2022 Redistributable (x64) from:
#    https://aka.ms/vs/17/release/vc_redist.x64.exe

# 2. Reinstall compatible torch + transformers
pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu
pip install "transformers==4.36.2"

# 3. Verify
python -c "import torch; import transformers; print(torch.__version__, transformers.__version__)"

# 4. Re-run full feedback smoke test
cd m3_upgrade/feedback_generator
python train_feedback_model.py --data ../data/seed_dataset.jsonl --backend pretrained --smoke-test --epochs 3
```

---

*Built as a Final Year Project prototype. All modules have stable public interfaces so individual components can be upgraded independently without cascading changes.*
