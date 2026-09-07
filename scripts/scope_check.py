#!/usr/bin/env python3
"""Does checking scope catch the questions relevance cannot? Phase 5 follow-up.

    python scripts/scope_check.py

## The failure this addresses

Abstention on relevance alone reaches AUC 0.806, and the residual errors share a
shape. "What are the capital adequacy requirements for a finance company?" scores
4.21 - higher than most answerable questions - because it retrieves an article
titled *Group Capital Adequacy*. A cross-encoder trained on topical relevance is
right that the passage is about capital adequacy. What it cannot see is that the
passage governs a different kind of entity.

That is a question about **scope**, not relevance, and no threshold on a
relevance score can reach it.

## The check

Every instrument says near its start who it binds and what it covers. Those
framing sections - preamble, introduction, objective, scope - are concatenated
into a scope profile per document, and the question is scored against that
profile with the same cross-encoder used for reranking.

The intuition: a question about finance companies may match the *content* of an
insurance capital article closely while matching the insurance instrument's
statement of who it applies to poorly. Relevance and scope disagree, and that
disagreement is the signal.

Using framing sections rather than a dedicated Scope of Application section is
deliberate. Only 21 of 46 documents have one the parser can identify, and a
check that works on half the corpus is not a check. Every document has framing
material.

## Reading the result

The comparison is AUC of relevance alone against AUC of each combination, on the
same 100 questions. An improvement inside the interval is not an improvement.
The honest outcome may well be that this does not help, and that is worth
recording either way - it is the difference between a diagnosis and a fix.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.retrieval.base import Chunk  # noqa: E402

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
ANSWERING = REPO_ROOT / "results" / "answering.json"
OUT = REPO_ROOT / "results" / "scope_check.json"

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Section labels that carry an instrument's framing rather than its obligations.
FRAMING = ("preamble", "introduction", "objective", "scope", "applicab", "definitions")
PROFILE_CHARS = 1400


def scope_profiles() -> dict[str, str]:
    """doc_id -> the text that says what this instrument is and who it binds."""
    rows = [
        json.loads(line)
        for line in SECTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    parts: dict[str, list[str]] = {}
    for record in rows:
        label = (record["section"] + " " + record["metadata"].get("section_title", "")).lower()
        if any(word in label for word in FRAMING):
            parts.setdefault(record["doc_id"], []).append(record["text"])

    profiles = {}
    for doc_id, texts in parts.items():
        profiles[doc_id] = "\n".join(texts)[:PROFILE_CHARS]
    # A document with no framing section falls back to its own title, which at
    # least names the entity type it governs.
    titles = {r["doc_id"]: r["metadata"].get("title", "") for r in rows}
    for doc_id, title in titles.items():
        profiles.setdefault(doc_id, title)
    return profiles


def auc(answerable: list[float], unanswerable: list[float]) -> float:
    pairs = [(a, u) for a in answerable for u in unanswerable]
    return sum((a > u) + 0.5 * (a == u) for a, u in pairs) / len(pairs)


def auc_interval(
    answerable: list[float], unanswerable: list[float], rounds: int, rng: random.Random
) -> tuple[float, float]:
    boot = []
    for _ in range(rounds):
        A = [answerable[rng.randrange(len(answerable))] for _ in answerable]
        U = [unanswerable[rng.randrange(len(unanswerable))] for _ in unanswerable]
        boot.append(auc(A, U))
    boot.sort()
    return boot[int(0.025 * rounds)], boot[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20260902)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not ANSWERING.exists():
        sys.exit("results/answering.json not found. Run scripts/run_answering.py first.")

    recorded = json.loads(ANSWERING.read_text(encoding="utf-8"))["per_question"]
    profiles = scope_profiles()

    benchmark = {
        json.loads(line)["id"]: json.loads(line)
        for line in (REPO_ROOT / "benchmark" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    from regulens.retrieval._sentence_transformers import load_cross_encoder

    model = load_cross_encoder()(RERANK_MODEL, device="cpu")

    # The document each question's top passage came from, so scope is scored
    # against the instrument the system would actually have answered from.
    rows = []
    pairs = []
    for record in recorded:
        top_doc = record["cited"][0].split("::")[0] if record["cited"] else None
        rows.append(record | {"top_doc": top_doc})
        question = benchmark[record["id"]]["question"]
        pairs.append((question, profiles.get(top_doc, "")))

    print(f"scoring {len(pairs)} question-scope pairs on CPU...")
    scope_scores = [float(s) for s in model.predict(pairs, show_progress_bar=False)]

    for record, score in zip(rows, scope_scores):
        record["scope_score"] = round(score, 3)

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]

    strategies = {
        "relevance only": lambda r: r["top_score"],
        "scope only": lambda r: r["scope_score"],
        "sum": lambda r: r["top_score"] + r["scope_score"],
        "min of the two": lambda r: min(r["top_score"], r["scope_score"]),
    }

    print(f"\n{'strategy':<18}{'AUC':>7}{'95% interval':>20}")
    results = {}
    for name, fn in strategies.items():
        a = [fn(r) for r in answerable]
        u = [fn(r) for r in unanswerable]
        value = auc(a, u)
        lo, hi = auc_interval(a, u, args.rounds, random.Random(f"{args.seed}:{name}"))
        results[name] = {"auc": round(value, 4), "lo": round(lo, 4), "hi": round(hi, 4)}
        print(f"  {name:<16}{value:>7.3f}   {lo:.3f} - {hi:.3f}")

    # Does scope rescue the specific cases relevance ranks highest?
    worst = sorted(unanswerable, key=lambda r: -r["top_score"])[:5]
    print("\nthe unanswerable questions relevance scores highest:")
    print(f"  {'id':<7}{'relevance':>11}{'scope':>9}   top document")
    for r in worst:
        print(f"  {r['id']:<7}{r['top_score']:>11.2f}{r['scope_score']:>9.2f}   {r['top_doc']}")

    median_scope_answerable = statistics.median(r["scope_score"] for r in answerable)
    print(f"\nmedian scope score: answerable {median_scope_answerable:.2f}, "
          f"unanswerable {statistics.median(r['scope_score'] for r in unanswerable):.2f}")

    OUT.write_text(
        json.dumps(
            {
                "model": RERANK_MODEL,
                "profile_chars": PROFILE_CHARS,
                "strategies": results,
                "per_question": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
