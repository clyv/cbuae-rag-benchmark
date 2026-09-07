#!/usr/bin/env python3
"""Build the cross-reference graph over the parsed corpus.

    python scripts/build_graph.py
    python scripts/build_graph.py --audit 15    # print sampled edges to check

Writes two things:

  corpus/processed/references.jsonl   every edge with the phrase that produced
                                      it, for auditing. Gitignored with the rest
                                      of the parsed corpus - it quotes source
                                      text, and SOURCES.md does not permit
                                      redistributing that.

  results/graph.json                  the census and the edge list as bare
                                      section identifiers. Structure, not text,
                                      so it is committed and the finding stays
                                      reproducible without the corpus.

The census is the point of the report. A graph is only worth following if the
edges exist, and printing how many references were dropped - and why - is what
distinguishes a sparse corpus from a broken extractor.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.graph.references import (  # noqa: E402
    build_adjacency,
    companion_documents,
    extract_references,
)

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
EDGES = REPO_ROOT / "corpus" / "processed" / "references.jsonl"
REPORT = REPO_ROOT / "results" / "graph.json"


def load_sections() -> list[dict]:
    if not SECTIONS.exists():
        sys.exit(f"{SECTIONS} not found. Run scripts/build_corpus.py first.")
    return [
        json.loads(line)
        for line in SECTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--audit", type=int, default=0, help="print N sampled edges")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sections = load_sections()
    references, census = extract_references(sections)
    adjacency = build_adjacency(references)
    companions = companion_documents(sections)

    EDGES.write_text(
        "\n".join(
            json.dumps(
                {"source": r.source, "target": r.target, "number": r.number, "phrase": r.phrase},
                ensure_ascii=False,
            )
            for r in references
        ),
        encoding="utf-8",
    )

    cross = [r for r in references if r.cross_document]
    report = {
        "sections": len(sections),
        "documents": len({s["doc_id"] for s in sections}),
        "census": census,
        "edges": len(references),
        "cross_document_edges": len(cross),
        "sections_with_any_edge": len(adjacency),
        "companion_pairs": companions,
        "edge_list": [[r.source, r.target] for r in references],
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"sections {len(sections)} in {report['documents']} documents\n")
    print("references found and what became of them")
    order = [
        ("mentions", "Article/Clause mentions"),
        ("self", "self-references, dropped"),
        ("external", "point outside the corpus, dropped"),
        ("unresolved_other_instrument", "name an instrument not recognised"),
        ("unresolved_target", "target section does not exist or is ambiguous"),
        ("resolved_intra", "resolved within a document"),
        ("resolved_cross", "resolved across documents"),
    ]
    for key, label in order:
        print(f"  {census[key]:5d}  {label}")

    print()
    print(f"edges                    {len(references)}")
    print(f"  cross-document         {len(cross)}")
    print(f"sections with any edge   {len(adjacency)} of {len(sections)}"
          f"  ({len(adjacency) / len(sections):.0%})")
    print(f"companion pairs found    {len(companions) // 2}")

    if args.audit:
        print("\nsampled edges")
        random.seed(0)
        for reference in random.sample(references, min(args.audit, len(references))):
            print(f"  {reference.source}")
            print(f"    -> {reference.target}")
            print(f"       ...{reference.phrase[:100]}...")

    if cross:
        print("\nevery cross-document edge")
        for reference in cross:
            print(f"  {reference.source}  ->  {reference.target}")

    print(f"\nWrote {EDGES.relative_to(REPO_ROOT)} and {REPORT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
