#!/usr/bin/env python3
"""Does indexing the instrument's own title stop the twins beating each other?

    python scripts/run_doc_title.py
    python scripts/run_doc_title.py --fast   # hybrid only

Writes results/doc_title.json.

## Where this came from

Not from a blog post. `scripts/analyse_failures.py` classified every missed
section and found that **15% of them are the right provision retrieved from the
wrong instrument** - `INS-FIN-002::Section 2, Article 1` returned when the answer
is in `INS-FIN-001::Section 2, Article 1`.

Those two sections carry the same article number, the same heading ("Article (1)
- Minimum Capital Requirement"), and near-identical bodies. The single word that
tells them apart is *Takaful*, and it appears only in the document title - which
`indexable_text` did not index, because `section_title` equals the document title
for just 44 of 763 sections.

So the fix is one line, and it is the cheap deterministic form of what the
literature calls contextual retrieval: give each chunk enough context to know
which document it belongs to.

## What it might cost

Every chunk gains a dozen words of formal boilerplate - "Insurance Authority
Board Decision Number (25) of 2014 Pertinent to..." - identical across all 74
sections of that instrument. In a dense embedding that dilutes the body's own
meaning; in BM25 those terms have high document frequency and are discounted to
nearly nothing, but they still lengthen every document and BM25 normalises by
length.

The prediction worth writing down first: this should help `comparative` and
`adversarial` questions, where the twins compete, and do nothing or slightly
hurt elsewhere. A single overall number would hide both halves, so the report
breaks the change out by category and names every question that moved.
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
from regulens.retrieval.base import Chunk  # noqa: E402

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "doc_title.json"
CACHE_DIR = REPO_ROOT / ".cache" / "doc_title"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
METRIC = "recall@10"


def load_chunks() -> list[Chunk]:
    return [
        Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {}))
        for r in (json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip())
    ]


def paired_difference(a: list[float], b: list[float], rounds: int, rng: random.Random):
    diffs = [b[i] - a[i] for i in range(len(a))]
    point = statistics.fmean(diffs)
    means = sorted(statistics.fmean(diffs[rng.randrange(len(diffs))] for _ in diffs) for _ in range(rounds))
    return point, means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true")
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

    scores: dict[str, dict[str, dict[str, float]]] = {}
    categories: dict[str, str] = {}

    for setting in (False, True):
        label = "with title" if setting else "baseline"
        print(f"building index, {label}...", flush=True)
        hybrid = HybridRetriever([
            BM25Retriever(chunks, include_doc_title=setting),
            DenseRetriever(chunks, DENSE_MODEL,
                           cache=CACHE_DIR / f"title-{int(setting)}.npz",
                           include_doc_title=setting),
        ])
        systems = [("hybrid", hybrid)]
        if not args.fast:
            systems.append(("hybrid+reranker", RerankedRetriever(hybrid, RERANK_MODEL)))

        for name, system in systems:
            report = evaluate(system, items)
            answerable = [q for q in report.per_question if q.category != "unanswerable"]
            scores.setdefault(name, {})[label] = {q.item_id: q.scores[METRIC] for q in answerable}
            for q in answerable:
                categories[q.item_id] = q.category
            print(f"  {name:16s} {label:11s} {METRIC} "
                  f"{statistics.fmean(q.scores[METRIC] for q in answerable):.3f}", flush=True)

    report: dict = {"metric": METRIC, "systems": {}}
    for name, byset in scores.items():
        ids = sorted(byset["baseline"])
        base = [byset["baseline"][i] for i in ids]
        titled = [byset["with title"][i] for i in ids]
        point, low, high = paired_difference(base, titled, args.rounds,
                                             random.Random(f"{args.seed}:{name}"))
        moved = [
            {"id": i, "category": categories[i],
             "baseline": byset["baseline"][i], "with_title": byset["with title"][i]}
            for i in ids if byset["baseline"][i] != byset["with title"][i]
        ]
        by_cat: dict[str, dict] = {}
        for cat in sorted(set(categories.values())):
            sel = [i for i in ids if categories[i] == cat]
            by_cat[cat] = {
                "n": len(sel),
                "baseline": statistics.fmean(byset["baseline"][i] for i in sel),
                "with_title": statistics.fmean(byset["with title"][i] for i in sel),
            }
        report["systems"][name] = {
            "baseline": statistics.fmean(base),
            "with_title": statistics.fmean(titled),
            "difference": point,
            "interval": [low, high],
            "questions_improved": sum(1 for m in moved if m["with_title"] > m["baseline"]),
            "questions_worsened": sum(1 for m in moved if m["with_title"] < m["baseline"]),
            "by_category": by_cat,
            "moved": moved,
        }

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for name, r in report["systems"].items():
        print(f"\n{name}  ({METRIC}, 86 answerable questions)")
        print(f"  baseline     {r['baseline']:.3f}")
        print(f"  with title   {r['with_title']:.3f}")
        print(f"  difference   {r['difference']:+.3f}   95% interval "
              f"{r['interval'][0]:+.3f} to {r['interval'][1]:+.3f}")
        print(f"  {r['questions_improved']} questions improved, {r['questions_worsened']} worsened")
        print(f"\n  {'category':16s} {'baseline':>9s} {'with title':>11s} {'change':>8s}")
        for cat, c in r["by_category"].items():
            delta = c["with_title"] - c["baseline"]
            print(f"  {cat:16s} {c['baseline']:9.3f} {c['with_title']:11.3f} {delta:+8.3f}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
