#!/usr/bin/env python3
"""Does the corpus's own cross-reference graph help retrieval?

    python scripts/run_graph_eval.py --ceiling-only   # seconds, no models
    python scripts/run_graph_eval.py                  # full, loads models

Writes results/graph_eval.json.

Three measurements, cheapest first, because the cheap ones can settle the
question before the expensive one runs:

**The premise.** Phase 6 assumes that when a question needs two provisions, the
regulation links them. That is checkable directly: how many co-required pairs in
the benchmark are joined by an explicit reference? If the answer is near zero,
no expansion strategy can work, because the structure being followed is not the
structure the questions need.

**The ceiling.** For each system already measured, how many questions could a
perfect expansion rescue - where a required section that retrieval missed sits
within one, two or three hops of something it found? This bounds *any* expansion
policy, not just the one implemented here, which makes it stronger evidence than
a single retriever run.

**The measurement.** Then actually run it, because "cannot help" and "actively
hurts" are different claims and only the second needs a retriever to establish.
Expansion adds candidates before the reranker, so what is measured is whether
the graph puts anything worth ranking in front of it.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.evaluation.runner import evaluate, load_benchmark  # noqa: E402
from regulens.graph.references import build_adjacency, extract_references  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
RESULTS = REPO_ROOT / "results"
OUT = RESULTS / "graph_eval.json"

BASELINES = ["bm25", "dense", "hybrid-rrf", "hybrid+reranker"]
PRODUCTION = "hybrid+reranker"
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reachable(adjacency: dict[str, list[str]], seed: set[str], hops: int) -> set[str]:
    frontier, seen = set(seed), set()
    for _ in range(hops):
        nxt: set[str] = set()
        for node in frontier:
            nxt.update(adjacency.get(node, []))
        nxt -= seen
        seen |= nxt
        frontier = nxt
    return seen


def paired_difference(a: list[float], b: list[float], rounds: int, rng: random.Random):
    """Mean of (b - a) with a 95% interval, resampling question indices jointly."""
    diffs = [b[i] - a[i] for i in range(len(a))]
    point = statistics.fmean(diffs)
    means = sorted(statistics.fmean(diffs[rng.randrange(len(diffs))] for _ in diffs) for _ in range(rounds))
    return point, means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ceiling-only", action="store_true", help="skip the retriever run")
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sections = load_jsonl(SECTIONS)
    references, census = extract_references(sections)
    adjacency = build_adjacency(references)
    benchmark = {row["id"]: row for row in load_jsonl(BENCHMARK)}
    required_of = {
        qid: {f"{e['doc_id']}::{e['section']}" for e in row["required_evidence"]}
        for qid, row in benchmark.items()
    }

    report: dict = {"edges": len(references), "census": census}

    # --- the premise --------------------------------------------------------
    pairs = adjacent = 0
    for qid, required in required_of.items():
        for a, b in combinations(sorted(required), 2):
            pairs += 1
            adjacent += b in adjacency.get(a, [])
    report["co_required_pairs"] = pairs
    report["co_required_pairs_linked"] = adjacent

    print("PREMISE - when a question needs two provisions, does the text link them?")
    print(f"  {adjacent} of {pairs} co-required section pairs are joined by an explicit reference"
          f"  ({adjacent / pairs:.1%})\n")

    # --- the ceiling --------------------------------------------------------
    print("CEILING - questions a perfect expansion could rescue, by hop depth")
    print(f"  {'system':22s} {'missing':>8s} {'1 hop':>7s} {'2 hop':>7s} {'3 hop':>7s}")
    ceilings: dict[str, dict] = {}
    for name in BASELINES:
        path = RESULTS / f"{name}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))["per_question"]
        missing = 0
        rescued = {1: 0, 2: 0, 3: 0}
        rescued_ids: list[str] = []
        for row in rows:
            required = required_of[row["id"]]
            if not required:
                continue
            retrieved = set(row["retrieved"])
            missed = required - retrieved
            if not missed:
                continue
            missing += 1
            for hops in (1, 2, 3):
                if missed & reachable(adjacency, retrieved, hops):
                    rescued[hops] += 1
                    if hops == 1:
                        rescued_ids.append(row["id"])
        ceilings[name] = {"missing_evidence": missing, "rescued": rescued, "rescued_at_1_hop": rescued_ids}
        print(f"  {name:22s} {missing:8d} {rescued[1]:7d} {rescued[2]:7d} {rescued[3]:7d}")
    report["ceiling"] = ceilings

    required_sections = {s for r in required_of.values() for s in r}
    report["required_sections"] = len(required_sections)
    report["required_sections_in_graph"] = len(required_sections & set(adjacency))
    print(f"\n  {report['required_sections_in_graph']} of {report['required_sections']} distinct "
          f"required sections have any edge at all")

    if args.ceiling_only:
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {OUT.relative_to(REPO_ROOT)}  (ceiling only)")
        return 0

    # --- the measurement ----------------------------------------------------
    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.graph_expand import GraphExpandedRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    chunks = [
        Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {}))
        for r in load_jsonl(CHUNKS)
    ]
    items = load_benchmark(BENCHMARK)

    print("\nbuilding the index...", flush=True)
    hybrid = HybridRetriever([BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL)])
    expanded = GraphExpandedRetriever(hybrid, adjacency, chunks)
    system = RerankedRetriever(expanded, RERANK_MODEL)
    system.name = "graph-expanded+reranker"

    added = [expanded.expansion_size(item.question) for item in items]
    report["sections_added_per_query"] = {
        "mean": round(statistics.fmean(added), 2),
        "median": statistics.median(added),
        "max": max(added),
        "queries_with_no_expansion": sum(1 for a in added if a == 0),
    }
    print(f"expansion adds a median of {statistics.median(added):.0f} sections per query "
          f"({report['sections_added_per_query']['queries_with_no_expansion']} of {len(added)} "
          f"queries get none)")

    started = time.perf_counter()
    result = evaluate(system, items)
    report["seconds"] = round(time.perf_counter() - started, 1)

    baseline = json.loads((RESULTS / f"{PRODUCTION}.json").read_text(encoding="utf-8"))
    base_by_id = {q["id"]: q for q in baseline["per_question"]}
    metric = f"recall@{args.k}"

    ids = [q.item_id for q in result.per_question if q.category != "unanswerable"]
    ours = [q.scores[metric] for q in result.per_question if q.category != "unanswerable"]
    theirs = [base_by_id[i]["scores"][metric] for i in ids]

    rng = random.Random(f"{args.seed}:graph")
    point, low, high = paired_difference(theirs, ours, args.rounds, rng)
    report["measured"] = {
        "metric": metric,
        "baseline": statistics.fmean(theirs),
        "graph_expanded": statistics.fmean(ours),
        "difference": point,
        "interval": [low, high],
        "questions": len(ids),
        "changed": [i for i, a, b in zip(ids, theirs, ours) if a != b],
    }
    report["per_question"] = [
        {"id": q.item_id, "category": q.category, "scores": q.scores, "retrieved": q.retrieved}
        for q in result.per_question
    ]

    print(f"\nMEASURED - {metric} over {len(ids)} answerable questions")
    print(f"  {PRODUCTION:24s} {statistics.fmean(theirs):.3f}")
    print(f"  graph-expanded           {statistics.fmean(ours):.3f}")
    print(f"  difference               {point:+.3f}   95% interval {low:+.3f} to {high:+.3f}")
    if report["measured"]["changed"]:
        print(f"  questions that changed   {', '.join(report['measured']['changed'])}")
    else:
        print("  questions that changed   none")

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
