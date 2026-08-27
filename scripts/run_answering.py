#!/usr/bin/env python3
"""Measure abstention and citation validity. Phase 5.

    python scripts/run_answering.py

Writes results/answering.json and results/abstention.md.

## Why this reports a curve instead of a number

There are 6 unanswerable questions. Choosing the abstention threshold that
maximises performance on those 6 and then reporting that performance would be
fitting the parameter to the test set, and the resulting figure would say more
about the tuning than the system. With a sample that small a single threshold
can be moved to almost any result.

So the whole trade-off is reported: at each threshold, how many unanswerable
questions were correctly declined against how many answerable ones were wrongly
declined. That curve is a property of the system. A reader can pick the
operating point their use case justifies - a compliance tool would rather refuse
a question it could have answered than answer one it should not have - and the
README states which point it quotes and that the point was chosen after seeing
the data.

## Why only one system is scored

Abstention needs a relevance score that is comparable across questions. Only the
cross-encoder produces one; BM25 scores are unbounded and RRF scores encode rank
position, not quality. See regulens.generation.answer for the argument.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.evaluation.runner import load_benchmark  # noqa: E402
from regulens.generation.answer import (  # noqa: E402
    ExtractiveGenerator,
    answer_question,
    validate_citations,
)
from regulens.retrieval.base import Chunk  # noqa: E402

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
RESULTS = REPO_ROOT / "results"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def load_chunks() -> list[Chunk]:
    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS.relative_to(REPO_ROOT)} not found. Run scripts/build_corpus.py.")
    out = []
    for line in CHUNKS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {})))
    return out


def build_reranker(chunks: list[Chunk]):
    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    hybrid = HybridRetriever([BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL)])
    return RerankedRetriever(hybrid, RERANK_MODEL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=5, help="passages given to the answerer")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    chunks = load_chunks()
    items = load_benchmark(BENCHMARK)
    system = build_reranker(chunks)
    generator = ExtractiveGenerator()

    # Retrieve once; the threshold sweep then runs offline over stored scores.
    records = []
    for index, item in enumerate(items, start=1):
        print(f"  [{index}/{len(items)}] {item.id}", end="\r", flush=True)
        results = system.retrieve(item.question, args.k)
        answer = answer_question(item.question, results, generator=generator, threshold=None)
        validity = validate_citations(answer)
        records.append(
            {
                "id": item.id,
                "category": item.category,
                "answerable": item.category != "unanswerable",
                "top_score": results[0].score if results else None,
                "citations": validity["citations"],
                "grounded": validity["grounded"],
                "supported": validity["supported"],
                "cited": [c.evidence_id for c in answer.citations],
            }
        )
    print(" " * 40, end="\r")

    scores = sorted({round(r["top_score"], 2) for r in records if r["top_score"] is not None})
    answerable = [r for r in records if r["answerable"]]
    unanswerable = [r for r in records if not r["answerable"]]

    curve = []
    for threshold in scores:
        declined_bad = sum(1 for r in unanswerable if r["top_score"] <= threshold)
        declined_good = sum(1 for r in answerable if r["top_score"] <= threshold)
        curve.append(
            {
                "threshold": threshold,
                "unanswerable_declined": declined_bad,
                "unanswerable_total": len(unanswerable),
                "answerable_wrongly_declined": declined_good,
                "answerable_total": len(answerable),
            }
        )

    grounded = statistics.fmean(r["grounded"] for r in records)
    supported = statistics.fmean(r["supported"] for r in records)

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "answering.json").write_text(
        json.dumps(
            {
                "system": system.name,
                "generator": generator.name,
                "k": args.k,
                "citation_grounded": grounded,
                "citation_supported": supported,
                "per_question": records,
                "abstention_curve": curve,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"system     {system.name} + {generator.name} generator, k={args.k}")
    print(f"questions  {len(records)} ({len(answerable)} answerable, {len(unanswerable)} not)\n")
    print(f"citation grounded  {grounded:.3f}  (cited section was in the retrieved context)")
    print(f"citation supported {supported:.3f}  (quoted text appears in that section)\n")

    print("relevance score of the top passage:")
    for label, rows in (("answerable", answerable), ("unanswerable", unanswerable)):
        vals = sorted(r["top_score"] for r in rows)
        print(
            f"  {label:<13} min {vals[0]:7.2f}  median {statistics.median(vals):7.2f}  max {vals[-1]:7.2f}"
        )

    print("\nabstention trade-off:")
    print(f"  {'threshold':>10}  {'declined (of ' + str(len(unanswerable)) + ')':>18}  "
          f"{'wrongly declined (of ' + str(len(answerable)) + ')':>28}")
    shown = [c for c in curve if c["unanswerable_declined"] > 0 or c["answerable_wrongly_declined"] > 0]
    step = max(1, len(shown) // 14)
    for row in shown[::step]:
        print(
            f"  {row['threshold']:>10.2f}  {row['unanswerable_declined']:>18}  "
            f"{row['answerable_wrongly_declined']:>28}"
        )
    print(f"\nWrote {(RESULTS / 'answering.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
