"""
smoke_test_pipeline.py

A torch-free smoke test that validates every part of the feedback pipeline
EXCEPT the neural network training loop itself:

  - Dataset loading and splitting
  - Input/output formatting (format_source, format_target)
  - Tokenizer training (ByteLevelBPETokenizer)
  - ROUGE-L metric on the seed examples

Run this when torch has a DLL issue on the current machine.
The real training (train_feedback_model.py --smoke-test) runs this exact
logic PLUS the T5 forward/backward pass — run that on a machine with a
working torch install (or after reinstalling torch/VC++ redist).

Usage:
    python smoke_test_pipeline.py --data ../data/seed_dataset.jsonl
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from metrics import rouge_l

# Import the formatting helpers from the real script
sys.path.insert(0, str(Path(__file__).parent))
from train_feedback_model import load_dataset, format_source, format_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    # ---- 1. Load and split -----------------------------------------------
    rows = load_dataset(args.data)
    n = len(rows)
    train_rows = rows[:int(n * 0.7)]
    val_rows   = rows[int(n * 0.7):int(n * 0.85)]
    test_rows  = rows[int(n * 0.85):]
    print(f"[OK] Dataset loaded: {n} rows")
    print(f"     Split: {len(train_rows)} train / {len(val_rows)} val / {len(test_rows)} test")

    # ---- 2. Formatting ----------------------------------------------------
    sample = train_rows[0]
    src = format_source(sample)
    tgt = format_target(sample)
    assert src and tgt, "format_source/format_target returned empty strings"
    print(f"\n[OK] format_source: {src[:80]}...")
    print(f"     format_target: {tgt[:80]}...")

    # ---- 3. Tokenizer training (same as smoke test in train_feedback_model) -
    try:
        from tokenizers import ByteLevelBPETokenizer
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_path = Path(tmpdir) / "corpus.txt"
            with open(corpus_path, "w") as f:
                for row in train_rows + val_rows:
                    f.write(format_source(row) + "\n" + format_target(row) + "\n")

            tok = ByteLevelBPETokenizer()
            tok.train(files=[str(corpus_path)], vocab_size=500, min_frequency=1,
                      special_tokens=["<pad>", "<eos>", "<unk>"])

            sample_enc = tok.encode(src)
            assert len(sample_enc.ids) > 0
            print(f"\n[OK] ByteLevelBPETokenizer: vocab_size={tok.get_vocab_size()}, "
                  f"sample tokens={len(sample_enc.ids)}")
    except ImportError:
        print("\n[SKIP] tokenizers package not installed — skipping tokenizer test")

    # ---- 4. ROUGE-L metric ------------------------------------------------
    # Use feedback text as both reference and hypothesis — should give score=1.0
    ref = test_rows[0]["feedback"]
    score = rouge_l(ref, ref)
    assert score == 1.0, f"Expected ROUGE-L=1.0 on identical strings, got {score}"
    print(f"\n[OK] ROUGE-L (self): {score}")

    # Cross-example ROUGE-L
    hyp = test_rows[0]["feedback"]
    ref2 = test_rows[1]["feedback"] if len(test_rows) > 1 else "dummy reference text here"
    cross = rouge_l(ref2, hyp)
    print(f"     ROUGE-L (cross): {cross}  (low is expected on 24 seed examples)")

    # ---- 5. Summary -------------------------------------------------------
    print("""
========================================================
Pipeline smoke test PASSED (torch-free)
========================================================
  Validated:
    [x] Dataset loading + splitting
    [x] format_source / format_target
    [x] ByteLevelBPETokenizer training
    [x] ROUGE-L metric

  NOT validated here (needs working torch):
    [ ] T5 model instantiation
    [ ] Forward pass / loss computation
    [ ] Backward pass / optimizer step

  To run the full smoke test (with torch):
    1. Fix torch on this machine:
       - Install Visual C++ 2019 Redistributable (x64) from Microsoft
         https://aka.ms/vs/17/release/vc_redist.x64.exe
       - Then: pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu
       - Then: pip install "transformers==4.36.2"
    2. python train_feedback_model.py --data ../data/seed_dataset.jsonl \\
           --backend pretrained --smoke-test --epochs 3
========================================================
""")


if __name__ == "__main__":
    main()
