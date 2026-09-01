"""
generate_dataset.py

Uses an LLM (Anthropic API) to bootstrap a synthetic training dataset of
(question, answer, score, feedback) examples. This dataset is then used
to train YOUR OWN small seq2seq model from scratch (see train_seq2seq.py) —
the LLM is only used here, offline, to create training data. It is not
part of the final deployed model.

Requirements:
    pip install anthropic

Set your API key:
    export ANTHROPIC_API_KEY=your_key_here
"""

import json
import random
import time
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

MODEL = "claude-sonnet-4-6"

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
    "Explain how a hash table achieves average O(1) lookup time.",
    "What is the difference between symmetric and asymmetric encryption?",
    "Describe how SQL injection attacks work and how to prevent them.",
    "Explain the CIA triad in information security.",
    "What is the purpose of a firewall in network security?",
    # add more questions here, or generate them — see generate_questions() below
]


def generate_questions(topic: str, n: int = 10) -> list[str]:
    """
    Auto-generates n exam/interview-style questions for a given topic using
    the LLM. Call this once per topic and merge results into QUESTIONS —
    much faster than hand-writing a large question bank.
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
# ]
# QUESTIONS = build_question_bank(TOPICS, per_topic=10)  # ~50 questions


def call_llm(prompt: str, max_tokens: int = 300) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


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
    For each question, generates one example per score band by default
    (examples_per_question = len(BANDS)). Increase examples_per_question
    and sample bands randomly if you want more volume per question.
    """
    dataset = []
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
            print(f"Generated: [{band_label}] {q[:50]}...")
            time.sleep(0.3)  # be gentle on rate limits

    return dataset


if __name__ == "__main__":
    dataset = build_dataset(QUESTIONS)

    with open("feedback_dataset.jsonl", "w") as f:
        for row in dataset:
            f.write(json.dumps(row) + "\n")

    print(f"\nSaved {len(dataset)} examples to feedback_dataset.jsonl")


# -----------------------------------------------------------------------------
# TIPS:
# - Aim for at least 500-1000 examples for a small seq2seq model to learn
#   useful patterns. Add more questions to QUESTIONS, or set
#   examples_per_question higher with band sampled via random.choice(BANDS).
# - Spot-check a sample of generated (answer, feedback) pairs manually —
#   synthetic data can be repetitive or drift in style, so a quick pass
#   catches issues before you spend time training on it.
# - Keep this script and its output separate from your deployed model —
#   it's a one-time offline data-generation step.
# -----------------------------------------------------------------------------
