#!/usr/bin/env python3
"""Turn results/*.json into the README tables, with intervals. Phase 4.

    python scripts/report_results.py

## Why intervals rather than a ranking

This benchmark is small. A system scoring 0.70 against one scoring 0.66 looks
like an improvement and may sit well inside the range either would produce on a
different draw of the same size. Reporting point estimates alone invites a
ranking narrative the data cannot support, which the README's limitations
section commits to avoiding. The sample size is read from the data rather than
written into the prose, so these tables stay honest as the benchmark grows.

Two things are computed:

**A bootstrap interval per system.** Resample the questions with replacement,
recompute the mean, repeat. The spread of those means is how much the figure
would move on a different sample of questions from the same population.

**A paired bootstrap on the difference between two systems.** This is the one
that answers "is B actually better than A". Pairing matters: both systems answer
the *same* questions, so their scores move together across resamples, and the
difference has a much tighter interval than comparing two independent intervals
would suggest. Two overlapping per-system intervals can still hide a real and
consistent difference - judging by whether the error bars touch is the common
mistake here.

If the interval for a difference includes zero, the honest statement is that
this benchmark cannot separate the two systems.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "results"

# Order systems build on each other, so the table reads as an argument.
SYSTEM_ORDER = ["bm25", "dense", "hybrid-rrf", "hybrid+reranker"]

HEADLINE = ["recall@5", "recall@10", "full_recall@10", "ndcg@10", "mrr"]


def load_reports() -> dict[str, dict]:
    reports = {}
    for path in RESULTS.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Identify a retriever report by its own shape rather than by excluding
        # filenames. results/ also holds answering.json, which has per_question
        # but no retriever, and demo.json, which has neither - a name-based
        # exclusion list silently breaks every time something new is written here.
        if "retriever" in data and "per_question" in data:
            reports[data["retriever"]] = data
    if not reports:
        sys.exit("No result files in results/. Run scripts/run_eval.py first.")
    return reports


def answerable(report: dict) -> list[dict]:
    return [q for q in report["per_question"] if q["category"] != "unanswerable"]


def bootstrap_mean(values: list[float], rounds: int, rng: random.Random) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    n = len(values)
    means = []
    for _ in range(rounds):
        means.append(statistics.fmean(values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def paired_difference(
    a: list[float], b: list[float], rounds: int, rng: random.Random
) -> tuple[float, float, float]:
    """Mean of (b - a) with a 95% interval, resampling question indices jointly."""
    n = len(a)
    diffs = [b[i] - a[i] for i in range(n)]
    point = statistics.fmean(diffs)
    means = []
    for _ in range(rounds):
        means.append(statistics.fmean(diffs[rng.randrange(n)] for _ in range(n)))
    means.sort()
    return point, means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260825)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    reports = load_reports()
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    latency = {s["system"]: s for s in summary}
    order = [n for n in SYSTEM_ORDER if n in reports] + [
        n for n in reports if n not in SYSTEM_ORDER
    ]
    rng = random.Random(args.seed)

    lines: list[str] = []
    add = lines.append

    n_answerable = len(answerable(reports[order[0]]))
    add(f"### Overall, over the {n_answerable} answerable questions\n")
    add("| System | " + " | ".join(HEADLINE) + " | median latency |")
    add("|---|" + "---|" * (len(HEADLINE) + 1))
    for name in order:
        rows = answerable(reports[name])
        cells = [f"{statistics.fmean(q['scores'][m] for q in rows):.3f}" for m in HEADLINE]
        ms = latency.get(name, {}).get("median_query_ms")
        add(f"| {name} | " + " | ".join(cells) + f" | {ms:.0f} ms |")

    add("\n### recall@10 with 95% bootstrap intervals\n")
    add("| System | recall@10 | 95% interval |")
    add("|---|---|---|")
    for name in order:
        values = [q["scores"]["recall@10"] for q in answerable(reports[name])]
        lo, hi = bootstrap_mean(values, args.rounds, random.Random(f"{args.seed}:{name}"))
        add(f"| {name} | {statistics.fmean(values):.3f} | {lo:.3f} – {hi:.3f} |")

    add("\n### Does each step actually help? Paired differences in recall@10\n")
    add("Paired on the same questions, so this is tighter than comparing the")
    add("intervals above. An interval spanning zero means this benchmark cannot")
    add("separate the two systems.\n")
    add("| Comparison | difference | 95% interval | separates? |")
    add("|---|---|---|---|")

    seen: set[tuple[str, str]] = set()

    def compare(a_name: str, b_name: str, metric: str = "recall@10") -> None:
        if a_name not in reports or b_name not in reports:
            return
        if (a_name, b_name) in seen:
            return
        seen.add((a_name, b_name))
        a_rows = {q["id"]: q for q in answerable(reports[a_name])}
        b_rows = {q["id"]: q for q in answerable(reports[b_name])}
        ids = [i for i in a_rows if i in b_rows]
        a = [a_rows[i]["scores"][metric] for i in ids]
        b = [b_rows[i]["scores"][metric] for i in ids]
        # A seed derived from the pair, not the shared generator. Otherwise the
        # interval for one comparison depends on how many comparisons ran before
        # it, and the same pair reported twice would disagree with itself.
        local = random.Random(f"{args.seed}:{a_name}:{b_name}:{metric}")
        point, lo, hi = paired_difference(a, b, args.rounds, local)
        verdict = "no" if lo <= 0 <= hi else "**yes**"
        add(f"| {b_name} vs {a_name} | {point:+.3f} | {lo:+.3f} – {hi:+.3f} | {verdict} |")

    # Each step against the one before it.
    for i in range(len(order) - 1):
        compare(order[i], order[i + 1])

    # And the comparisons the project's question actually asks: hybrid, with and
    # without reranking, against each single-strategy system on its own.
    add("| | | | |")
    for baseline in ("bm25", "dense"):
        for combined in ("hybrid-rrf", "hybrid+reranker"):
            compare(baseline, combined)

    add("\n### recall@10 by category\n")
    categories = [
        c for c in sorted({q["category"] for q in reports[order[0]]["per_question"]})
        if c != "unanswerable"
    ]
    add("| System | " + " | ".join(categories) + " |")
    add("|---|" + "---|" * len(categories))
    for name in order:
        cells = []
        for category in categories:
            rows = [q for q in reports[name]["per_question"] if q["category"] == category]
            cells.append(f"{statistics.fmean(q['scores']['recall@10'] for q in rows):.3f}")
        add(f"| {name} | " + " | ".join(cells) + " |")
    add("")
    add("`n` per category: " + ", ".join(
        f"{c} {sum(1 for q in reports[order[0]]['per_question'] if q['category'] == c)}"
        for c in categories
    ))

    add("")
    add("### The 6 unanswerable questions are not scored here")
    add("")
    add("Retrieval always returns its top k, so a retriever has no abstention")
    add("decision to make. Every figure on an item with no required evidence is")
    add("then fixed by construction: recall is 1.0 because nothing can be missed,")
    add("precision is 0.0 because nothing retrieved can be required. Neither")
    add("varies between systems and neither measures anything.")
    add("")
    add("Abstention is a property of the answering stage, which is Phase 5. These")
    add("six questions exist to test whether it declines to answer rather than")
    add("confabulating from whatever retrieval handed it. A number for them now")
    add("would be an artefact of the metric definition, not a result.")

    out = "\n".join(lines)
    (RESULTS / "tables.md").write_text(out + "\n", encoding="utf-8")
    print(out)
    print(f"\nWrote {(RESULTS / 'tables.md').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
