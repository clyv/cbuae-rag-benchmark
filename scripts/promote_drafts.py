#!/usr/bin/env python3
"""Move verified drafts into the benchmark. Phase 3.

    python scripts/promote_drafts.py --list      # what is ready, what is not
    python scripts/promote_drafts.py --dry-run
    python scripts/promote_drafts.py

benchmark/drafts.jsonl holds candidate questions. benchmark/questions.jsonl is
the benchmark. This script is the only thing that moves an item between them,
and it refuses to move anything a human has not actually checked.

## Why the gate exists

The evidence sets in drafts.jsonl were written by reading the corpus, and every
one of them resolves to a real section. That is not the same as being correct.
Whether a section is genuinely *required* to answer a question - and whether the
set is complete - is a judgement about the regulation, and this project's single
substantive claim is that a human made it. A benchmark whose ground truth was
both drafted and approved by a model measures the model's reading, not the
regulation, and every number downstream inherits that.

So promotion requires two fields that only a person can honestly supply:

    provenance.minutes_to_label   how long verification actually took; drafts
                                  carry 0, meaning not yet verified
    provenance.confidence         how sure the verifier is that
                                  required_evidence is complete and correct

## Verifying a draft

For each item, open the sections it cites and check three things:

1. **Does each cited section actually support the question?** If a section is
   merely on-topic, it is helpful_evidence, not required_evidence.
2. **Is anything missing?** A question that cannot be answered from the cited
   set alone has an incomplete label, which reads as a retrieval failure later.
3. **Is the set minimal?** Extra sections make recall easier to score highly and
   the benchmark less discriminating.

Then set minutes_to_label to the real figure and confidence to high, medium or
low. Set it low without embarrassment - low-confidence items are excluded from
headline metrics and counted in the README, which is the honest outcome.

Ids are reassigned on promotion: drafts use D001..., the benchmark uses Q001...
and never reuses a retired id.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DRAFTS = REPO_ROOT / "benchmark" / "drafts.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"

VALID_CONFIDENCE = {"high", "medium", "low"}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def blocking_reasons(item: dict) -> list[str]:
    """Why this draft may not be promoted yet. Empty means ready."""
    reasons: list[str] = []
    prov = item.get("provenance", {})

    minutes = prov.get("minutes_to_label")
    if not isinstance(minutes, (int, float)) or minutes <= 0:
        reasons.append("minutes_to_label is 0 - not yet verified by a human")

    confidence = prov.get("confidence")
    if confidence not in VALID_CONFIDENCE:
        reasons.append("provenance.confidence is unset")

    if item.get("category") == "unanswerable" and item.get("required_evidence"):
        reasons.append("unanswerable items must have empty required_evidence")
    if item.get("category") != "unanswerable" and not item.get("required_evidence"):
        reasons.append("no required_evidence")

    return reasons


def next_question_number(existing: list[dict]) -> int:
    highest = 0
    for item in existing:
        match = re.fullmatch(r"Q(\d{3})", item.get("id", ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="report readiness, change nothing")
    parser.add_argument("--dry-run", action="store_true", help="show what would be promoted")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    drafts = read_jsonl(DRAFTS)
    if not drafts:
        sys.exit(f"{DRAFTS.relative_to(REPO_ROOT)} is empty - nothing to promote.")

    ready = [d for d in drafts if not blocking_reasons(d)]
    blocked = [(d, blocking_reasons(d)) for d in drafts if blocking_reasons(d)]

    if args.list or not ready:
        print(f"{len(ready)} of {len(drafts)} draft(s) ready to promote\n")
        for item, reasons in blocked:
            print(f"  {item.get('id', '?')}  {item.get('category', '?')}")
            for reason in reasons:
                print(f"      - {reason}")
        if not ready:
            print(
                "\nNothing is ready. Verify a draft by opening the sections it "
                "cites,\nthen set provenance.minutes_to_label and "
                "provenance.confidence.\nSee this script's docstring for what "
                "verification means."
            )
        if args.list:
            return 0

    if not ready:
        return 1

    existing = read_jsonl(BENCHMARK)
    number = next_question_number(existing)

    promoted = []
    for item in ready:
        item = dict(item)
        item["id"] = f"Q{number:03d}"
        number += 1
        promoted.append(item)

    print(f"\nPromoting {len(promoted)}:")
    for original, item in zip(ready, promoted):
        print(f"  {original['id']} -> {item['id']}  {item['category']:<15} {item['question'][:52]}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    with BENCHMARK.open("a", encoding="utf-8") as fh:
        for item in promoted:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    remaining = [d for d in drafts if blocking_reasons(d)]
    DRAFTS.write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in remaining),
        encoding="utf-8",
    )

    print(f"\nAppended to {BENCHMARK.relative_to(REPO_ROOT)}; {len(remaining)} draft(s) remain.")
    print("Now run: python scripts/validate_benchmark.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
