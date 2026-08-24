"""Retrieval metrics.

These are the project's headline numbers, so they are dependency-free and
unit-tested. Everything here scores *retrieval* - whether the system surfaced
the sections a human labelled as required. Nothing here scores legal accuracy.

Vocabulary used throughout:
    evidence id  a "DOC_ID::SECTION" string identifying one labelled section
    retrieved    the ranked list of evidence ids the system returned, best first
    required     the unordered set of evidence ids a human labelled as necessary
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def evidence_id(doc_id: str, section: str) -> str:
    """Canonical key for one piece of evidence."""
    return f"{doc_id.strip()}::{section.strip()}"


def _top_k(items: Sequence[str], k: int) -> list[str]:
    """Take the top k retrieved chunks, THEN collapse repeated sections.

    Design decision worth defending in a write-up: a chunker often emits the
    same section several times, so the top 5 chunks may cover only 2 distinct
    sections. Truncating before deduplicating means those repeats consume
    retrieval budget, which is what actually happens to a user. Deduplicating
    first would flatter the system by pretending a redundant result was free.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in items[:k]:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_all(items: Iterable[str]) -> list[str]:
    """Rank-preserving dedupe over the whole list (used by reciprocal rank)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def recall_at_k(retrieved: Sequence[str], required: Iterable[str], k: int) -> float:
    """Fraction of required evidence appearing in the top k.

    Returns 1.0 when nothing is required (an unanswerable item cannot fail
    recall); score abstention separately with `abstention_correct`.
    """
    required_set = set(required)
    if not required_set:
        return 1.0
    top_k = set(_top_k(retrieved, k))
    return len(required_set & top_k) / len(required_set)


def precision_at_k(retrieved: Sequence[str], required: Iterable[str], k: int) -> float:
    """Fraction of the top k that is required evidence."""
    required_set = set(required)
    top_k = _top_k(retrieved, k)
    if not top_k:
        return 0.0
    return sum(1 for item in top_k if item in required_set) / len(top_k)


def full_recall_at_k(retrieved: Sequence[str], required: Iterable[str], k: int) -> float:
    """1.0 only if EVERY required section is in the top k, else 0.0.

    Stricter than recall@k and arguably the honest metric for multi-hop
    questions: partial evidence means the question cannot actually be answered.
    Worth reporting alongside recall@k.
    """
    required_set = set(required)
    if not required_set:
        return 1.0
    return float(required_set <= set(_top_k(retrieved, k)))


def reciprocal_rank(retrieved: Sequence[str], required: Iterable[str]) -> float:
    """1/rank of the first required item (rank is 1-based). 0.0 if none found."""
    required_set = set(required)
    if not required_set:
        return 0.0
    for rank, item in enumerate(_dedupe_all(retrieved), start=1):
        if item in required_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved: Sequence[str],
    required: Iterable[str],
    k: int,
    helpful: Iterable[str] = (),
) -> float:
    """Normalised discounted cumulative gain with binary or graded relevance.

    Gain is 2 for required evidence and 1 for helpful evidence, so a system that
    surfaces required sections above merely-related ones scores higher. Uses the
    standard log2(rank + 1) discount.
    """
    required_set = set(required)
    helpful_set = set(helpful) - required_set

    def gain(item: str) -> int:
        if item in required_set:
            return 2
        if item in helpful_set:
            return 1
        return 0

    ranked = _top_k(retrieved, k)
    dcg = sum(gain(item) / math.log2(rank + 1) for rank, item in enumerate(ranked, start=1))

    ideal_gains = [2] * len(required_set) + [1] * len(helpful_set)
    ideal_gains = sorted(ideal_gains, reverse=True)[:k]
    idcg = sum(g / math.log2(rank + 1) for rank, g in enumerate(ideal_gains, start=1))

    return dcg / idcg if idcg > 0 else 0.0


def abstention_correct(retrieved: Sequence[str], required: Iterable[str], answered: bool) -> bool:
    """Did the system correctly answer vs. correctly decline?

    For an unanswerable item (empty required set) the right behaviour is to
    decline. For every other item, declining is a failure. Report this as its
    own column - averaging it into recall hides the behaviour you care about.
    """
    del retrieved  # kept in the signature so all scorers share one shape
    return (not set(required)) != answered


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
