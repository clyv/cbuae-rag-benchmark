#!/usr/bin/env python3
"""Measure what citation validity costs when a model writes prose.

    python scripts/run_abstractive.py --limit 15     # sanity check
    python scripts/run_abstractive.py                # all 100

Writes results/abstractive.json.

The extractive answerer scores 1.000 grounded and 1.000 supported by
construction. This runs the same retrieval and the same validation against a
local generative model, so the two numbers are directly comparable and the gap
between them is the price of fluency.

Supported is reported at two thresholds. The lenient one is the project default
- four shared content words - which suits an extractive answerer whose quote is
the source text. For a generated claim it is far too easy to pass, since
"company", "board" and "requirements" appear everywhere in this corpus, so the
strict figure requires 60% of the claim's vocabulary to come from the section it
cites. The strict number is the honest one; the lenient one is shown beside it
to make clear how much the threshold matters.
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

from regulens.evaluation.obligation import score_claims  # noqa: E402
from regulens.evaluation.runner import load_benchmark  # noqa: E402
from regulens.generation.abstractive import split_claims  # noqa: E402
from regulens.generation.answer import ExtractiveGenerator, answer_question, validate_citations  # noqa: E402
from regulens.retrieval.base import Chunk  # noqa: E402

CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "abstractive.json"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
STRICT_RATIO = 0.6


def over_attributed(text: str) -> bool:
    """Does any single claim carry more than one passage number?

    A sentence tagged [2][3] credits one claim to two sections, and the quote
    checked against both is the same sentence - so if it came from one of them,
    the other is unsupported by construction. Recorded because it turned out to
    be the dominant failure mode, and separating it keeps the headline number
    from being read as general unreliability.
    """
    return any(len(numbers) > 1 for _, numbers in split_claims(text))


def load_chunks() -> list[Chunk]:
    out = []
    for line in CHUNKS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.append(Chunk(r["chunk_id"], r["doc_id"], r["section"], r["text"], r.get("metadata", {})))
    return out


def _mean(rows: list[dict], key: str) -> float:
    return statistics.fmean(r[key] for r in rows) if rows else 0.0


def obligation_pairs(answer, results) -> list[tuple[str, str]]:
    """Pair each claim with the text of the section it cites.

    Citation validity asks whether a claim's words appear in its source. That
    check passes on "an insurer may appoint an actuary" cited to a section
    saying "shall" - almost every word matches, and the obligation is inverted.
    These pairs are what `score_claims` uses to catch that.
    """
    sources = {f"{r.chunk.doc_id}::{r.chunk.section}": r.chunk.text for r in results}
    return [
        (c.quote, sources[c.evidence_id])
        for c in answer.citations
        if c.evidence_id in sources and c.quote.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=0, help="score only the first N questions")
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from regulens.generation.abstractive import AbstractiveGenerator
    from regulens.retrieval.bm25 import BM25Retriever
    from regulens.retrieval.dense import DenseRetriever
    from regulens.retrieval.hybrid import HybridRetriever
    from regulens.retrieval.rerank import RerankedRetriever

    chunks = load_chunks()
    items = load_benchmark(BENCHMARK)
    if args.limit:
        items = items[: args.limit]

    system = RerankedRetriever(
        HybridRetriever([BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL)]),
        RERANK_MODEL,
    )
    print("loading the generator...", flush=True)
    generator = AbstractiveGenerator()
    extractive = ExtractiveGenerator()

    records = []
    abstractive_pairs: list[tuple[str, str]] = []
    extractive_pairs: list[tuple[str, str]] = []
    started = time.perf_counter()
    for n, item in enumerate(items, start=1):
        elapsed = time.perf_counter() - started
        print(f"  [{n}/{len(items)}] {item.id}  ({elapsed / max(n - 1, 1):.0f}s/q)", end="\r", flush=True)
        results = system.retrieve(item.question, args.k)

        abstractive = answer_question(item.question, results, generator=generator, threshold=None)
        quoted = answer_question(item.question, results, generator=extractive, threshold=None)

        abstractive_pairs += obligation_pairs(abstractive, results)
        extractive_pairs += obligation_pairs(quoted, results)

        lenient = validate_citations(abstractive)
        strict = validate_citations(abstractive, min_overlap_ratio=STRICT_RATIO)
        base = validate_citations(quoted, min_overlap_ratio=STRICT_RATIO)

        records.append(
            {
                "id": item.id,
                "category": item.category,
                "answerable": item.category != "unanswerable",
                "text": abstractive.text,
                "declined": abstractive.abstained,
                "citations": lenient["citations"],
                "grounded": lenient["grounded"],
                "supported_lenient": lenient["supported"],
                "supported_strict": strict["supported"],
                "extractive_supported_strict": base["supported"],
                "over_attributed": over_attributed(abstractive.text),
                "cited": [c.evidence_id for c in abstractive.citations],
                "required": list(item.required),
            }
        )
    print(" " * 60, end="\r")

    cited = [r for r in records if r["citations"]]
    uncited = [r for r in records if not r["citations"] and not r["declined"]]
    declined = [r for r in records if r["declined"]]

    summary = {
        "generator": generator.model_name,
        "k": args.k,
        "strict_ratio": STRICT_RATIO,
        "questions": len(records),
        "answers_with_citations": len(cited),
        "answers_without_citations": len(uncited),
        "declined": len(declined),
        "grounded": statistics.fmean(r["grounded"] for r in cited) if cited else 0.0,
        "supported_lenient": statistics.fmean(r["supported_lenient"] for r in cited) if cited else 0.0,
        "supported_strict": statistics.fmean(r["supported_strict"] for r in cited) if cited else 0.0,
        "extractive_supported_strict": statistics.fmean(
            r["extractive_supported_strict"] for r in records
        ),
        "supported_strict_one_source": _mean(
            [r for r in cited if not r["over_attributed"]], "supported_strict"
        ),
        "supported_strict_over_attributed": _mean(
            [r for r in cited if r["over_attributed"]], "supported_strict"
        ),
        "answers_over_attributed": sum(r["over_attributed"] for r in cited),
        "obligation": score_claims(abstractive_pairs),
        "extractive_obligation": score_claims(extractive_pairs),
        "seconds_per_question": round((time.perf_counter() - started) / len(records), 1),
    }
    OUT.write_text(json.dumps({"summary": summary, "per_question": records}, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"generator   {summary['generator']}")
    print(f"questions   {summary['questions']}  ({summary['seconds_per_question']}s each)")
    print(f"  answers carrying at least one citation : {summary['answers_with_citations']}")
    print(f"  answers with no citation at all        : {summary['answers_without_citations']}")
    print(f"  model declined                         : {summary['declined']}")
    print()
    print(f"  grounded                    {summary['grounded']:.3f}   (extractive: 1.000)")
    print(f"  supported, lenient          {summary['supported_lenient']:.3f}   (extractive: 1.000)")
    print(f"  supported, strict {STRICT_RATIO:.0%} overlap {summary['supported_strict']:.3f}"
          f"   (extractive: {summary['extractive_supported_strict']:.3f})")
    ob, base = summary["obligation"], summary["extractive_obligation"]
    print()
    print(f"  obligation fidelity         {ob['obligation_fidelity']:.3f}"
          f"   (extractive: {base['obligation_fidelity']:.3f})")
    print(f"    of {ob['force_bearing']} claims that state an obligation: "
          f"{ob['preserved']} preserved, {ob['strengthened']} strengthened, "
          f"{ob['weakened']} weakened")
    print(f"    {ob['no_force']} of {ob['claims']} claims state no obligation at all")
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
