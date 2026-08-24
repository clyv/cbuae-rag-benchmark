"""Run a retriever against the benchmark and write scored results.

Usage from a script or notebook:

    from regulens.evaluation.runner import load_benchmark, evaluate
    items = load_benchmark("benchmark/questions.jsonl")
    report = evaluate(my_retriever, items, k_values=(1, 3, 5, 10))
    print(report.to_markdown())

The report deliberately breaks results out by category. A single averaged
number hides the finding that matters - typically that every system does fine
on single-hop questions and they only separate on cross-document ones.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from regulens.evaluation.metrics import (
    evidence_id,
    full_recall_at_k,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from regulens.retrieval.base import Retriever


@dataclass(frozen=True)
class BenchmarkItem:
    id: str
    question: str
    category: str
    difficulty: str
    required: tuple[str, ...]
    helpful: tuple[str, ...] = ()
    confidence: str = "high"


@dataclass
class QuestionScore:
    item_id: str
    category: str
    difficulty: str
    scores: dict[str, float]
    retrieved: list[str]


@dataclass
class Report:
    retriever_name: str
    k_values: tuple[int, ...]
    per_question: list[QuestionScore] = field(default_factory=list)

    def overall(self) -> dict[str, float]:
        keys = self.per_question[0].scores.keys() if self.per_question else []
        return {key: mean(q.scores[key] for q in self.per_question) for key in keys}

    def by_category(self) -> dict[str, dict[str, float]]:
        buckets: dict[str, list[QuestionScore]] = defaultdict(list)
        for q in self.per_question:
            buckets[q.category].append(q)
        out = {}
        for category, items in sorted(buckets.items()):
            keys = items[0].scores.keys()
            out[category] = {key: mean(i.scores[key] for i in items) for key in keys}
            out[category]["n"] = len(items)
        return out

    def to_markdown(self) -> str:
        overall = self.overall()
        cols = list(overall.keys())
        lines = [
            f"### {self.retriever_name}",
            "",
            f"Questions scored: {len(self.per_question)}",
            "",
            "| category | n | " + " | ".join(cols) + " |",
            "|---|---|" + "---|" * len(cols),
        ]
        for category, values in self.by_category().items():
            row = [category, str(int(values["n"]))]
            row += [f"{values[c]:.3f}" for c in cols]
            lines.append("| " + " | ".join(row) + " |")
        overall_row = ["**overall**", f"**{len(self.per_question)}**"]
        overall_row += [f"**{overall[c]:.3f}**" for c in cols]
        lines.append("| " + " | ".join(overall_row) + " |")
        return "\n".join(lines)

    def to_json(self, path: str | Path) -> None:
        payload = {
            "retriever": self.retriever_name,
            "k_values": list(self.k_values),
            "overall": self.overall(),
            "by_category": self.by_category(),
            "per_question": [
                {
                    "id": q.item_id,
                    "category": q.category,
                    "difficulty": q.difficulty,
                    "scores": q.scores,
                    "retrieved": q.retrieved,
                }
                for q in self.per_question
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_benchmark(path: str | Path, include_low_confidence: bool = False) -> list[BenchmarkItem]:
    """Read questions.jsonl, skipping retired items.

    Low-confidence items are excluded by default: if you were not sure the
    evidence labels were right, they should not drive a headline number.
    Pass include_low_confidence=True to report the sensitivity separately.
    """
    items: list[BenchmarkItem] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} is not valid JSON: {exc}") from exc

        if raw.get("retired"):
            continue
        confidence = raw.get("provenance", {}).get("confidence", "high")
        if confidence == "low" and not include_low_confidence:
            continue

        items.append(
            BenchmarkItem(
                id=raw["id"],
                question=raw["question"],
                category=raw["category"],
                difficulty=raw["difficulty"],
                required=tuple(
                    evidence_id(e["doc_id"], e["section"]) for e in raw.get("required_evidence", [])
                ),
                helpful=tuple(
                    evidence_id(e["doc_id"], e["section"]) for e in raw.get("helpful_evidence", [])
                ),
                confidence=confidence,
            )
        )
    if not items:
        raise ValueError(f"No usable questions found in {path}.")
    return items


def evaluate(
    retriever: Retriever,
    items: list[BenchmarkItem],
    k_values: tuple[int, ...] = (1, 3, 5, 10),
) -> Report:
    """Score one retriever across the benchmark."""
    max_k = max(k_values)
    report = Report(retriever_name=retriever.name, k_values=k_values)

    for item in items:
        results = retriever.retrieve(item.question, k=max_k)
        retrieved = [r.chunk.evidence_id for r in results]

        scores: dict[str, float] = {}
        for k in k_values:
            scores[f"recall@{k}"] = recall_at_k(retrieved, item.required, k)
            scores[f"full_recall@{k}"] = full_recall_at_k(retrieved, item.required, k)
            scores[f"precision@{k}"] = precision_at_k(retrieved, item.required, k)
            scores[f"ndcg@{k}"] = ndcg_at_k(retrieved, item.required, k, helpful=item.helpful)
        scores["mrr"] = reciprocal_rank(retrieved, item.required)

        report.per_question.append(
            QuestionScore(
                item_id=item.id,
                category=item.category,
                difficulty=item.difficulty,
                scores=scores,
                retrieved=retrieved[:max_k],
            )
        )
    return report
