# Placement Prep Agent — Working Prototype

This is a functional end-to-end slice of the full project: **upload a
resume → get a parsed profile → practice real questions → get scored
with feedback → see it all on a live dashboard.** Roughly half the PRD's
functional requirements are genuinely implemented here; the rest are
clearly marked stand-ins with a documented upgrade path.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**, upload `sample_resume.pdf` (or
`sample_resume.docx`, included in this folder) and click through the
flow.

## What's real vs. what's a stand-in

| Module | Status | Notes |
|---|---|---|
| **M1 — Profile Parsing** | ✅ Real | Same code from your earlier module: PDF/DOCX → structured profile, section-splitting + regex + keyword matching. No changes needed here to keep this demo working. |
| **M2 — Question Generation** | 🟡 Stand-in | Picks from a curated 20-question bank (`data/question_bank.json`) biased toward weak areas and resume skills — not a real RAG/LLM pipeline. `modules/question_generation/generator.py`'s `pick_next_question()` is the exact function boundary to replace with a real LLM call once you have an API key. Nothing downstream needs to change if the replacement returns the same `{id, topic, type, difficulty, prompt, ...}` shape. |
| **M3 — Evaluation & Feedback** | 🟡 Stand-in | MCQ = exact match. Short answer = keyword-overlap against a rubric (each question's `keywords` list). This is real scoring, just not LLM-based — it genuinely fails answers that don't cover the right concepts (try it). `evaluator.py`'s `evaluate_answer()` is the swap point for an LLM grader later. |
| **M4 — Analytics & Recommendation** | ✅ Real | Aggregates actual attempt scores per topic, flags anything under 50% as weak, generates recommendations from real data — not hardcoded. |
| **M5 — Dashboard** | ✅ Real | Profile summary, skill fingerprint, weak areas, recommendations, and activity all render from live data, not mockup placeholders. This is the same visual design as the standalone dashboard mockup shared earlier, now wired to a real backend. |

**Why stand-ins instead of the real thing for M2/M3:** those need an LLM
API key your team hasn't set up yet, and getting the *structure* right
(how modules hand data to each other, what the dashboard needs, how
scoring flows into weak-area detection) doesn't require it. Swapping in
real LLM calls later is a contained change in two files, not a rewrite.

## Project structure

```
app.py                          — Flask app, wires everything together
database.py                     — SQLite storage (swap for MySQL/Postgres per PRD later)
data/question_bank.json         — M2's question bank
modules/
  profile_parsing/              — M1 (Joyal's module, unchanged)
  question_generation/          — M2 stand-in (Aiswarya's module — replace generator.py)
  evaluation/                   — M3 stand-in (Nihal's module — replace evaluator.py)
  analytics/                    — M4 (Pulikanti's module, real logic)
templates/                      — dashboard, upload, practice, result pages
static/style.css                — shared design system
sample_resume.pdf/.docx         — test fixtures
```

## What each person should actually do with this

- **Joyal (M1):** already done — this just imports your existing code unchanged. If you improve education parsing (per your module's README), it'll flow through automatically.
- **Aiswarya (M2):** replace `generator.py`'s `pick_next_question()` with a real RAG/LLM pipeline. Keep the return shape the same and nothing else breaks.
- **Nihal (M3):** replace `evaluator.py`'s `evaluate_answer()` with LLM-based grading, especially for the cases keyword-matching gets wrong (right concept, different wording). Keep the `(score, feedback)` return signature.
- **Pulikanti (M4/M5):** the analytics logic and dashboard are real — from here it's about refining recommendation quality and polishing the frontend, not rebuilding the pipeline.

## Known limitations (be upfront about these in your review)

- SQLite, not a production DB — fine for a demo, swap per the PRD's tech stack for anything beyond that
- No authentication — anyone can view any candidate_id by URL
- Keyword-rubric grading will mark a correct answer wrong if it uses different wording than the rubric's keyword list — this is the single most visible limitation to explain in a demo, not hide
- Education parsing still only pulls CGPA + raw text, not structured degree/institution (per M1's own README)
