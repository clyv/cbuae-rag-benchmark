"""Tests for the retrieval metrics.

If you claim a number in the README, the code producing it should be tested.
Run with: pytest
"""

import math

from regulens.evaluation.metrics import (
    abstention_correct,
    evidence_id,
    full_recall_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

A = evidence_id("DOC-1", "Article 4")
B = evidence_id("DOC-1", "Article 7")
C = evidence_id("DOC-2", "Article 5")
NOISE = [evidence_id("DOC-9", f"Article {i}") for i in range(1, 10)]


def test_evidence_id_strips_whitespace():
    assert evidence_id(" DOC-1 ", " Article 4 ") == "DOC-1::Article 4"


def test_recall_partial_and_full():
    retrieved = [A, NOISE[0], NOISE[1]]
    assert recall_at_k(retrieved, [A, B], k=5) == 0.5
    assert recall_at_k([A, B], [A, B], k=5) == 1.0
    assert recall_at_k(NOISE, [A, B], k=5) == 0.0


def test_recall_respects_cutoff():
    retrieved = NOISE[:4] + [A]
    assert recall_at_k(retrieved, [A], k=3) == 0.0
    assert recall_at_k(retrieved, [A], k=5) == 1.0


def test_duplicate_chunks_consume_retrieval_budget():
    # A chunker may emit the same section three times. Those repeats occupy
    # slots the user actually paid for, so they must not be free.
    retrieved = [A, A, A, B]
    assert recall_at_k(retrieved, [A, B], k=3) == 0.5
    assert recall_at_k(retrieved, [A, B], k=4) == 1.0
    # Section-level dedupe still applies within the window.
    assert precision_at_k(retrieved, [A, B], k=3) == 1.0


def test_full_recall_is_all_or_nothing():
    assert full_recall_at_k([A, NOISE[0]], [A, B], k=5) == 0.0
    assert full_recall_at_k([A, NOISE[0], B], [A, B], k=5) == 1.0


def test_precision():
    assert precision_at_k([A, B, NOISE[0], NOISE[1]], [A, B], k=4) == 0.5
    assert precision_at_k([], [A], k=5) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank([A], [A]) == 1.0
    assert reciprocal_rank([NOISE[0], NOISE[1], A], [A, B]) == 1 / 3
    assert reciprocal_rank(NOISE, [A]) == 0.0


def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k([A, B], [A, B], k=5) == 1.0


def test_ndcg_penalises_burying_evidence():
    good = ndcg_at_k([A, NOISE[0], NOISE[1]], [A], k=5)
    bad = ndcg_at_k([NOISE[0], NOISE[1], A], [A], k=5)
    assert good > bad


def test_ndcg_grades_required_above_helpful():
    required_first = ndcg_at_k([A, C], [A], k=5, helpful=[C])
    helpful_first = ndcg_at_k([C, A], [A], k=5, helpful=[C])
    assert required_first > helpful_first


def test_ndcg_known_value():
    # Single required item at rank 2: DCG = 2/log2(3), IDCG = 2/log2(2).
    expected = (2 / math.log2(3)) / (2 / math.log2(2))
    assert ndcg_at_k([NOISE[0], A], [A], k=5) == expected


def test_unanswerable_items_do_not_fail_recall():
    assert recall_at_k(NOISE, [], k=5) == 1.0
    assert full_recall_at_k(NOISE, [], k=5) == 1.0


def test_abstention_scoring():
    # Unanswerable question: declining is right, answering is wrong.
    assert abstention_correct(NOISE, [], answered=False) is True
    assert abstention_correct(NOISE, [], answered=True) is False
    # Answerable question: answering is right, declining is wrong.
    assert abstention_correct([A], [A], answered=True) is True
    assert abstention_correct([A], [A], answered=False) is False
