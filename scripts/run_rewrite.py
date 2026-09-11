#!/usr/bin/env python3
"""Does rewriting the question help retrieve the answer?

    python scripts/run_rewrite.py --prf-only   # no model, a couple of minutes
    python scripts/run_rewrite.py              # adds HyDE, ~15 minutes

Writes results/rewrite.json.

The prediction is in `src/regulens/retrieval/rewrite.py` and was written before
this ran. Query rewriting attacks vocabulary mismatch, and `results/failures.md`
measured vocabulary mismatch at **one** of 39 missed sections. Expansion may also
actively hurt, by harvesting terms from a matched instrument and dragging the
query toward the wrong twin.

Both rewriters sit in front of hybrid retrieval, and the reranker sits after, so
what is measured is whether a rewritten query puts better candidates in front of
the same ranker.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.evaluation.runner import evaluate, load_benchmark  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402
from regulens.retrieval.rewrite import (  # noqa: E402
    HypotheticalAnswerRewriter,
    PseudoRelevanceRewriter,
    RewrittenRetriever,
)

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "rewrite.json"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
METRIC = "recall@10"


def load_chunks() -> list[Chunk]:
    return [
        Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {}))
        for r in (json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip())
    ]


def paired(a: list[float], b: list[float], rounds: int, rng: random.Random):
    diffs = [b[i] - a[i] for i in range(len(a))]
    point = statistics.fmean(diffs)
    means = sorted(statistics.fmean(diffs[rng.randrange(len(diffs))] for _ in diffs) for _ in range(rounds))
    return point, means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prf-only", action="store_true")
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    chunks = load_chunks()
    items = load_benchmark(BENCHMARK)
    hybrid = HybridRetriever([BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL)])

    systems: list[tuple[str, object, object]] = [("baseline", hybrid, None)]

    prf = PseudoRelevanceRewriter(hybrid)
    systems.append(("prf", RewrittenRetriever(hybrid, prf), prf))

    if not args.prf_only:
        print("loading the generator for HyDE...", flush=True)
        from regulens.generation.abstractive import AbstractiveGenerator

        model = AbstractiveGenerator(max_new_tokens=70)
        hyde = HypotheticalAnswerRewriter(lambda prompt: model._run(prompt))
        systems.append(("hyde", RewrittenRetriever(hybrid, hyde), hyde))

    report: dict = {"metric": METRIC, "systems": {}}
    per_question: dict[str, dict[str, float]] = {}

    for label, retriever, _ in systems:
        started = time.perf_counter()
        system = RerankedRetriever(retriever, RERANK_MODEL)
        result = evaluate(system, items)
        answerable = [q for q in result.per_question if q.category != "unanswerable"]
        per_question[label] = {q.item_id: q.scores[METRIC] for q in answerable}
        report["systems"][label] = {
            METRIC: statistics.fmean(q.scores[METRIC] for q in answerable),
            "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
            "seconds": round(time.perf_counter() - started, 1),
        }
        if isinstance(retriever, RewrittenRetriever):
            report["systems"][label]["examples"] = [
                {"question": q, "rewritten": r}
                for q, r in list(retriever.rewrites.items())[:5]
            ]
            unchanged = sum(1 for q, r in retriever.rewrites.items() if q == r)
            report["systems"][label]["queries_unchanged"] = unchanged
        print(f"  {label:10s} {METRIC} {report['systems'][label][METRIC]:.3f}   "
              f"({report['systems'][label]['seconds']:.0f}s)", flush=True)

    ids = sorted(per_question["baseline"])
    base = [per_question["baseline"][i] for i in ids]
    for label in per_question:
        if label == "baseline":
            continue
        point, low, high = paired(base, [per_question[label][i] for i in ids],
                                  args.rounds, random.Random(f"{args.seed}:{label}"))
        report["systems"][label]["vs_baseline"] = {"difference": point, "interval": [low, high]}

    report["per_question"] = per_question
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'system':10s} {METRIC:>10s} {'full@10':>8s} {'vs baseline':>12s}  95% interval")
    for label in report["systems"]:
        s = report["systems"][label]
        vs = s.get("vs_baseline")
        tail = (f"{vs['difference']:+12.3f}  {vs['interval'][0]:+.3f} to {vs['interval'][1]:+.3f}"
                if vs else f"{'-':>12s}")
        print(f"{label:10s} {s[METRIC]:10.3f} {s['full_recall@10']:8.3f} {tail}")

    for label in report["systems"]:
        examples = report["systems"][label].get("examples")
        if examples:
            print(f"\n{label}, what it did to the first query:")
            print(f"  before: {examples[0]['question']}")
            print(f"  after : {examples[0]['rewritten'][:220]}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
