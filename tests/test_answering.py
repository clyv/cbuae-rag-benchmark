"""Tests for grounded answering.

The two properties that matter are the two the project claims: the system
declines when the evidence does not support an answer, and a citation that does
not hold up is detected rather than trusted.
"""

from __future__ import annotations

import pytest

from regulens.generation.answer import (
    Citation,
    ExtractiveGenerator,
    GroundedAnswer,
    answer_question,
    validate_citations,
)
from regulens.retrieval.base import Chunk, RetrievalResult

ARTICLE_3 = (
    "A documented Risk Management strategy, including a clearly defined Risk "
    "Appetite statement that is Board-approved. A documented process for the "
    "Board's approval for any deviation from the Risk Appetite."
)
ARTICLE_5 = (
    "The head of the control function must not participate in operational "
    "business responsibilities, such as underwriting, investment or accounting."
)


def result(doc_id: str, section: str, text: str, score: float, rank: int) -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(
            chunk_id=f"{doc_id}::{section}",
            doc_id=doc_id,
            section=section,
            text=text,
            metadata={"url": "https://example.invalid/doc"},
        ),
        score=score,
        rank=rank,
    )


def context() -> list[RetrievalResult]:
    return [
        result("INS-GOV-003", "Article 3", ARTICLE_3, 8.0, 1),
        result("INS-GOV-003", "Article 5", ARTICLE_5, 2.0, 2),
    ]


# --- abstention -------------------------------------------------------------


def test_declines_when_nothing_was_retrieved():
    answer = answer_question("anything", [], threshold=0.0)
    assert answer.abstained
    assert not answer.citations


def test_declines_when_the_best_passage_is_below_threshold():
    answer = answer_question("q", context(), threshold=9.0)
    assert answer.abstained
    assert "9.000" in answer.reason
    assert answer.top_score == 8.0


def test_answers_when_the_best_passage_clears_the_threshold():
    answer = answer_question("q", context(), threshold=1.0)
    assert not answer.abstained
    assert answer.citations


def test_threshold_is_inclusive_so_an_exact_tie_declines():
    """A score exactly at the threshold is not evidence of relevance."""
    assert answer_question("q", context(), threshold=8.0).abstained


def test_no_threshold_means_never_decline():
    answer = answer_question("q", context(), threshold=None)
    assert not answer.abstained


def test_an_abstention_carries_no_citations_to_check():
    scores = validate_citations(answer_question("q", context(), threshold=9.0))
    assert scores["abstained"] == 1.0
    assert scores["citations"] == 0


# --- extractive answering ---------------------------------------------------


def test_every_citation_names_a_retrieved_section():
    answer = answer_question("risk appetite deviation", context(), threshold=None)
    available = {f"{r.chunk.doc_id}::{r.chunk.section}" for r in context()}
    assert {c.evidence_id for c in answer.citations} <= available


def test_extractive_answers_are_grounded_and_supported_by_construction():
    answer = answer_question("risk appetite deviation", context(), threshold=None)
    scores = validate_citations(answer)
    assert scores["grounded"] == 1.0
    assert scores["supported"] == 1.0


def test_the_quote_comes_from_the_section_it_cites():
    answer = answer_question("who approves a deviation", context(), threshold=None)
    sources = {f"{r.chunk.doc_id}::{r.chunk.section}": r.chunk.text for r in context()}
    for citation in answer.citations:
        for word in citation.quote.split()[:5]:
            assert word in sources[citation.evidence_id]


def test_one_citation_per_section_even_when_chunks_repeat():
    """Several chunks of one article are one source, not three."""
    repeated = [
        result("INS-GOV-003", "Article 3", ARTICLE_3, 8.0, 1),
        result("INS-GOV-003", "Article 3", ARTICLE_3, 7.0, 2),
        result("INS-GOV-003", "Article 5", ARTICLE_5, 2.0, 3),
    ]
    answer = answer_question("q", repeated, threshold=None)
    ids = [c.evidence_id for c in answer.citations]
    assert len(ids) == len(set(ids))


def test_citation_count_is_capped():
    many = [result("D", f"Article {i}", ARTICLE_3, 5.0, i) for i in range(1, 9)]
    answer = answer_question("q", many, generator=ExtractiveGenerator(max_citations=2))
    assert len(answer.citations) == 2


# --- the failures validate_citations exists to catch ------------------------


def test_a_citation_to_a_section_that_was_never_retrieved_is_ungrounded():
    """The failure mode of a generator inventing a plausible-looking reference."""
    answer = GroundedAnswer(
        text="...",
        citations=[Citation("INS-FIN-001", "Section 2, Article 4", "invented text")],
        context_used=context(),
    )
    assert validate_citations(answer)["grounded"] == 0.0


def test_a_quote_absent_from_a_real_section_is_unsupported():
    """The reference is real; the words attributed to it are not there."""
    answer = GroundedAnswer(
        text="...",
        citations=[
            Citation("INS-GOV-003", "Article 3", "Companies must maintain a fidelity bond")
        ],
        context_used=context(),
    )
    scores = validate_citations(answer)
    assert scores["grounded"] == 1.0
    assert scores["supported"] == 0.0


def test_partly_invented_citations_score_between():
    answer = GroundedAnswer(
        text="...",
        citations=[
            Citation("INS-GOV-003", "Article 3", "Board-approved Risk Appetite statement"),
            Citation("INS-XXX-999", "Article 1", "does not exist"),
        ],
        context_used=context(),
    )
    assert validate_citations(answer)["grounded"] == pytest.approx(0.5)


def test_an_answer_with_no_citations_scores_zero():
    answer = GroundedAnswer(text="Trust me.", citations=[], context_used=context())
    scores = validate_citations(answer)
    assert scores["grounded"] == 0.0
    assert scores["supported"] == 0.0
