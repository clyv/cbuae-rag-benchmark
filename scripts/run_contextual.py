#!/usr/bin/env python3
"""Contextual retrieval: does a generated context sentence beat the title?

    python scripts/run_contextual.py --generate   # writes the contexts, ~40 min
    python scripts/run_contextual.py              # evaluates from the cache

Writes results/contextual.json, and corpus/processed/contexts.json (gitignored
with the rest of the parsed corpus - it is generated text about CBUAE text).

Measured against the strongest configuration found so far rather than the
shipped one, because the interesting question is whether it adds anything to
`results/combined.md`:

    whole sections                      0.791
    whole sections + document title     0.866

so the cells here are context on and off, crossed with title on and off, all at
whole-section chunking. If a generated sentence is only reproducing what the
title already says, the context column will not move the title column.
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
from regulens.ingest.chunk import chunk_sections  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402
from regulens.retrieval.contextual import (  # noqa: E402
    ContextCache,
    build_context,
    contextualise,
    migrate,
)

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "contextual.json"
CACHE_DIR = REPO_ROOT / ".cache" / "contextual"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GENERATOR = "Qwen/Qwen2.5-0.5B-Instruct"
WHOLE_SECTION = 10**6
METRIC = "recall@10"


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


def generate_contexts(chunks: list[Chunk]) -> None:
    from regulens.generation.abstractive import AbstractiveGenerator

    model = AbstractiveGenerator(model_name=GENERATOR, max_new_tokens=48)
    cache = ContextCache(GENERATOR)

    # Entries written under the old text-only key are still good wherever the
    # text was unique, so they are carried forward rather than regenerated.
    carried = migrate(cache.entries, chunks, GENERATOR)
    if carried:
        before = len(cache.entries)
        cache.entries = carried
        cache.save()
        print(f"carried {len(carried)} contexts forward from {before} legacy entries; "
              f"{len(chunks) - len(carried)} to regenerate")
    started = time.perf_counter()
    written = 0

    for n, chunk in enumerate(chunks, start=1):
        if cache.get(chunk) is not None:
            continue
        cache.put(chunk, build_context(lambda p: model._run(p), chunk))
        written += 1
        if written % 25 == 0:
            rate = (time.perf_counter() - started) / written
            left = (len(chunks) - n) * rate
            print(f"  [{n}/{len(chunks)}] {rate:.1f}s each, ~{left / 60:.0f} min left",
                  end="\r", flush=True)
            cache.save()  # checkpoint, so an interrupted run resumes

    cache.save()
    print(" " * 70, end="\r")
    print(f"generated {written} contexts ({len(cache)} cached) in "
          f"{(time.perf_counter() - started) / 60:.0f} min")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--generate", action="store_true", help="write the context sentences first")
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sections = load_sections()
    chunks = chunk_sections(sections, max_tokens=WHOLE_SECTION, overlap=0)

    if args.generate:
        generate_contexts(chunks)

    cache = ContextCache(GENERATOR)
    contexts = {c.chunk_id: (cache.get(c) or "") for c in chunks}
    have = sum(1 for v in contexts.values() if v)
    if not have:
        sys.exit("No contexts cached. Run with --generate first.")
    print(f"{have} of {len(chunks)} chunks have a context sentence\n")

    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    items = load_benchmark(BENCHMARK)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    contextual_chunks = contextualise(chunks, contexts)

    cells = [
        ("whole sections", chunks, False),
        ("+ title", chunks, True),
        ("+ context", contextual_chunks, False),
        ("+ context + title", contextual_chunks, True),
    ]

    per_question: dict[str, dict[str, float]] = {}
    summary: dict[str, dict] = {}

    for label, cell_chunks, title in cells:
        system = RerankedRetriever(
            HybridRetriever([
                BM25Retriever(cell_chunks, include_doc_title=title),
                DenseRetriever(cell_chunks, DENSE_MODEL,
                               cache=CACHE_DIR / f"{label.replace(' ', '_').replace('+', 'p')}.npz",
                               include_doc_title=title),
            ]),
            RERANK_MODEL,
        )
        report = evaluate(system, items)
        answerable = [q for q in report.per_question if q.category != "unanswerable"]
        per_question[label] = {q.item_id: q.scores[METRIC] for q in answerable}
        summary[label] = {
            METRIC: statistics.fmean(q.scores[METRIC] for q in answerable),
            "full_recall@10": statistics.fmean(q.scores["full_recall@10"] for q in answerable),
        }
        print(f"  {label:20s} {METRIC} {summary[label][METRIC]:.3f}", flush=True)

    ids = sorted(per_question["whole sections"])
    base = [per_question["whole sections"][i] for i in ids]
    for label in summary:
        if label == "whole sections":
            continue
        point, low, high = paired(base, [per_question[label][i] for i in ids],
                                  args.rounds, random.Random(f"{args.seed}:{label}"))
        summary[label]["vs_whole_sections"] = {"difference": point, "interval": [low, high]}

    samples = [
        {"chunk_id": c.chunk_id, "section": c.section,
         "doc_title": c.metadata.get("doc_title", "")[:70], "context": contexts[c.chunk_id]}
        for c in chunks[:400] if contexts[c.chunk_id]
    ][:8]

    OUT.write_text(json.dumps({"metric": METRIC, "generator": GENERATOR,
                               "chunks": len(chunks), "with_context": have,
                               "cells": summary, "samples": samples,
                               "per_question": per_question},
                              indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'configuration':20s} {METRIC:>10s} {'full@10':>8s} {'vs base':>9s}  95% interval")
    for label, _, _ in cells:
        s = summary[label]
        vs = s.get("vs_whole_sections")
        tail = (f"{vs['difference']:+9.3f}  {vs['interval'][0]:+.3f} to {vs['interval'][1]:+.3f}"
                if vs else f"{'-':>9s}")
        print(f"{label:20s} {s[METRIC]:10.3f} {s['full_recall@10']:8.3f} {tail}")

    print("\nwhat the model wrote, first few:")
    for sample in samples[:4]:
        print(f"  {sample['chunk_id'][:44]}")
        print(f"    {sample['context'][:150]}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
