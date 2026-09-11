#!/usr/bin/env python3
"""Why does retrieval miss what it misses?

    python scripts/analyse_failures.py
    python scripts/analyse_failures.py --system bm25

Writes results/failures.json.

The results table says hybrid+reranker reaches 0.750 recall@10 and leaves 35 of
86 answerable questions short of their full evidence. "0.750" is a number you
can put in a README; it is not a reason, and it does not tell you what to build
next. Legal-RAG benchmarks published through 2026 increasingly report a failure
*taxonomy* alongside the score for exactly this reason - an aggregate hides
whether a system is failing for one reason or five.

This classifies every miss from output already recorded, so it needs no models
and no re-run.

## The categories, and why these

**matched instrument outranked** - this corpus contains matched instruments: a
conventional regulation and its Takaful counterpart, a Regulation and its
Standards, two motor policies. They share section labels and much of their
wording. When the required section is `INS-FIN-001::Section 2, Article 1` and the
system returned `INS-FIN-002::Section 2, Article 1`, it found the right provision
in the wrong instrument. That is a scope failure, not a topical one, and it is
the same finding `results/scope_check.md` reached from the other direction.

**same label, unrelated instrument** - kept apart from the above on purpose.
"Article 4" exists in a sanctions resolution and in a motor decision, and a
retriever returning one when the other was wanted has not confused a matched
pair, it has just missed. Folding the two together would inflate the headline
category with coincidence.

**same document, wrong article** - the system found the right instrument and the
wrong provision inside it. A ranking problem rather than a retrieval one.

**lexical gap** - the question shares almost no content vocabulary with the
section that answers it. This is the paraphrase case the README already reports
six of; measuring it across every miss says whether those six were the whole
story.

**no signal** - nothing retrieved came from the right document or shared
vocabulary with the right section. The honest bucket: these are the ones with no
cheap explanation.

A question missing two required sections can appear in two categories. Counts
are therefore over *missed sections*, with question counts reported separately.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

SECTIONS = REPO_ROOT / "corpus" / "processed" / "sections.jsonl"
BENCHMARK = REPO_ROOT / "benchmark" / "questions.jsonl"
RESULTS = REPO_ROOT / "results"
OUT = RESULTS / "failures.json"

STOPWORDS = frozenset(
    """a an and are as at be been but by for from had has have if in into is it its
    must no not of on or shall should such that the their there these this to was
    were which who will with within would what when how does do can may any""".split()
)
LEXICAL_GAP = 0.10


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system", default="hybrid+reranker")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    path = RESULTS / f"{args.system}.json"
    if not path.exists():
        sys.exit(f"{path} not found. Run scripts/run_eval.py first.")

    rows = json.loads(path.read_text(encoding="utf-8"))["per_question"]
    benchmark = {r["id"]: r for r in load_jsonl(BENCHMARK)}
    text_of = {f"{s['doc_id']}::{s['section']}": s["text"] for s in load_jsonl(SECTIONS)}
    # A section label that appears in more than one document is a twin: matched
    # instruments reuse the drafter's own numbering.
    label_twins: dict[str, set[str]] = collections.defaultdict(set)
    for key in text_of:
        doc, _, label = key.partition("::")
        label_twins[label].add(doc)

    missed_rows = []
    by_category: collections.Counter[str] = collections.Counter()
    question_kinds: collections.Counter[str] = collections.Counter()

    for row in rows:
        required = {f"{e['doc_id']}::{e['section']}" for e in benchmark[row["id"]]["required_evidence"]}
        if not required:
            continue
        retrieved = list(dict.fromkeys(row["retrieved"]))
        missed = required - set(retrieved)
        if not missed:
            question_kinds["complete"] += 1
            continue
        question_kinds["partial" if len(missed) < len(required) else "total"] += 1

        question = benchmark[row["id"]]["question"]
        for target in sorted(missed):
            doc, _, label = target.partition("::")
            got_docs = {r.partition("::")[0] for r in retrieved}

            twin = next(
                (r for r in retrieved
                 if r.partition("::")[2] == label and r.partition("::")[0] != doc
                 and len(label_twins[label]) > 1),
                None,
            )
            # Sharing a section label is not the same as being a matched
            # instrument. "Article 4" exists in a sanctions resolution and in a
            # motor decision, and those two have nothing to do with each other.
            # A real pair sits in the same registry category - INS-FIN-001 and
            # INS-FIN-002, INS-MOT-002 and INS-MOT-003 - so the two are counted
            # separately rather than letting coincidence inflate the finding.
            matched = bool(twin) and twin.partition("::")[0][:7] == doc[:7]
            overlap = 0.0
            if target in text_of:
                q, s = tokens(question), tokens(text_of[target])
                overlap = len(q & s) / len(q) if q else 0.0

            if matched:
                kind = "matched instrument outranked"
            elif twin:
                kind = "same label, unrelated instrument"
            elif doc in got_docs:
                kind = "same document, wrong article"
            elif overlap < LEXICAL_GAP:
                kind = "lexical gap"
            else:
                kind = "no signal"

            by_category[kind] += 1
            missed_rows.append({
                "id": row["id"],
                "category": row["category"],
                "missed": target,
                "kind": kind,
                "question_overlap_with_target": round(overlap, 3),
                "twin_retrieved": twin,
            })

    report = {
        "system": args.system,
        "questions_with_required_evidence": sum(question_kinds.values()),
        "questions": dict(question_kinds),
        "missed_sections": len(missed_rows),
        "by_kind": dict(by_category),
        "by_kind_and_category": {
            kind: dict(collections.Counter(r["category"] for r in missed_rows if r["kind"] == kind))
            for kind in by_category
        },
        "missed": missed_rows,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(question_kinds.values())
    print(f"{args.system}, over {total} answerable questions\n")
    print(f"  {question_kinds['complete']:3d}  found every required section")
    print(f"  {question_kinds['partial']:3d}  found some but not all")
    print(f"  {question_kinds['total']:3d}  found none\n")
    print(f"{len(missed_rows)} missed sections, by why:\n")
    for kind, n in by_category.most_common():
        share = n / len(missed_rows)
        print(f"  {n:3d}  ({share:4.0%})  {kind}")
        cats = report["by_kind_and_category"][kind]
        print(f"        {', '.join(f'{c} {v}' for c, v in sorted(cats.items(), key=lambda kv: -kv[1]))}")

    twins = [r for r in missed_rows if r["kind"] == "matched instrument outranked"]
    if twins:
        print("\nthe right provision in the wrong instrument:")
        for r in twins[:6]:
            print(f"  {r['id']}  wanted {r['missed']}")
            print(f"         got    {r['twin_retrieved']}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
