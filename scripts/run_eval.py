#!/usr/bin/env python3
"""Run the retrieval systems against the benchmark. Phase 4.

    python scripts/run_eval.py --systems bm25
    python scripts/run_eval.py                     # every system that will load

Writes one JSON per system to results/, plus results/summary.md.

## Two reporting decisions worth knowing about

**Unanswerable items are scored separately.** `recall_at_k` returns 1.0 when
nothing is required, which is correct - an item with no required evidence cannot
fail recall - but it means the 6 unanswerable questions would hand every system
a free 1.0 and lift overall recall by the same 12 points across the board.
Averaging them in would flatter all four systems equally and compress the
differences the project exists to measure. Headline recall here is therefore
over the 44 answerable items; the unanswerable ones are reported as their own
row, where what matters is how much irrelevant material was pulled in.

**Latency is measured per query, not per run.** Indexing cost is reported
separately, because it is paid once and a reranker's cost is paid on every
query. The two numbers answer different questions.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.evaluation.runner import evaluate, load_benchmark  # noqa: E402
from regulens.retrieval.base import Chunk, RetrievalResult  # noqa: E402

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
RESULTS = REPO_ROOT / "results"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Timed:
    """Wraps a retriever to record per-query latency without changing the harness."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.latencies_ms: list[float] = []

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        start = time.perf_counter()
        out = self.inner.retrieve(query, k)
        self.latencies_ms.append((time.perf_counter() - start) * 1000)
        return out


def load_chunks() -> list[Chunk]:
    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS.relative_to(REPO_ROOT)} not found. Run scripts/build_corpus.py.")
    chunks = []
    for line in CHUNKS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            chunks.append(
                Chunk(
                    chunk_id=raw["chunk_id"],
                    doc_id=raw["doc_id"],
                    section=raw["section"],
                    text=raw["text"],
                    metadata=raw.get("metadata", {}),
                )
            )
    return chunks


def build(name: str, chunks: list[Chunk], cache: dict):
    """Construct one system, reusing components the hybrid systems share."""
    if name == "bm25":
        from regulens.retrieval.bm25 import BM25Retriever

        cache.setdefault("bm25", BM25Retriever(chunks))
        return cache["bm25"]

    if name == "dense":
        from regulens.retrieval.dense import DenseRetriever

        cache.setdefault("dense", DenseRetriever(chunks, DENSE_MODEL))
        return cache["dense"]

    if name == "hybrid":
        from regulens.retrieval.hybrid import HybridRetriever

        cache.setdefault(
            "hybrid",
            HybridRetriever([build("bm25", chunks, cache), build("dense", chunks, cache)]),
        )
        return cache["hybrid"]

    if name == "rerank":
        from regulens.retrieval.rerank import RerankedRetriever

        return RerankedRetriever(build("hybrid", chunks, cache), RERANK_MODEL)

    raise ValueError(f"unknown system {name!r}")


def split_scores(report, answerable_only: bool = True) -> dict[str, float]:
    """Mean scores over answerable items only - see the module docstring."""
    rows = [
        q for q in report.per_question
        if not answerable_only or q.category != "unanswerable"
    ]
    if not rows:
        return {}
    keys = rows[0].scores.keys()
    return {k: statistics.fmean(q.scores[k] for q in rows) for k in keys}


def noise_on_unanswerable(report) -> float | None:
    """Mean precision@10 on unanswerable items - i.e. how much noise came back.

    Recall is meaningless here, but an unanswerable question still shows whether
    a system floods the top 10 with confident-looking irrelevant sections, which
    is what the abstention story in the README turns on.
    """
    rows = [q for q in report.per_question if q.category == "unanswerable"]
    if not rows:
        return None
    return statistics.fmean(q.scores.get("precision@10", 0.0) for q in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--systems", default="bm25,dense,hybrid,rerank")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10])
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    chunks = load_chunks()
    items = load_benchmark(BENCHMARK)
    answerable = sum(1 for i in items if i.category != "unanswerable")
    print(f"{len(chunks)} chunks | {len(items)} questions ({answerable} answerable)\n")

    RESULTS.mkdir(exist_ok=True)
    cache: dict = {}
    summary = []

    for name in [s.strip() for s in args.systems.split(",") if s.strip()]:
        print(f"--- {name}")
        try:
            start = time.perf_counter()
            system = build(name, chunks, cache)
            index_seconds = time.perf_counter() - start
        except ImportError as exc:
            print(f"    skipped: {exc}\n")
            continue

        timed = Timed(system)
        report = evaluate(timed, items, k_values=tuple(args.k))

        overall = split_scores(report)
        median_ms = statistics.median(timed.latencies_ms)
        noise = noise_on_unanswerable(report)

        report.to_json(RESULTS / f"{system.name}.json")
        summary.append(
            {
                "system": system.name,
                "index_seconds": round(index_seconds, 1),
                "median_query_ms": round(median_ms, 1),
                "answerable_n": answerable,
                "scores": {k: round(v, 4) for k, v in overall.items()},
                "unanswerable_precision_at_10": round(noise, 4) if noise is not None else None,
                "by_category": report.by_category(),
            }
        )

        print(f"    index {index_seconds:.1f}s | median query {median_ms:.1f}ms")
        for k in args.k:
            print(
                f"    recall@{k:<3} {overall[f'recall@{k}']:.3f}"
                f"   full_recall@{k:<3} {overall[f'full_recall@{k}']:.3f}"
            )
        print(f"    mrr        {overall['mrr']:.3f}")
        if noise is not None:
            print(f"    unanswerable precision@10 {noise:.3f} (lower is better)")
        print()

    (RESULTS / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(summary)} result file(s) to {RESULTS.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
