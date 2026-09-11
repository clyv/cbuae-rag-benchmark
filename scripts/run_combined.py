#!/usr/bin/env python3
"""Do the two independent gains stack?

    python scripts/run_combined.py

Writes results/combined.json.

Two changes were each measured against the shipped configuration and each
cleared zero on a paired bootstrap:

  not splitting sections   +0.041   (results/chunking.md)
  indexing the doc title   +0.052   (results/doc_title.md)

Adding those up would give +0.093, and that is exactly the arithmetic worth
distrusting. Both changes plausibly fix *the same* failures - a whole section is
easier to tell from its siblings, and so is a section carrying its instrument's
name - in which case the combination is worth much less than the sum. This runs
the 2x2 rather than assuming either way.

The baseline cell reproduces the shipped configuration, which is also a check
that nothing else has drifted since those numbers were reported.
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

from regulens.evaluation.runner import evaluate, load_benchmark  # noqa: E402
from regulens.ingest.chunk import chunk_sections  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "combined.json"
CACHE_DIR = REPO_ROOT / ".cache" / "combined"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
WHOLE_SECTION = 10**6
METRIC = "recall@10"

CELLS = [
    ("shipped", 512, 64, False),
    ("whole sections", WHOLE_SECTION, 0, False),
    ("doc title", 512, 64, True),
    ("both", WHOLE_SECTION, 0, True),
]


def load_sections() -> list[Chunk]:
    return [
        Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {}))
        for r in (json.loads(l) for l in SECTIONS.read_text(encoding="utf-8").splitlines() if l.strip())
    ]


def paired(a: list[float], b: list[float], rounds: int, rng: random.Random):
    diffs = [b[i] - a[i] for i in range(len(a))]
    point = statistics.fmean(diffs)
    means = sorted(statistics.fmean(diffs[rng.randrange(len(diffs))] for _ in diffs) for _ in range(rounds))
    return point, means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    sections = load_sections()
    items = load_benchmark(BENCHMARK)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    per_question: dict[str, dict[str, float]] = {}
    summary: dict[str, dict] = {}

    for label, max_tokens, overlap, title in CELLS:
        chunks = chunk_sections(sections, max_tokens=max_tokens, overlap=overlap)
        system = RerankedRetriever(
            HybridRetriever([
                BM25Retriever(chunks, include_doc_title=title),
                DenseRetriever(chunks, DENSE_MODEL,
                               cache=CACHE_DIR / f"{max_tokens}-{overlap}-{int(title)}.npz",
                               include_doc_title=title),
            ]),
            RERANK_MODEL,
        )
        report = evaluate(system, items)
        answerable = [q for q in report.per_question if q.category != "unanswerable"]
        per_question[label] = {q.item_id: q.scores[METRIC] for q in answerable}
        summary[label] = {
            "chunks": len(chunks),
            "max_tokens": max_tokens,
            "overlap": overlap,
            "doc_title": title,
            METRIC: statistics.fmean(q.scores[METRIC] for q in answerable),
            "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
            "mrr": statistics.fmean(q.scores["mrr"] for q in answerable),
        }
        print(f"  {label:16s} {len(chunks):5d} chunks   {METRIC} {summary[label][METRIC]:.3f}", flush=True)

    ids = sorted(per_question["shipped"])
    base = [per_question["shipped"][i] for i in ids]
    for label in ("whole sections", "doc title", "both"):
        point, low, high = paired(base, [per_question[label][i] for i in ids],
                                  args.rounds, random.Random(f"{args.seed}:{label}"))
        summary[label]["vs_shipped"] = {"difference": point, "interval": [low, high]}

    additive = summary["whole sections"]["vs_shipped"]["difference"] + \
        summary["doc title"]["vs_shipped"]["difference"]
    observed = summary["both"]["vs_shipped"]["difference"]

    report_out = {
        "metric": METRIC,
        "cells": summary,
        "additive_prediction": additive,
        "observed_combined": observed,
        "interaction": observed - additive,
        "per_question": per_question,
    }
    OUT.write_text(json.dumps(report_out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'configuration':16s} {METRIC:>10s} {'full@10':>8s} {'vs shipped':>11s}  95% interval")
    for label, _, _, _ in CELLS:
        s = summary[label]
        vs = s.get("vs_shipped")
        tail = (f"{vs['difference']:+11.3f}  {vs['interval'][0]:+.3f} to {vs['interval'][1]:+.3f}"
                if vs else f"{'-':>11s}")
        print(f"{label:16s} {s[METRIC]:10.3f} {s['full_recall@10']:8.3f} {tail}")

    print(f"\nif the two were independent, both would be  {additive:+.3f}")
    print(f"both actually measures                      {observed:+.3f}")
    interaction = observed - additive
    word = "more than the sum" if interaction > 0 else "less than the sum"
    print(f"interaction                                 {interaction:+.3f}  ({word})")
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
