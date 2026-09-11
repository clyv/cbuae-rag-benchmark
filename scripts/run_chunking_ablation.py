#!/usr/bin/env python3
"""Does chunk size change what retrieval finds?

    python scripts/run_chunking_ablation.py
    python scripts/run_chunking_ablation.py --fast   # skip the reranker

Writes results/chunking.json.

Chunk size is the largest knob in a RAG pipeline that this project had never
turned. Phase 2 picked 512 words with 64 of overlap, and every number reported
since has been measured at that one setting - so the results table compares four
retrievers over a chunking choice that was never itself compared to anything.

`chunk.py` was written for this: it takes `max_tokens` and `overlap` as
arguments, and chunking never changes a chunk's `evidence_id`, because the
benchmark labels name *sections*. The ground truth is therefore valid at every
setting, and the ablation needs no relabelling.

## The hypothesis worth stating before the run

Regulatory sections are already semantic units - one article is one obligation,
bounded by the drafter rather than by a token budget. If that is true, splitting
them should *hurt*: a 128-word window cuts an obligation away from the condition
that governs it, and the embedding of half an article is not half as useful.

The opposite prediction is just as reasonable: long sections dilute a single
embedding across several topics, so splitting should sharpen retrieval.

Both are plausible, which is what makes it worth measuring rather than assuming.

## A note on the cache

Each configuration gets its own embedding cache under the scratchpad rather than
the shared one. The production cache is keyed to the shipped chunking, and
leaving it holding whatever configuration happened to run last would make the
next API start silently re-embed.
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
from regulens.ingest.chunk import chunk_sections, count_tokens  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "chunking.json"
CACHE_DIR = Path(
    REPO_ROOT / ".cache" / "chunking"
)

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# A very large budget means no section is ever split, which is the section-aware
# baseline rather than a size setting - it is what the corpus looks like when the
# drafter's own boundaries are the only ones used.
WHOLE_SECTION = 10**6

CONFIGS: list[tuple[str, int, int]] = [
    ("whole sections", WHOLE_SECTION, 0),
    ("1024 / 128", 1024, 128),
    ("512 / 64", 512, 64),
    ("256 / 32", 256, 32),
    ("128 / 16", 128, 16),
    ("64 / 8", 64, 8),
    # Overlap held against a fixed size, to separate the two effects.
    ("512 / 0", 512, 0),
    ("512 / 192", 512, 192),
]

SHIPPED = "512 / 64"


def load_sections() -> list[Chunk]:
    if not SECTIONS.exists():
        sys.exit(f"{SECTIONS} not found. Run scripts/build_corpus.py first.")
    out = []
    for line in SECTIONS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {})))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true", help="hybrid only, skip the reranker")
    parser.add_argument("--k", type=int, default=10)
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

    rows = []
    for label, max_tokens, overlap in CONFIGS:
        started = time.perf_counter()
        chunks = chunk_sections(sections, max_tokens=max_tokens, overlap=overlap)
        sizes = [count_tokens(c.text) for c in chunks]
        split = sum(1 for c in chunks if "#" in c.chunk_id)

        print(f"  {label:16s} {len(chunks):5d} chunks, median {statistics.median(sizes):4.0f} words", flush=True)

        cache = CACHE_DIR / f"{max_tokens}-{overlap}.npz"
        hybrid = HybridRetriever(
            [BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL, cache=cache)]
        )

        row = {
            "label": label,
            "max_tokens": max_tokens,
            "overlap": overlap,
            "chunks": len(chunks),
            "sections_split": len({c.evidence_id for c in chunks if "#" in c.chunk_id}),
            "chunks_from_splits": split,
            "median_words": statistics.median(sizes),
            "max_words": max(sizes),
        }

        for name, system in [("hybrid", hybrid)] + (
            [] if args.fast else [("hybrid+reranker", RerankedRetriever(hybrid, RERANK_MODEL))]
        ):
            report = evaluate(system, items)
            answerable = [q for q in report.per_question if q.category != "unanswerable"]
            row[name] = {
                "recall@10": statistics.fmean(q.scores["recall@10"] for q in answerable),
                "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
                "mrr": statistics.fmean(q.scores["mrr"] for q in answerable),
            }
            # Per-question scores for the shipped setting, so a paired comparison
            # against any other row is possible without re-running everything.
            row.setdefault("per_question", {})[name] = {
                q.item_id: q.scores["recall@10"] for q in answerable
            }

        row["seconds"] = round(time.perf_counter() - started, 1)
        rows.append(row)
        best = row.get("hybrid+reranker") or row["hybrid"]
        print(f"  {'':16s} recall@10 {best['recall@10']:.3f}   ({row['seconds']:.0f}s)\n", flush=True)

    OUT.write_text(json.dumps({"configs": rows}, indent=2, ensure_ascii=False), encoding="utf-8")

    system_key = "hybrid" if args.fast else "hybrid+reranker"
    print(f"\n{'chunking':16s} {'chunks':>7s} {'median':>7s} {'recall@10':>10s} {'full@10':>8s} {'MRR':>7s}")
    for row in rows:
        scores = row[system_key]
        mark = "  <- shipped" if row["label"] == SHIPPED else ""
        print(f"{row['label']:16s} {row['chunks']:7d} {row['median_words']:7.0f} "
              f"{scores['recall@10']:10.3f} {scores['full_recall@10']:8.3f} {scores['mrr']:7.3f}{mark}")

    baseline = next(r for r in rows if r["label"] == SHIPPED)[system_key]["recall@10"]
    spread = max(r[system_key]["recall@10"] for r in rows) - min(r[system_key]["recall@10"] for r in rows)
    print(f"\nshipped setting  {baseline:.3f}")
    print(f"spread across all settings  {spread:.3f}")
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
