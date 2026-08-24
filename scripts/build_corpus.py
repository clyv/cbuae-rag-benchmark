#!/usr/bin/env python3
"""corpus/raw -> corpus/processed. Phase 2.

Parses every downloaded instrument into citable sections, splits oversized
sections into retrievable chunks, and writes both to corpus/processed/ as JSONL
alongside a report of what happened.

    python scripts/build_corpus.py
    python scripts/build_corpus.py --max-tokens 384 --overlap 48

Two outputs, deliberately kept separate:

    sections.jsonl   one record per citable section. This is the vocabulary
                     benchmark labels are written against - when labelling a
                     question, the section values here are the ones to cite.
    chunks.jsonl     one record per indexed unit. Several chunks may share a
                     section, and therefore an evidence_id.

The chunking parameters are recorded in the report so a run can be reproduced,
and so a later fixed-size-versus-section-aware ablation has a baseline to
compare against.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from regulens.ingest.chunk import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP, chunk_sections, count_tokens
from regulens.ingest.parse import parse_html

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "corpus" / "registry.csv"
RAW_DIR = REPO_ROOT / "corpus" / "raw"
PROCESSED_DIR = REPO_ROOT / "corpus" / "processed"

# Registry columns copied onto every chunk, so a retrieval result can be cited
# and date-checked without going back to the registry.
CARRIED_COLUMNS = [
    "title",
    "doc_type",
    "url",
    "effective_date",
    "status",
    "code",
    "parent_doc_id",
]


@dataclass
class DocStats:
    doc_id: str
    sections: int
    chunks: int
    words: int
    warnings: int


def load_registry() -> list[dict[str, str]]:
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rows = load_registry()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_sections = []
    all_chunks = []
    stats: list[DocStats] = []
    warnings: list[str] = []
    missing: list[str] = []

    for row in rows:
        doc_id = row["doc_id"]
        path = RAW_DIR / f"{doc_id}.html"
        if not path.exists():
            missing.append(doc_id)
            continue

        parsed = parse_html(path.read_text(encoding="utf-8"), doc_id)
        warnings.extend(parsed.warnings)

        carried = {key: row.get(key, "") for key in CARRIED_COLUMNS}
        sections = [
            replace(section, metadata={**section.metadata, **carried})
            for section in parsed.sections
        ]
        chunks = chunk_sections(sections, max_tokens=args.max_tokens, overlap=args.overlap)

        all_sections.extend(sections)
        all_chunks.extend(chunks)
        stats.append(
            DocStats(
                doc_id=doc_id,
                sections=len(sections),
                chunks=len(chunks),
                words=sum(count_tokens(s.text) for s in sections),
                warnings=len(parsed.warnings),
            )
        )

    def write(name: str, items: list) -> Path:
        target = PROCESSED_DIR / name
        with target.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
        return target

    write("sections.jsonl", all_sections)
    write("chunks.jsonl", all_chunks)

    words = sum(s.words for s in stats)
    section_words = [count_tokens(s.text) for s in all_sections]
    oversized = sum(1 for w in section_words if w > args.max_tokens)
    label_kinds = Counter(
        "numbered" if any(ch.isdigit() for ch in s.section) else "prose"
        for s in all_sections
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunking": {"max_tokens": args.max_tokens, "overlap": args.overlap, "unit": "whitespace words"},
        "documents": len(stats),
        "documents_missing_raw_file": missing,
        "sections": len(all_sections),
        "chunks": len(all_chunks),
        "words": words,
        "sections_over_budget": oversized,
        "median_section_words": sorted(section_words)[len(section_words) // 2] if section_words else 0,
        "largest_section_words": max(section_words) if section_words else 0,
        "section_label_kinds": dict(label_kinds),
        "duplicate_evidence_ids": len(all_sections) - len({s.evidence_id for s in all_sections}),
        "warnings": warnings,
        "per_document": [asdict(s) for s in stats],
    }
    (PROCESSED_DIR / "ingest_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"documents          {len(stats)}")
    print(f"sections           {len(all_sections)}")
    print(f"chunks             {len(all_chunks)}  (max_tokens={args.max_tokens}, overlap={args.overlap})")
    print(f"words              {words:,}")
    print(f"median section     {report['median_section_words']} words")
    print(f"largest section    {report['largest_section_words']} words")
    print(f"sections > budget  {oversized}")
    print(f"label kinds        {dict(label_kinds)}")
    print(f"duplicate evidence ids {report['duplicate_evidence_ids']}")
    if missing:
        print(f"\nNo raw file for: {', '.join(missing)}")
    if warnings:
        print(f"\n{len(warnings)} parser warning(s); see corpus/processed/ingest_report.json")
        for note in warnings[:10]:
            print(f"  {note}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
