#!/usr/bin/env python3
"""Record what the system actually answers, for a static demo. Phase 5.

    python scripts/export_demo.py

Writes results/demo.json: every benchmark question with the citations the real
stack returned, the relevance scores, and whether the labelled evidence was
found.

## Why a recording rather than a live demo

A shareable page cannot reach a retriever running on a laptop, and embedding a
language model in the page would be a different system answering - which would
misrepresent what was built and measured. So the real stack runs here, once, and
its output is frozen. Every citation, score and verdict on the page is what the
system returned, not a mock-up.

The recording carries something a live demo could not: each question's labelled
evidence, so a reader can see for themselves whether the system found what a
human said was required. That turns the demo into a view of the benchmark rather
than a sales pitch that only shows the questions it gets right.

Excerpts obey the same cap as the API, for the same licensing reason - the page
identifies a provision and links to it, and is not a copy of the Rulebook.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.api.app import MAX_EXCERPT_CHARS  # noqa: E402
from regulens.api.index import Index, load_chunks  # noqa: E402
from regulens.evaluation.metrics import evidence_id  # noqa: E402

BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
OUT = REPO_ROOT / "results" / "demo.json"

# Used only to show the abstention behaviour on the page. It is not a default
# anywhere in the codebase - see results/abstention.md for why one is not
# shipped, and treat this as an illustration rather than a recommendation.
DEMO_THRESHOLD = 5.0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    questions = [
        json.loads(line)
        for line in BENCHMARK.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    index = Index(load_chunks())

    out = []
    for n, item in enumerate(questions, start=1):
        print(f"  [{n}/{len(questions)}] {item['id']}", end="\r", flush=True)
        answer, results = index.answer(item["question"], k=5, rerank=True, threshold=None)

        required = [evidence_id(e["doc_id"], e["section"]) for e in item["required_evidence"]]
        retrieved = [f"{r.chunk.doc_id}::{r.chunk.section}" for r in results]
        found = [r for r in required if r in retrieved]

        by_section = {f"{r.chunk.doc_id}::{r.chunk.section}": r for r in results}
        citations = []
        for citation in answer.citations:
            hit = by_section.get(citation.evidence_id)
            citations.append(
                {
                    "id": citation.evidence_id,
                    "doc_id": citation.doc_id,
                    "section": citation.section,
                    "document": hit.chunk.metadata.get("title", "") if hit else "",
                    "excerpt": citation.quote[:MAX_EXCERPT_CHARS].rstrip(),
                    "url": citation.url,
                    "score": round(hit.score, 2) if hit else 0.0,
                    "required": citation.evidence_id in required,
                }
            )

        out.append(
            {
                "id": item["id"],
                "question": item["question"],
                "category": item["category"],
                "difficulty": item["difficulty"],
                "required": required,
                "found": found,
                "complete": bool(required) and len(found) == len(required),
                "top_score": round(results[0].score, 2) if results else None,
                "would_decline": bool(results) and results[0].score <= DEMO_THRESHOLD,
                "citations": citations,
            }
        )
    print(" " * 40, end="\r")

    OUT.write_text(
        json.dumps(
            {
                "system": "hybrid+reranker",
                "generator": "extractive",
                "k": 5,
                "demo_threshold": DEMO_THRESHOLD,
                "excerpt_cap": MAX_EXCERPT_CHARS,
                "questions": out,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    answerable = [q for q in out if q["required"]]
    print(f"{len(out)} questions recorded -> {OUT.relative_to(REPO_ROOT)}")
    print(f"  complete evidence found : {sum(q['complete'] for q in answerable)}/{len(answerable)}")
    print(f"  unanswerable declined   : "
          f"{sum(q['would_decline'] for q in out if not q['required'])}"
          f"/{sum(1 for q in out if not q['required'])} at threshold {DEMO_THRESHOLD}")
    print(f"  answerable wrongly declined: {sum(q['would_decline'] for q in answerable)}/{len(answerable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
