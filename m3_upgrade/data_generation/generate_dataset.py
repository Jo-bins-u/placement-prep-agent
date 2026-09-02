"""
generate_dataset.py

Uses the Groq API (llama3-70b-8192) to bootstrap a synthetic training dataset
of (question, answer, score, feedback) examples. This dataset is then used
to train a small scorer and feedback-generator model — the LLM is only used
here, offline, to create training data. It is NOT part of the deployed system.

Requirements:
    pip install groq

Uses the same GROQ_API_KEY already set in prototype/.env — no second API key needed.
The key is loaded from the environment or from prototype/.env automatically.

Usage:
    python generate_dataset.py
    # -> writes feedback_dataset.jsonl
"""

import json
import os
import random
import time
from pathlib import Path

import httpx
from groq import Groq  # pip install groq

# ---------------------------------------------------------------------------
# Groq client — reads GROQ_API_KEY from environment or prototype/.env
# ---------------------------------------------------------------------------
def _load_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    # data_generation/ is 3 levels inside prototype/
    # __file__ -> data_generation/generate_dataset.py
    # .parent   -> data_generation/
    # .parent   -> m3_upgrade/
    # .parent   -> prototype/
    # + ".env"  -> prototype/.env
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise EnvironmentError(
        "GROQ_API_KEY not found. Set it in your shell or in prototype/.env"
    )

# Use a custom httpx client with SSL verification disabled.
# Needed when running behind a corporate/college proxy that intercepts TLS
# (the same environment issue that causes pip SSL errors).
client = Groq(
    api_key=_load_api_key(),
    http_client=httpx.Client(verify=False),
)

MODEL = "openai/gpt-oss-120b"  # best model available on this Groq account

# Score bands: (label, min_pct, max_pct)
BANDS = [
    ("poor", 0.05, 0.35),
    ("needs_improvement", 0.40, 0.60),
    ("good", 0.65, 0.80),
    ("excellent", 0.85, 1.00),
]

MAX_SCORE = 10.0


# ---- 1. Your question bank ---------------------------------------------------
# Option A: hand-write questions here.
# Option B: auto-generate them per topic with generate_questions() below —
# much faster way to get to 30-50+ questions with real topic coverage.

QUESTIONS = [
    # Data Structures
    "Explain how a hash table achieves average O(1) lookup time.",
    "What is the difference between an array and a linked list?",
    "How does a self-balancing binary search tree maintain O(log n) operations?",
    # Databases
    "Describe how SQL injection attacks work and how to prevent them.",
    "What is the difference between a clustered and a non-clustered index?",
    "What do the ACID properties of a database transaction guarantee?",
    # Networking / Security
    "What is the difference between symmetric and asymmetric encryption?",
    "Explain the CIA triad in information security.",
    "What is the purpose of a firewall in network security?",
    "Explain the difference between TCP and UDP.",
    # Operating Systems
    "What is a deadlock, and what four conditions cause it?",
    "Explain the difference between a process and a thread.",
    # System Design
    "What is the difference between horizontal and vertical scaling?",
    "What problem does a load balancer solve, and name one algorithm it uses?",
    # OOP / Python
    "Explain polymorphism with a concrete example.",
    "What is the difference between a list and a tuple in Python?",
    "How does Python's garbage collection work at a high level?",
    # Machine Learning
    "What is overfitting, and name two ways to reduce it.",
    "Explain the difference between supervised and unsupervised learning.",
    # add more questions here, or generate them — see generate_questions() below
]


def generate_questions(topic: str, n: int = 10) -> list[str]:
    """
    Auto-generates n exam/interview-style questions for a given topic using
    the LLM. Call this once per topic and merge results into QUESTIONS.
    """
    prompt = f"""Generate {n} distinct exam/interview-style questions about "{topic}".
Vary the difficulty (some basic, some advanced) and the question style
(explain, compare, describe, apply). Output ONLY the questions, one per line,
no numbering, no extra text."""
    text = call_llm(prompt, max_tokens=n * 30)
    return [line.strip() for line in text.split("\n") if line.strip()]


def build_question_bank(topics: list[str], per_topic: int = 10) -> list[str]:
    """Generates and merges questions across multiple topics."""
    all_questions = []
    for topic in topics:
        qs = generate_questions(topic, per_topic)
        all_questions.extend(qs)
        print(f"Generated {len(qs)} questions for topic: {topic}")
        time.sleep(0.3)
    return all_questions


# Example: uncomment to auto-build a larger question bank instead of the
# hardcoded list above. Adjust topics to match your evaluator's domain.
#
# TOPICS = [
#     "hash tables and data structures",
#     "network security fundamentals",
#     "cryptography basics",
#     "web application vulnerabilities",
#     "operating systems and processes",
#     "object-oriented programming",
#     "machine learning fundamentals",
#     "system design",
# ]
# QUESTIONS = build_question_bank(TOPICS, per_topic=10)  # ~80 questions


# ---------------------------------------------------------------------------
# LLM call wrapper
# ---------------------------------------------------------------------------
def call_llm(prompt: str, max_tokens: int = 300) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def generate_answer(question: str, band_label: str) -> str:
    quality_instructions = {
        "poor": "very poor, largely incorrect or off-topic, 1-2 sentences",
        "needs_improvement": "partially correct but missing key points, 2-3 sentences",
        "good": "mostly correct with minor gaps, 2-4 sentences",
        "excellent": "fully correct, clear, and complete, 3-5 sentences",
    }
    prompt = f"""Write a student's answer to this question. The answer quality
should be: {quality_instructions[band_label]}.

Question: {question}

Only output the answer text, nothing else. Do not mention the quality level."""
    return call_llm(prompt, max_tokens=200)


def generate_feedback(question: str, answer: str, score: float, band_label: str) -> str:
    prompt = f"""You are an instructor giving feedback on a student's answer.

Question: {question}
Student's Answer: {answer}
Score: {score:.1f}/{MAX_SCORE:.0f} ({band_label.replace('_', ' ')})

Write 2-3 sentences of specific, constructive feedback. Reference concrete
details from the answer. If the score isn't excellent, end with one actionable
suggestion for improvement.

Only output the feedback text, nothing else."""
    return call_llm(prompt, max_tokens=150)


def build_dataset(questions: list[str], examples_per_question: int = 4) -> list[dict]:
    """
    For each question, generates one example per score band (4 bands = 4 rows
    per question by default). With 19 questions this gives ~76 rows.
    Increase examples_per_question or add more questions to scale up.
    """
    dataset = []
    total = len(questions) * len(BANDS)
    done = 0
    for q in questions:
        for band_label, lo, hi in BANDS:
            answer = generate_answer(q, band_label)
            score = round(random.uniform(lo, hi) * MAX_SCORE, 1)
            feedback = generate_feedback(q, answer, score, band_label)

            dataset.append({
                "question": q,
                "answer": answer,
                "score": score,
                "max_score": MAX_SCORE,
                "band": band_label,
                "feedback": feedback,
            })
            done += 1
            print(f"[{done}/{total}] [{band_label}] {q[:55]}...")
            time.sleep(0.3)  # stay within Groq rate limits

    return dataset


if __name__ == "__main__":
    print(f"Generating dataset: {len(QUESTIONS)} questions x {len(BANDS)} bands "
          f"= {len(QUESTIONS) * len(BANDS)} examples")
    print(f"Model: {MODEL}\n")

    dataset = build_dataset(QUESTIONS)

    out_path = Path(__file__).parent / "feedback_dataset.jsonl"
    with open(out_path, "w") as f:
        for row in dataset:
            f.write(json.dumps(row) + "\n")

    print(f"\nSaved {len(dataset)} examples to {out_path}")
    print("Next step: run scorer/train_scorer.py --data data_generation/feedback_dataset.jsonl")


# -----------------------------------------------------------------------------
# TIPS:
# - With 19 questions x 4 bands you get ~76 rows — enough to test the pipeline
#   but not enough for a real model. Add more questions or increase
#   examples_per_question and sample bands randomly for more volume.
# - Spot-check ~20 generated (answer, feedback) pairs before training —
#   LLM output can drift or become repetitive across similar questions.
# - The output file (feedback_dataset.jsonl) is a one-time offline artefact.
#   It does not go into the deployed app — only the trained model does.
# -----------------------------------------------------------------------------
