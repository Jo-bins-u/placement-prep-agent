# Prepwise validation report

Generated 20260924_121126 · runtime 18.2 s

## Summary

| Metric | Value | Target | Result |
|---|---:|---:|:---:|
| Resume parser macro-F1 (text) | 0.977 | ≥ 0.85 | PASS |
| Resume parser macro-F1 (DOCX) | 0.977 | ≥ 0.85 | PASS |
| Internship extraction F1 | 1.000 | ≥ 0.85 | PASS |
| Project extraction F1 | 1.000 | ≥ 0.85 | PASS |
| Skill extraction F1 | 0.909 | ≥ 0.8 | PASS |
| Email extraction accuracy | 1.000 | ≥ 0.95 | PASS |
| Answer scoring band accuracy | 1.000 | ≥ 0.8 | PASS |
| Answer scoring Spearman rho | 0.992 | ≥ 0.8 | PASS |
| MCQ scoring accuracy | 1.000 | ≥ 1.0 | PASS |
| Code judge accuracy | 1.000 | ≥ 1.0 | PASS |
| Proficiency error reduction vs average @1 attempt | 0.329 | ≥ 0.2 | PASS |
| Proficiency error reduction vs average @5 attempts (on par ≥ -2%) | 0.055 | ≥ -0.02 | PASS |
| Proficiency error reduction vs average @12 attempts (on par ≥ -2%) | 0.001 | ≥ -0.02 | PASS |
| Weak-flag false alarms @1 attempt — old method | 0.203 | — | — |
| Weak-flag false alarms @1 attempt — new metric | 0.000 | — | — |
| Weak-flag precision @5 attempts — old method | 0.789 | — | — |
| Weak-flag precision @5 attempts — new metric | 0.784 | — | — |
| OTP digit uniformity p-value | 0.959 | ≥ 0.05 | PASS |
| OTP lifecycle checks passed | 1.000 | ≥ 1.0 | PASS |
| Resume feedback determinism | 1.000 | ≥ 1.0 | PASS |
| Question bank validity | 1.000 | ≥ 1.0 | PASS |

## Resume parser

| Mode | Field | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| text | skills | 0.942 | 0.878 | 0.909 |
| text | projects | 1.000 | 1.000 | 1.000 |
| text | education | 1.000 | 1.000 | 1.000 |
| text | internships | 1.000 | 1.000 | 1.000 |
| docx | skills | 0.942 | 0.878 | 0.909 |
| docx | projects | 1.000 | 1.000 | 1.000 |
| docx | education | 1.000 | 1.000 | 1.000 |
| docx | internships | 1.000 | 1.000 | 1.000 |

| Exact-match field | Accuracy |
|---|---:|
| contact.name | 100.0% |
| contact.email | 100.0% |
| internship_count | 100.0% |
| project_count | 100.0% |
| internship.role | 100.0% |
| internship.company | 91.7% |
| internship.duration | 100.0% |

## Answer evaluator

68 short-answer cases, 6 MCQ cases.

* Band accuracy: 100.0%
* Spearman ρ: 0.992 · Pearson r: 0.997
* MAE vs target: 1.2 points
* Correct ordering (full > partial > off-topic): 100.0%
* MCQ accuracy: 100.0%

_Synthetic answers built from each question's rubric keywords (full / half / off-topic / empty). Measures scoring consistency; paraphrased answers without the keywords are a known limitation of keyword scoring._

## Code judge

13 problems, 53 submissions · accuracy 100.0% · false accepts 0 · false rejects 0 · mean 149 ms

| Submission → judge status | Count |
|---|---:|
| infinite_loop -> timeout | 1 |
| reference -> correct | 13 |
| runtime_error -> runtime_error | 13 |
| syntax_error -> runtime_error | 13 |
| wrong_answer -> failed | 13 |

## Skill proficiency metric

2000 simulated learners per scenario — start ability ~ U(15,95); 'improving' learners gain U(0,25) points over 12 attempts; 70% open answers ~ N(ability + difficulty shift, 18), 30% MCQ all-or-nothing.
Parameters: {'prior_score': 50.0, 'prior_strength': 1.0, 'recency_decay': 0.9, 'min_attempts': 3}.

**Improving learners** (error = |estimate − true current skill|, in points)

| Attempts | Error: plain average | Error: metric | Reduction | Weak-flag false alarms (average → metric) | Weak-flag precision (average → metric) |
|---:|---:|---:|---:|---:|---:|
| 1 | 22.4 | 15.0 | 32.9% | 20.3% → 0.0% | 74.2% → 100.0% |
| 2 | 16.1 | 12.7 | 21.1% | 17.5% → 0.0% | 76.0% → 100.0% |
| 3 | 13.1 | 11.3 | 13.6% | 16.8% → 16.4% | 77.4% → 77.8% |
| 5 | 10.5 | 9.9 | 5.5% | 14.5% → 15.0% | 78.9% → 78.4% |
| 8 | 9.1 | 9.1 | -0.6% | 15.3% → 14.4% | 75.0% → 76.1% |
| 12 | 9.4 | 9.4 | 0.1% | 16.3% → 14.2% | 69.7% → 72.2% |

**Stationary learners** (error = |estimate − true current skill|, in points)

| Attempts | Error: plain average | Error: metric | Reduction | Weak-flag false alarms (average → metric) | Weak-flag precision (average → metric) |
|---:|---:|---:|---:|---:|---:|
| 1 | 22.4 | 15.0 | 32.9% | 20.3% → 0.0% | 74.2% → 100.0% |
| 2 | 16.0 | 12.5 | 22.0% | 17.2% → 0.0% | 77.3% → 100.0% |
| 3 | 13.0 | 11.0 | 15.5% | 16.0% → 15.6% | 80.0% → 80.4% |
| 5 | 10.3 | 9.4 | 9.0% | 13.4% → 14.3% | 83.2% → 82.1% |
| 8 | 8.0 | 7.7 | 3.4% | 11.8% → 12.4% | 85.5% → 84.8% |
| 12 | 6.7 | 6.9 | -3.7% | 9.9% → 10.3% | 87.7% → 87.2% |


## One-time codes

* 100,000 codes sampled; digit χ² = 3.12 (p = 0.959)
* Entropy: 3.3219 bits/digit (19.93 bits/code, max 19.93)
* Duplicates: 4764 (expected 4837.4 for a uniform generator)
* Brute-force success chance per issued code: 0.0005%
* Issue 1.4 ms · verify 1.6 ms (mean)

| Lifecycle check | Result |
|---|:---:|
| correct code accepted | PASS |
| code cannot be reused | PASS |
| stored value is a hash, not the code | PASS |
| wrong code rejected | PASS |
| locked after 5 wrong attempts | PASS |
| expired code rejected | PASS |
| sign-up code can't reset a password | PASS |
| resend blocked during cool-down | PASS |
| resend allowed after cool-down | PASS |
| newest code works after resend | PASS |

## Resume feedback scorer

* deterministic: 100.0%
* in range: 100.0%
* categories complete: 100.0%
* internship added: 100.0%
* project added: 100.0%
* skills added: 100.0%

## Question bank

20 questions · valid 100.0% · duplicate ids 0
* By difficulty: {'easy': 6, 'medium': 10, 'hard': 4}
* By type: {'short_answer': 17, 'mcq': 3}
