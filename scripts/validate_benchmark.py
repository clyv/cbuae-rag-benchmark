#!/usr/bin/env python3
"""Validate benchmark/questions.jsonl against the schema and the registry.

Catches the two errors that quietly corrupt results: a malformed question, and
an evidence label pointing at a doc_id that is not in the corpus.

Usage:
    python scripts/validate_benchmark.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
REGISTRY = REPO_ROOT / "corpus" / "registry.csv"
SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"

VALID_CATEGORIES = {
    "single_hop", "cross_section", "cross_document",
    "temporal", "comparative", "adversarial", "unanswerable",
}
VALID_DIFFICULTY = {"easy", "medium", "hard"}
VALID_SOURCES = {"hand_written", "derived_from_document_structure", "llm_drafted_human_verified"}

# The mix decided in benchmark/PLAN.md. Kept here so drift is caught while the
# set is being built rather than discovered when the results tables are drawn:
# the by-category recall table is the one the project's question turns on, and a
# category that quietly ends up with two items cannot support a column in it.
TARGET_MIX = {
    "single_hop": 18,
    "cross_section": 27,
    "cross_document": 17,
    "comparative": 13,
    "adversarial": 11,
    "unanswerable": 14,
    "temporal": 0,
}

# Confidence levels excluded from headline metrics, per PLAN.md.
EXCLUDED_CONFIDENCE = {"low"}


def known_doc_ids() -> set[str]:
    if not REGISTRY.exists():
        return set()
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        return {row["doc_id"].strip() for row in csv.DictReader(fh) if row.get("doc_id")}


def labelling_eligibility() -> dict[str, str]:
    """doc_id -> reason it may not appear in an answer key, for ineligible rows.

    Some instruments are in the retrieval index but must not be cited as
    required evidence - see the registry's labelling_eligible column and
    SOURCES.md for why. Absent column means everything is eligible, so an older
    registry still validates.
    """
    if not REGISTRY.exists():
        return {}
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        return {
            row["doc_id"].strip(): (row.get("labelling_note") or "").strip()
            for row in csv.DictReader(fh)
            if row.get("doc_id") and (row.get("labelling_eligible") or "").strip() == "false"
        }


def corpus_evidence_ids() -> set[str]:
    """Every doc_id::section that actually exists after parsing.

    Without this, a mistyped or misremembered section label is indistinguishable
    from a retrieval failure: the question simply scores zero for ever, and the
    system gets blamed for it.
    """
    if not SECTIONS.exists():
        return set()
    ids: set[str] = set()
    for line in SECTIONS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            ids.add(f"{record['doc_id']}::{record['section']}")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=BENCHMARK,
        help=(
            "questions file to validate (default: benchmark/questions.jsonl). "
            "Point it at benchmark/drafts.jsonl to check drafts before promoting."
        ),
    )
    args = parser.parse_args()
    globals()["BENCHMARK"] = args.file

    if not BENCHMARK.exists() or not BENCHMARK.read_text(encoding="utf-8").strip():
        print(f"{BENCHMARK.relative_to(REPO_ROOT)} is empty - nothing to validate yet.")
        return 0

    doc_ids = known_doc_ids()
    ineligible = labelling_eligibility()
    corpus_ids = corpus_evidence_ids()
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

        for entry, scored in [(e, True) for e in evidence] + [
            (e, False) for e in item.get("helpful_evidence", [])
        ]:
            did = entry.get("doc_id", "")
            section = entry.get("section", "")
            if doc_ids and did not in doc_ids:
                errors.append(f"{qid}: doc_id {did!r} is not in corpus/registry.csv")
            if not section:
                errors.append(f"{qid}: an evidence entry has no section")
                continue

            # An ineligible instrument still belongs in the index - it is a
            # useful near-miss distractor - but naming it as required evidence
            # would make the answer key assert which instrument governs an
            # obligation today, which is a legal judgement this project does not
            # make. helpful_evidence is not scored, so it may reference them.
            if scored and did in ineligible:
                errors.append(
                    f"{qid}: doc_id {did!r} is not labelling-eligible "
                    f"({ineligible[did] or 'see registry'}) - it belongs in the "
                    "index, not the ground truth"
                )

            if corpus_ids:
                key = f"{did}::{section}"
                if key not in corpus_ids:
                    errors.append(
                        f"{qid}: evidence {key!r} does not exist in the parsed "
                        "corpus - check corpus/processed/sections.jsonl for the "
                        "exact label"
                    )

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

    total = sum(categories.values())
    print("\nAgainst the target mix in benchmark/PLAN.md:")
    print(f"  {'category':<16}{'have':>6}{'target':>8}{'gap':>7}")
    for name, target in TARGET_MIX.items():
        have = categories.get(name, 0)
        print(f"  {name:<16}{have:>6}{target:>8}{have - target:>+7}")
    print(f"  {'TOTAL':<16}{total:>6}{sum(TARGET_MIX.values()):>8}")

    scored = total - sum(confidences.get(c, 0) for c in EXCLUDED_CONFIDENCE)
    print(
        f"\nHeadline metrics would score {scored} of {total} item(s); "
        f"{total - scored} excluded as low confidence."
    )
    if total and total < sum(TARGET_MIX.values()):
        print(
            f"Benchmark is incomplete ({total}/{sum(TARGET_MIX.values())}). "
            "Results computed now would not reflect the planned mix."
        )

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
