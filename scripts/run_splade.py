#!/usr/bin/env python3
"""A fifth retrieval system: learned sparse, alone and fused.

    python scripts/run_splade.py

Writes results/splade.json.

The results table compares four systems: BM25, dense, their fusion, and that
fusion reranked. SPLADE is the family none of them covers - sparse like BM25, so
it scores through term matches, but with learned weights that put mass on terms
the passage never uses. On a passage about "deviation from the Risk Appetite" it
weights *appetite*, *deviation*, *board* and *approval* from the text, and
expands to *hunger*, *risks* and *approved*, which are not in it.

Two questions, and they are different:

1. **Alone**, does learned sparse beat BM25 and dense on this corpus? It is the
   one family that could fix paraphrase without giving up lexical precision.
2. **Fused**, does adding it to the existing hybrid help? Reciprocal rank fusion
   takes any number of rankers, so a three-way fusion costs one line - and if
   SPLADE finds the same documents BM25 already finds, it adds nothing but
   latency.

The prediction, recorded first: `results/model_sweep.md` established that n=100
cannot resolve a +0.023 effect. Unless learned sparse is dramatically better or
worse here, the honest outcome is another interval containing zero - which is
itself the finding the sweep pointed at.
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

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "splade.json"

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
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever
    from regulens.retrieval.splade import SpladeRetriever

    chunks = load_chunks()
    items = load_benchmark(BENCHMARK)

    bm25 = BM25Retriever(chunks)
    dense = DenseRetriever(chunks, DENSE_MODEL)
    print("encoding the corpus with the sparse model...", flush=True)
    started = time.perf_counter()
    splade = SpladeRetriever(chunks)
    encode_seconds = time.perf_counter() - started
    nonzero = float((splade.matrix > 0).sum(axis=1).mean())
    print(f"  {encode_seconds:.0f}s, mean {nonzero:.0f} non-zero terms per chunk "
          f"of {splade.matrix.shape[1]}\n", flush=True)

    hybrid2 = HybridRetriever([bm25, dense])
    hybrid3 = HybridRetriever([bm25, dense, splade])

    systems = [
        ("splade", splade),
        ("bm25 + dense", hybrid2),
        ("bm25 + dense + splade", hybrid3),
        ("bm25 + dense + reranker", RerankedRetriever(hybrid2, RERANK_MODEL)),
        ("bm25 + dense + splade + reranker", RerankedRetriever(hybrid3, RERANK_MODEL)),
    ]

    per_question: dict[str, dict[str, float]] = {}
    rows: list[dict] = []

    for label, system in systems:
        began = time.perf_counter()
        report = evaluate(system, items)
        answerable = [q for q in report.per_question if q.category != "unanswerable"]
        per_question[label] = {q.item_id: q.scores[METRIC] for q in answerable}
        rows.append({
            "label": label,
            METRIC: statistics.fmean(q.scores[METRIC] for q in answerable),
            "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
            "mrr": statistics.fmean(q.scores["mrr"] for q in answerable),
            "seconds": round(time.perf_counter() - began, 1),
        })
        print(f"  {label:34s} {METRIC} {rows[-1][METRIC]:.3f}  ({rows[-1]['seconds']:.0f}s)", flush=True)

    shipped = "bm25 + dense + reranker"
    ids = sorted(per_question[shipped])
    base = [per_question[shipped][i] for i in ids]
    for row in rows:
        if row["label"] == shipped:
            continue
        point, low, high = paired(base, [per_question[row["label"]][i] for i in ids],
                                  args.rounds, random.Random(f"{args.seed}:{row['label']}"))
        row["vs_shipped"] = {"difference": point, "interval": [low, high]}

    sample = splade.expansion_for(
        "A documented process for the Board approval for any deviation from the Risk Appetite.",
        top=12,
    )
    OUT.write_text(json.dumps({
        "metric": METRIC, "model": splade.model_name, "shipped": shipped,
        "encode_seconds": round(encode_seconds, 1),
        "mean_nonzero_terms": round(nonzero, 1),
        "vocabulary": int(splade.matrix.shape[1]),
        "expansion_sample": sample, "rows": rows, "per_question": per_question,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'system':34s} {METRIC:>10s} {'full@10':>8s} {'vs shipped':>11s}  95% interval")
    for row in sorted(rows, key=lambda r: -r[METRIC]):
        vs = row.get("vs_shipped")
        tail = (f"{vs['difference']:+11.3f}  {vs['interval'][0]:+.3f} to {vs['interval'][1]:+.3f}"
                if vs else f"{'(shipped)':>11s}")
        print(f"{row['label']:34s} {row[METRIC]:10.3f} {row['full_recall@10']:8.3f} {tail}")

    print("\nwhat the sparse model weights for a risk-appetite passage:")
    print("  " + ", ".join(f"{t} {w}" for t, w in sample[:10]))
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
