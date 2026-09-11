#!/usr/bin/env python3
"""How often does the system cite a provision that is not law yet?

    python scripts/analyse_temporal.py
    python scripts/analyse_temporal.py --as-of 2027-08-01

Writes results/temporal.json.

Every other metric in this project is timeless. Recall asks whether the right
section was found; citation validity asks whether the words are there. Neither
asks what a compliance officer asks first - is this the law today?

Four instruments are listed In-Force while commencing later: INS-TAK-001 on
2026-09-14, and INS-TAK-006/007/008 on 2027-07-15. They are indexed on purpose
as near-miss distractors and barred from the answer key. Nothing stops a
retriever returning them.

Runs on recorded output, so it needs no models and no re-run.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from regulens.evaluation.temporal import exposure, load_commencements  # noqa: E402

REGISTRY = REPO_ROOT / "corpus" / "registry.csv"
RESULTS = REPO_ROOT / "results"
OUT = RESULTS / "temporal.json"
SYSTEMS = ["bm25", "dense", "hybrid-rrf", "hybrid+reranker"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    commencements = load_commencements(REGISTRY)
    premature_docs = sorted(
        d for d, c in commencements.items() if c is not None and c > as_of
    )

    print(f"as of {as_of.isoformat()}, not yet commenced:")
    for doc in premature_docs:
        print(f"  {doc}  commences {commencements[doc]}")
    unknown_docs = sorted(d for d, c in commencements.items() if c is None)
    print(f"\npublish no date at all ({len(unknown_docs)}): {', '.join(unknown_docs)}")

    report: dict = {"as_of": as_of.isoformat(), "not_yet_commenced": premature_docs,
                    "unknown_date": unknown_docs, "systems": {}}

    print(f"\n{'system':18s} {'questions':>10s} {'sections':>9s} {'at rank 1':>10s}")
    for name in SYSTEMS:
        path = RESULTS / f"{name}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))["per_question"]
        affected, sections, at_top = [], 0, 0
        by_category: collections.Counter[str] = collections.Counter()
        for row in rows:
            result = exposure(row["retrieved"], as_of, commencements)
            if result["clean"]:
                continue
            affected.append({"id": row["id"], "category": row["category"],
                             "premature": result["premature"],
                             "rank": result["first_premature_rank"]})
            sections += int(result["premature_count"])
            at_top += result["first_premature_rank"] == 1
            by_category[row["category"]] += 1

        report["systems"][name] = {
            "questions_affected": len(affected),
            "questions": len(rows),
            "premature_sections": sections,
            "at_rank_1": at_top,
            "by_category": dict(by_category),
            "affected": affected,
        }
        print(f"{name:18s} {len(affected):7d}/{len(rows):<3d} {sections:9d} {at_top:10d}")

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    shipped = report["systems"].get("hybrid+reranker")
    if shipped and shipped["affected"]:
        print("\nshipped system, questions citing something not yet law:")
        for row in shipped["affected"]:
            mark = "  <- at rank 1" if row["rank"] == 1 else ""
            print(f"  {row['id']}  {row['category']:15s} rank {row['rank']}  "
                  f"{', '.join(row['premature'])[:60]}{mark}")

    print(f"\nWrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
