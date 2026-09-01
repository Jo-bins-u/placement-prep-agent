# M3 Upgrade — Trained ASAG Scorer + Feedback Generator

Replaces the keyword-rubric grader with two real trained models:
1. **Scorer** — predicts a score from (question, answer)
2. **Feedback generator** — generates feedback text from (question, answer, score)

Both are trained on data bootstrapped once, offline, from an LLM — the
LLM is not part of the deployed system, only used to create training
examples. Everything that ships to users at the end runs with zero API
calls and zero ongoing cost.

## Everything here has been run and verified — except the two steps that need internet access this sandbox doesn't have (huggingface.co and the Anthropic API are both blocked here). Both are marked below. Run those two on your own machine.

```
data_generation/generate_dataset.py   — your script, unchanged. Needs ANTHROPIC_API_KEY. RUN ON YOUR MACHINE.
data/seed_dataset.jsonl               — 24 hand-written examples, same schema — lets you test everything else right now
scorer/train_scorer.py                — TESTED (tfidf backend). embeddings backend needs internet — RUN ON YOUR MACHINE.
feedback_generator/train_feedback_model.py — TESTED (--smoke-test). Real run needs internet — RUN ON YOUR MACHINE.
shared/metrics.py                     — TESTED. Pearson r, QWK, ROUGE-L.
```

## Run it now, with the seed data (no API key, no internet needed)

```bash
pip install -r requirements.txt

cd scorer
python train_scorer.py --data ../data/seed_dataset.jsonl --backend tfidf

cd ../feedback_generator
python train_feedback_model.py --data ../data/seed_dataset.jsonl --backend pretrained --smoke-test --epochs 3
```

Both will run start to finish and print real (if meaningless, at n=24)
metrics — this proves the pipeline works mechanically before you spend
API credits and training time on the real thing.

## Run it for real (on your own machine, with internet + an API key)

```bash
export ANTHROPIC_API_KEY=your_key_here
cd data_generation
python generate_dataset.py
# -> writes feedback_dataset.jsonl (start with the ~5 questions already
#    in the script; uncomment build_question_bank() for more topics/volume)

cd ../scorer
python train_scorer.py --data ../feedback_dataset.jsonl --backend tfidf       # baseline
python train_scorer.py --data ../feedback_dataset.jsonl --backend embeddings  # main model

cd ../feedback_generator
python train_feedback_model.py --data ../feedback_dataset.jsonl --backend pretrained --epochs 6
```

## 2-week plan

| Days | Work |
|---|---|
| 1–2 | Expand `QUESTIONS` in `generate_dataset.py` to 25-40 questions across your topics (use `build_question_bank()` to auto-generate more per topic). Run it — budget real time here, ~1-2 API calls per example with `time.sleep(0.3)` between calls adds up. Target 500-1000 rows in `feedback_dataset.jsonl`. |
| 3 | Spot-check ~30 generated (answer, feedback) pairs by hand. Synthetic data can be repetitive or drift — catch it now, not after training. |
| 4 | Run `train_scorer.py --backend tfidf` on the real dataset — this is your baseline number to beat. |
| 5–6 | Run `train_scorer.py --backend embeddings`. Compare Pearson/QWK against the TF-IDF baseline — this comparison is the actual ML story for your report. |
| 7 | Error analysis on the scorer: which (question, answer) pairs does it get most wrong? Write this up — it's more valuable to a review committee than the headline number alone. |
| 8–9 | Run `train_feedback_model.py --backend pretrained` on the real dataset. Watch the sample generations printed at the end — this is where you'll see if quality is usable or needs more data/epochs. |
| 10 | ROUGE-L against held-out feedback + your own qualitative read of 10-15 generations. Note failure patterns honestly (generic phrasing, ignoring specific details in the answer, etc). |
| 11–12 | Wire both models into `evaluator.py` in the main prototype: scorer replaces the keyword-rubric score, feedback generator replaces the keyword-based feedback string. Keep the `(score, feedback)` return signature so nothing else in the app needs to change. |
| 13 | End-to-end test through the actual dashboard — upload resume, practice, submit, see real model-generated score + feedback show up. |
| 14 | Buffer. Something in this plan will take longer than expected — probably data generation (step 1-2) or debugging the T5 fine-tuning environment on whoever's machine runs it. |

## What to say in your report, honestly

- You have a genuine baseline-vs-improved-model comparison for the scorer (TF-IDF vs. embeddings) — use it, it's good practice and shows you understand *why* the better model is better, not just that it exists.
- The feedback generator's ceiling is bounded by the LLM that generated its training data — it will not exceed calling that LLM directly at inference. The value is zero ongoing cost/dependency, not higher quality. Say this plainly rather than overselling.
- If from-scratch training (no pretrained weights) is something you want to show alongside the fine-tuned model as a comparison point, your original `train_seq2seq.py` is still the reference for that path — expect visibly more generic output at the same data size, which is itself a legitimate finding to report ("pretrained vs. from-scratch at equal data budget").
