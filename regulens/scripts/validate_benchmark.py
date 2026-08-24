#!/usr/bin/env python3
"""Validate benchmark/questions.jsonl against the schema and the registry.

Catches the two errors that quietly corrupt results: a malformed question, and
an evidence label pointing at a doc_id that is not in the corpus.

Usage:
    python scripts/validate_benchmark.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
REGISTRY = REPO_ROOT / "corpus" / "registry.csv"

VALID_CATEGORIES = {
    "single_hop", "cross_section", "cross_document",
    "temporal", "comparative", "adversarial", "unanswerable",
}
VALID_DIFFICULTY = {"easy", "medium", "hard"}
VALID_SOURCES = {"hand_written", "derived_from_document_structure", "llm_drafted_human_verified"}


def known_doc_ids() -> set[str]:
    if not REGISTRY.exists():
        return set()
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        return {row["doc_id"].strip() for row in csv.DictReader(fh) if row.get("doc_id")}


def main() -> int:
    if not BENCHMARK.exists() or not BENCHMARK.read_text(encoding="utf-8").strip():
        print(f"{BENCHMARK.relative_to(REPO_ROOT)} is empty - nothing to validate yet.")
        return 0

    doc_ids = known_doc_ids()
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    categories: Counter[str] = Counter()
    confidences: Counter[str] = Counter()
    label_minutes: list[float] = []

    for lineno, line in enumerate(BENCHMARK.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON - {exc}")
            continue

        qid = item.get("id", f"<line {lineno}>")
        if qid in seen_ids:
            errors.append(f"{qid}: duplicate id")
        seen_ids.add(qid)

        for field in ("id", "question", "category", "difficulty", "required_evidence", "provenance"):
            if field not in item:
                errors.append(f"{qid}: missing required field {field!r}")

        category = item.get("category")
        if category and category not in VALID_CATEGORIES:
            errors.append(f"{qid}: unknown category {category!r}")
        if category:
            categories[category] += 1

        if item.get("difficulty") and item["difficulty"] not in VALID_DIFFICULTY:
            errors.append(f"{qid}: unknown difficulty {item['difficulty']!r}")

        evidence = item.get("required_evidence", [])
        if category == "unanswerable" and evidence:
            errors.append(f"{qid}: unanswerable items must have empty required_evidence")
        if category != "unanswerable" and not evidence:
            errors.append(f"{qid}: no required_evidence - how would this be scored?")
        if category in {"cross_section", "cross_document"} and len(evidence) < 2:
            warnings.append(f"{qid}: category {category} but only {len(evidence)} evidence section(s)")
        if category == "cross_document" and len({e.get("doc_id") for e in evidence}) < 2:
            warnings.append(f"{qid}: category cross_document but evidence spans one document")

        for entry in evidence + item.get("helpful_evidence", []):
            did = entry.get("doc_id", "")
            if doc_ids and did not in doc_ids:
                errors.append(f"{qid}: doc_id {did!r} is not in corpus/registry.csv")
            if not entry.get("section"):
                errors.append(f"{qid}: an evidence entry has no section")

        prov = item.get("provenance", {})
        if prov.get("source") and prov["source"] not in VALID_SOURCES:
            errors.append(f"{qid}: unknown provenance.source {prov['source']!r}")
        confidences[prov.get("confidence", "unset")] += 1
        if isinstance(prov.get("minutes_to_label"), (int, float)):
            label_minutes.append(float(prov["minutes_to_label"]))
            if prov["minutes_to_label"] > 20:
                warnings.append(
                    f"{qid}: took {prov['minutes_to_label']} min to label - "
                    "check the evidence set is genuinely determinate"
                )

    total = len(seen_ids)
    print(f"{total} question(s) checked\n")
    if categories:
        print("By category:")
        for cat, n in sorted(categories.items()):
            print(f"  {cat:<18} {n}")
    if confidences:
        print("\nBy label confidence:")
        for conf, n in sorted(confidences.items()):
            print(f"  {conf:<18} {n}")
    if label_minutes:
        print(f"\nMedian labelling time: {sorted(label_minutes)[len(label_minutes)//2]:.0f} min")
    if not doc_ids:
        print("\nNote: registry is empty, so doc_id references were not checked.")

    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  x {e}")
        return 1

    print("\nNo errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
