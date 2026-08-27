#!/usr/bin/env python3
"""Measure whether label verification actually catches errors.

    python scripts/negative_control.py --plant
    python scripts/negative_control.py --review          # one item at a time
    python scripts/negative_control.py --score

## Why this exists

All 50 benchmark labels were LLM-drafted and human-verified, and verification
changed none of them. Two readings fit that record: the drafts were sound, or
the check was confirmatory rather than adversarial. Nothing else in this
repository distinguishes them, and the difference matters - the project's one
substantive claim is that a person established the ground truth.

This measures it. A sample of questions is taken, half are corrupted, all are
presented in random order with no indication of which is which, and the reviewer
marks each one sound or broken. The detection rate is then a number that can be
reported instead of an assurance.

## Why half the sample is untouched

If every item were corrupted, a reviewer who assumed so would score 100% without
reading anything. The untouched items measure the opposite error: calling a
correct label broken. A process that flags everything is as useless as one that
flags nothing, and only the false-positive rate exposes it.

## The corruptions are the mistakes a drafter would really make

Not random noise. A section is dropped, or a neighbouring article from the same
document is added or substituted - the plausible near-miss, which is what an LLM
drafting from a document it has read tends to get wrong. Corrupting with an
unrelated section from another instrument would be trivially detectable and
would measure nothing.

## Reading the result

With eight corrupted items the error bars are wide: catching seven of eight is
not meaningfully different from catching six. Report the count, not a percentage
carrying three significant figures, and say the sample was small.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
CONTROL_DIR = REPO_ROOT / "benchmark" / "control"
PLANTED = CONTROL_DIR / "planted.jsonl"
KEY = CONTROL_DIR / "key.json"
VERDICTS = CONTROL_DIR / "verdicts.csv"

DEFAULT_SAMPLE = 16


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sections_by_doc() -> dict[str, list[str]]:
    """doc_id -> section labels in document order, for picking neighbours."""
    order: dict[str, list[str]] = {}
    for record in read_jsonl(SECTIONS):
        order.setdefault(record["doc_id"], []).append(record["section"])
    return order


def corrupt(item: dict, order: dict[str, list[str]], rng: random.Random) -> tuple[dict, str] | None:
    """Return a broken copy of item and a description, or None if it cannot be broken."""
    item = json.loads(json.dumps(item))
    evidence = item["required_evidence"]

    def neighbour(doc_id: str, section: str) -> str | None:
        labels = order.get(doc_id, [])
        if section not in labels:
            return None
        index = labels.index(section)
        options = [labels[i] for i in (index - 1, index + 1) if 0 <= i < len(labels)]
        used = {e["section"] for e in evidence if e["doc_id"] == doc_id}
        options = [o for o in options if o not in used]
        return rng.choice(options) if options else None

    choices = []
    if len(evidence) >= 2:
        choices.append("drop")
    if evidence:
        choices += ["add", "swap"]
    else:
        choices.append("spurious")
    if not choices:
        return None

    how = rng.choice(choices)

    if how == "drop":
        removed = evidence.pop(rng.randrange(len(evidence)))
        return item, f"dropped a required section: {removed['doc_id']}::{removed['section']}"

    if how == "spurious":
        # An unanswerable item given evidence it should not have.
        doc_id = rng.choice(sorted(order))
        section = rng.choice(order[doc_id])
        item["required_evidence"] = [
            {"doc_id": doc_id, "section": section, "why": "supports the question"}
        ]
        return item, f"gave an unanswerable item evidence: {doc_id}::{section}"

    target = rng.choice(evidence)
    replacement = neighbour(target["doc_id"], target["section"])
    if replacement is None:
        return None

    if how == "add":
        evidence.append(
            {
                "doc_id": target["doc_id"],
                "section": replacement,
                "why": "also required to answer the question",
            }
        )
        return item, f"added a superfluous neighbour: {target['doc_id']}::{replacement}"

    original = target["section"]
    target["section"] = replacement
    target["why"] = "required to answer the question"
    return item, (
        f"swapped {target['doc_id']}::{original} for its neighbour "
        f"{target['doc_id']}::{replacement}"
    )


def plant(sample_size: int, seed: int) -> int:
    questions = read_jsonl(BENCHMARK)
    if len(questions) < sample_size:
        sys.exit(f"Only {len(questions)} question(s); need at least {sample_size}.")

    rng = random.Random(seed)
    order = sections_by_doc()
    if not order:
        sys.exit("No parsed corpus. Run scripts/build_corpus.py first.")

    sample = rng.sample(questions, sample_size)
    half = sample_size // 2

    planted: list[dict] = []
    key: dict[str, dict] = {}
    broken = 0

    for item in sample:
        want_broken = broken < half
        result = corrupt(item, order, rng) if want_broken else None
        if result is not None:
            item, description = result
            broken += 1
            key[item["id"]] = {"corrupted": True, "how": description}
        else:
            key[item["id"]] = {"corrupted": False, "how": ""}
        planted.append(item)

    rng.shuffle(planted)

    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    PLANTED.write_text(
        "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in planted), encoding="utf-8"
    )
    KEY.write_text(
        json.dumps({"seed": seed, "sample": sample_size, "items": key}, indent=2),
        encoding="utf-8",
    )
    VERDICTS.write_text(
        "question_id,verdict,note\n"
        + "".join(f"{i['id']},,\n" for i in planted),
        encoding="utf-8",
    )

    print(f"Planted {broken} corrupted item(s) among {sample_size}.")
    print(f"  {PLANTED.relative_to(REPO_ROOT)}   the items to review")
    print(f"  {VERDICTS.relative_to(REPO_ROOT)}  fill in the verdict column")
    print(f"  {KEY.relative_to(REPO_ROOT)}       DO NOT OPEN until you have scored")
    print()
    print("Review each item with:")
    print("  python scripts/negative_control.py --review")
    print()
    print("For each, write sound or broken in the verdict column. Judge only the")
    print("required_evidence: is every section genuinely needed, and is anything")
    print("missing? Then run --score.")
    return 0


def review() -> int:
    items = read_jsonl(PLANTED)
    if not items:
        sys.exit("Nothing planted. Run --plant first.")
    corpus = {(r["doc_id"], r["section"]): r for r in read_jsonl(SECTIONS)}

    for number, item in enumerate(items, start=1):
        print("=" * 74)
        print(f"[{number} of {len(items)}]  {item['id']}   {item['category']}")
        print("=" * 74)
        print(f"\nQUESTION\n  {item['question']}\n")
        evidence = item["required_evidence"]
        if not evidence:
            print("REQUIRED EVIDENCE\n  (none - claims the corpus does not cover this)\n")
        for entry in evidence:
            record = corpus.get((entry["doc_id"], entry["section"]))
            print("-" * 74)
            print(f"{entry['doc_id']}::{entry['section']}")
            print(f"  claimed role: {entry.get('why', '')}")
            if record is None:
                print("  !! not in the parsed corpus")
                continue
            print(f"  heading     : {record['metadata'].get('section_title', '')}")
            print("-" * 74)
            print(record["text"])
            print()
        print(f">> Record 'sound' or 'broken' for {item['id']} in "
              f"{VERDICTS.relative_to(REPO_ROOT)}\n")
    return 0


def score() -> int:
    if not KEY.exists():
        sys.exit("Nothing planted. Run --plant first.")
    key = json.loads(KEY.read_text(encoding="utf-8"))["items"]

    rows = [
        line.split(",", 2)
        for line in VERDICTS.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    ]
    verdicts = {r[0].strip(): r[1].strip().lower() for r in rows if len(r) >= 2}

    missing = [q for q, v in verdicts.items() if v not in {"sound", "broken"}]
    if missing:
        sys.exit(
            f"{len(missing)} item(s) have no verdict yet: {', '.join(missing[:8])}"
            + ("..." if len(missing) > 8 else "")
        )

    caught = missed = false_alarm = correct_pass = 0
    detail = []
    for qid, info in key.items():
        verdict = verdicts.get(qid)
        if info["corrupted"]:
            if verdict == "broken":
                caught += 1
                detail.append((qid, "caught", info["how"]))
            else:
                missed += 1
                detail.append((qid, "MISSED", info["how"]))
        else:
            if verdict == "sound":
                correct_pass += 1
            else:
                false_alarm += 1
                detail.append((qid, "false alarm", "label was untouched"))

    corrupted = caught + missed
    clean = correct_pass + false_alarm

    print(f"Corrupted items caught : {caught} of {corrupted}")
    print(f"Untouched items passed : {correct_pass} of {clean}")
    print(f"False alarms           : {false_alarm}")
    print()
    for qid, outcome, how in sorted(detail, key=lambda d: d[1]):
        print(f"  {qid}  {outcome:<12} {how}")
    print()
    if missed:
        print("Every missed item is a label that could be wrong in the benchmark")
        print("itself. Re-check the ones of the same shape before publishing results.")
    print("Sample is small; report the counts, not a percentage to three figures.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plant", action="store_true", help="build a blind sample")
    group.add_argument("--review", action="store_true", help="print the sample for review")
    group.add_argument("--score", action="store_true", help="compare verdicts with the key")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=20260825)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.plant:
        return plant(args.sample, args.seed)
    if args.review:
        return review()
    return score()


if __name__ == "__main__":
    raise SystemExit(main())
