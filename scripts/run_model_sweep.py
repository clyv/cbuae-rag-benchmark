#!/usr/bin/env python3
"""Does the choice of embedding model and reranker matter here?

    python scripts/run_model_sweep.py
    python scripts/run_model_sweep.py --embeddings-only

Writes results/model_sweep.json.

The results table compares four *architectures* while holding the models fixed:
bge-small for embeddings, ms-marco-MiniLM-L-6 for reranking. Both were chosen in
Phase 4 for size and speed, and `rerank.py` has carried a note since then saying
the larger reranker is "the obvious next experiment if the reranker earns its
place". It earned it. This is that experiment.

It matters more than it would have before. `results/combined.md` showed two
configuration choices worth 69% of the entire architecture gap, which makes the
question sharp: how much of a reported RAG result is the technique, and how much
is everything around it that nobody varied?

## Fairness

Each embedding model gets its own query and passage prefixes from
`instructions_for`. BGE instructs the query only, E5 prefixes both sides, GTE
neither. Running E5 with BGE's instruction, or with none, would measure the
prefix rather than the model - a mistake that quietly understates every
alternative and flatters the incumbent.

Every configuration is measured on the same chunks, the same questions and the
same metric, and each caches its embeddings separately so the shipped index is
untouched.
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
OUT = REPO_ROOT / "results" / "model_sweep.json"
CACHE_DIR = REPO_ROOT / ".cache" / "sweep"

SHIPPED_EMBED = "BAAI/bge-small-en-v1.5"
SHIPPED_RERANK = "cross-encoder/ms-marco-MiniLM-L-6-v2"

EMBEDDINGS = [SHIPPED_EMBED, "BAAI/bge-base-en-v1.5", "intfloat/e5-base-v2"]
RERANKERS = [SHIPPED_RERANK, "BAAI/bge-reranker-base"]
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
    parser.add_argument("--embeddings-only", action="store_true")
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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    bm25 = BM25Retriever(chunks)

    rows: list[dict] = []
    per_question: dict[str, dict[str, float]] = {}

    for embed in EMBEDDINGS:
        started = time.perf_counter()
        print(f"  {embed} ...", flush=True)
        try:
            dense = DenseRetriever(chunks, embed, cache=CACHE_DIR / f"{embed.replace('/', '_')}.npz")
        except Exception as exc:  # a model that will not load is a result, not a crash
            print(f"    could not load: {type(exc).__name__}: {exc}", flush=True)
            rows.append({"embedding": embed, "error": f"{type(exc).__name__}: {exc}"})
            continue

        hybrid = HybridRetriever([bm25, dense])
        rerankers = [None] if args.embeddings_only else [None] + RERANKERS

        for rerank in rerankers:
            label = f"{embed} + {rerank}" if rerank else f"{embed} (hybrid only)"
            try:
                system = RerankedRetriever(hybrid, rerank) if rerank else hybrid
                report = evaluate(system, items)
            except Exception as exc:
                print(f"    {rerank}: could not load: {type(exc).__name__}", flush=True)
                rows.append({"embedding": embed, "reranker": rerank,
                             "error": f"{type(exc).__name__}: {exc}"})
                continue

            answerable = [q for q in report.per_question if q.category != "unanswerable"]
            per_question[label] = {q.item_id: q.scores[METRIC] for q in answerable}
            rows.append({
                "embedding": embed,
                "reranker": rerank,
                "label": label,
                "dimensions": int(dense.embeddings.shape[1]),
                METRIC: statistics.fmean(q.scores[METRIC] for q in answerable),
                "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
                "mrr": statistics.fmean(q.scores["mrr"] for q in answerable),
            })
            print(f"    {rerank or 'no reranker':40s} {METRIC} {rows[-1][METRIC]:.3f}", flush=True)

        print(f"    ({time.perf_counter() - started:.0f}s)", flush=True)

    shipped_label = f"{SHIPPED_EMBED} + {SHIPPED_RERANK}"
    if shipped_label in per_question:
        ids = sorted(per_question[shipped_label])
        base = [per_question[shipped_label][i] for i in ids]
        for row in rows:
            if row.get("label") in per_question and row["label"] != shipped_label:
                point, low, high = paired(
                    base, [per_question[row["label"]][i] for i in ids],
                    args.rounds, random.Random(f"{args.seed}:{row['label']}"))
                row["vs_shipped"] = {"difference": point, "interval": [low, high]}

    OUT.write_text(json.dumps({"metric": METRIC, "shipped": shipped_label, "rows": rows,
                               "per_question": per_question}, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    scored = [r for r in rows if METRIC in r]
    scored.sort(key=lambda r: -r[METRIC])
    print(f"\n{'configuration':62s} {'dim':>4s} {METRIC:>10s} {'vs shipped':>11s}")
    for row in scored:
        vs = row.get("vs_shipped")
        tail = f"{vs['difference']:+11.3f}" if vs else ("   (shipped)" if row["label"] == shipped_label else "")
        print(f"{row['label'][:62]:62s} {row['dimensions']:4d} {row[METRIC]:10.3f} {tail}")

    failed = [r for r in rows if "error" in r]
    if failed:
        print("\ncould not be measured:")
        for row in failed:
            print(f"  {row.get('embedding')} / {row.get('reranker')}: {row['error'][:80]}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
