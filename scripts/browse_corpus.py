#!/usr/bin/env python3
"""Read the parsed corpus while labelling. Phase 3 aid.

    python scripts/browse_corpus.py --docs
    python scripts/browse_corpus.py --toc INS-GOV-003
    python scripts/browse_corpus.py --show INS-GOV-003 "Article 3"
    python scripts/browse_corpus.py --find "risk appetite"

## A warning about --find, which is the whole reason browsing comes first

Writing questions by searching for keywords biases the benchmark toward
questions that keyword search can already answer. If every question is found by
typing a phrase and taking whatever comes back, the evidence sets will be
exactly the passages containing that phrase - and BM25 will score well on the
resulting benchmark not because it is good, but because the benchmark was built
through a lexical lens. Systems 2, 3 and 4 would then be measured on a test
designed around system 1's strengths.

That failure is invisible in the results table. It looks like "hybrid retrieval
adds little", which is precisely the conclusion the project exists to test.

So: **browse by structure to choose what to ask about, then read the article.**
Use --find to check whether something exists or to locate a definition you half
remember, not to decide what the question should be. `benchmark/PLAN.md` records
this alongside the rest of the labelling protocol.

The scoring here is deliberately crude - term overlap, no stemming, no BM25
weighting - so that it stays useful for lookup while being obviously unfit as a
retrieval baseline. The real BM25 system is built and measured in Phase 4.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"

# Matches build_corpus.PLACEHOLDER_WORD_LIMIT. A document under this is one the
# Rulebook lists without publishing, so it holds nothing to cite even though it
# is perfectly labelling-eligible on paper.
PLACEHOLDER_WORD_LIMIT = 50


def load() -> list[dict]:
    if not SECTIONS.exists():
        sys.exit(
            f"{SECTIONS.relative_to(REPO_ROOT)} not found. "
            "Run scripts/build_corpus.py first."
        )
    return [
        json.loads(line)
        for line in SECTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def eligible(record: dict) -> bool:
    return (record["metadata"].get("labelling_eligible") or "true") != "false"


def flag(record: dict) -> str:
    return "" if eligible(record) else "  [NOT CITABLE]"


def list_documents(records: list[dict], only_citable: bool) -> None:
    seen: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    words: Counter[str] = Counter()
    for record in records:
        seen.setdefault(record["doc_id"], record)
        counts[record["doc_id"]] += 1
        words[record["doc_id"]] += len(record["text"].split())

    print(f"{'doc_id':13} {'sect':>4} {'words':>7}  title")
    shown = 0
    for doc_id, record in sorted(seen.items()):
        placeholder = words[doc_id] < PLACEHOLDER_WORD_LIMIT
        if only_citable and (not eligible(record) or placeholder):
            continue
        meta = record["metadata"]
        title = (meta.get("title") or meta.get("doc_title") or "")[:60]
        note = flag(record) or ("  [NOT PUBLISHED]" if placeholder else "")
        print(f"{doc_id:13} {counts[doc_id]:4} {words[doc_id]:7}  {title}{note}")
        shown += 1
    print(f"\n{shown} document(s)")


def table_of_contents(records: list[dict], doc_id: str) -> None:
    rows = [r for r in records if r["doc_id"] == doc_id]
    if not rows:
        sys.exit(f"No document {doc_id!r}. Try --docs.")
    meta = rows[0]["metadata"]
    print(f"{doc_id} - {meta.get('title', '')}")
    print(f"  {meta.get('code') or 'no code'} | effective {meta.get('effective_date') or 'not published'}"
          f" | {meta.get('status') or '?'}{flag(rows[0])}")
    print(f"  {meta.get('url', '')}\n")
    for record in rows:
        title = record["metadata"].get("section_title", "")
        words = len(record["text"].split())
        print(f"  {record['section']:<28} {words:>5}w  {title[:52]}")
    print(f"\n{len(rows)} section(s)")


def show(records: list[dict], doc_id: str, section: str) -> None:
    for record in records:
        if record["doc_id"] == doc_id and record["section"].lower() == section.lower():
            meta = record["metadata"]
            print(f"{record['doc_id']}::{record['section']}{flag(record)}")
            print(f"  title : {meta.get('section_title', '')}")
            if meta.get("parent_heading"):
                print(f"  within: {meta['parent_heading']}")
            print(f"  doc   : {meta.get('title', '')}")
            print(f"  url   : {meta.get('url', '')}")
            print("-" * 72)
            print(record["text"])
            return
    sys.exit(f"No section {section!r} in {doc_id}. Try --toc {doc_id}.")


def find(records: list[dict], query: str, limit: int, only_citable: bool) -> None:
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not terms:
        sys.exit("Query needs a word of three characters or more.")

    scored = []
    for record in records:
        if only_citable and not eligible(record):
            continue
        haystack = (
            record["text"] + " " + record["metadata"].get("section_title", "")
        ).lower()
        hits = sum(haystack.count(term) for term in terms)
        distinct = sum(1 for term in terms if term in haystack)
        if distinct == len(terms):
            scored.append((distinct, hits, record))
    scored.sort(key=lambda item: (-item[0], -item[1]))

    print(f"{len(scored)} section(s) contain every term; showing up to {limit}\n")
    for _, hits, record in scored[:limit]:
        meta = record["metadata"]
        print(f"{record['doc_id']}::{record['section']}{flag(record)}")
        print(f"  {meta.get('section_title', '')[:66]}  ({hits} hits)")
        window = re.search(
            r".{0,90}" + re.escape(terms[0]) + r".{0,110}",
            record["text"].lower(),
        )
        if window:
            print(f"  ...{window.group(0).strip()}...")
        print()

    if scored:
        print(
            "Reminder: use this to confirm something exists, not to choose what to\n"
            "ask. Questions found by keyword search produce a keyword-shaped\n"
            "benchmark - see this script's docstring."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--docs", action="store_true", help="list every document")
    group.add_argument("--toc", metavar="DOC_ID", help="list one document's sections")
    group.add_argument("--show", nargs=2, metavar=("DOC_ID", "SECTION"), help="print one section")
    group.add_argument("--find", metavar="QUERY", help="sections containing every term")
    parser.add_argument("-k", type=int, default=10, help="results for --find")
    parser.add_argument(
        "--citable-only",
        action="store_true",
        help="hide instruments that may not appear in required_evidence",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    records = load()
    if args.docs:
        list_documents(records, args.citable_only)
    elif args.toc:
        table_of_contents(records, args.toc)
    elif args.show:
        show(records, args.show[0], args.show[1])
    else:
        find(records, args.find, args.k, args.citable_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
