"""Tests for the retrieval systems that need no model weights.

Dense and reranker behaviour is not tested here: both are thin wrappers whose
substance is a downloaded model, and asserting on their output would be testing
the model rather than this code. What is tested is everything that decides
whether the comparison between systems is fair - shared tokenisation, shared
indexed text, and the fusion arithmetic.
"""

from __future__ import annotations

import pytest

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.bm25 import BM25Retriever
from regulens.retrieval.hybrid import HybridRetriever
from regulens.retrieval.text import indexable_text, tokenize


def chunk(chunk_id: str, text: str, title: str = "", section: str = "Article 1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="DOC-A",
        section=section,
        text=text,
        metadata={"section_title": title},
    )


# --- shared text handling ---------------------------------------------------


def test_subclause_references_match_the_article():
    """'Article 5(2)' must be findable by a query for Article 5.

    Questions cite articles loosely; the corpus cites them precisely. Keeping
    '5(2)' as one token would make the two unmatchable.
    """
    assert tokenize("Article 5(2)") == ["article", "5", "2"]
    assert "5" in tokenize("Article 5(2)")


def test_tokenizer_keeps_numbers_and_drops_punctuation():
    assert tokenize("AED 250,000,000") == ["aed", "250", "000", "000"]
    assert tokenize("C 25/2022") == ["c", "25", "2022"]


def test_indexed_text_includes_the_heading():
    """Several sections are titled by a heading absent from their own body."""
    c = chunk("c1", "The body says nothing topical.", title="Grievance")
    assert "Grievance" in indexable_text(c)
    assert "body says nothing" in indexable_text(c)


def test_indexed_text_survives_missing_metadata():
    bare = Chunk(chunk_id="c1", doc_id="D", section="Article 1", text="text only")
    assert indexable_text(bare) == "text only"


# --- the document title, which separates matched instruments ----------------


def titled(doc_id: str, doc_title: str) -> Chunk:
    """Two instruments whose articles are identical apart from their title -
    the shape that produces 15% of this corpus's missed evidence."""
    return Chunk(
        chunk_id=f"{doc_id}::Section 2, Article 1",
        doc_id=doc_id,
        section="Section 2, Article 1",
        text="The Minimum Subscribed and Paid Up Capital of each Company shall be:",
        metadata={
            "section_title": "Article (1) - Minimum Capital Requirement",
            "section_heading": "Article (1) - Minimum Capital Requirement",
            "doc_title": doc_title,
        },
    )


def test_the_document_title_is_left_out_by_default():
    """Off by default so the switch is a measured change, not a silent one."""
    c = titled("INS-FIN-002", "Financial Regulations for Takaful Insurance Companies")
    assert "Takaful" not in indexable_text(c)


def test_the_document_title_is_indexed_when_asked_for():
    c = titled("INS-FIN-002", "Financial Regulations for Takaful Insurance Companies")
    assert "Takaful" in indexable_text(c, include_doc_title=True)


def test_the_title_is_what_separates_two_otherwise_identical_articles():
    conventional = titled("INS-FIN-001", "Financial Regulations for Insurance Companies")
    takaful = titled("INS-FIN-002", "Financial Regulations for Takaful Insurance Companies")
    assert indexable_text(conventional) == indexable_text(takaful)
    assert indexable_text(conventional, True) != indexable_text(takaful, True)


def test_a_title_already_used_as_the_heading_adds_nothing():
    """A document's opening section is titled by the document itself. Adding the
    title there would weight one section's heading against every other section's
    body, so for those 44 sections the switch is a no-op."""
    c = Chunk(
        chunk_id="D::Introduction", doc_id="D", section="Introduction", text="body",
        metadata={"section_title": "Licensing Regulation", "section_heading": "Licensing Regulation",
                  "doc_title": "Licensing Regulation"},
    )
    assert indexable_text(c, include_doc_title=True) == indexable_text(c)


# --- BM25 -------------------------------------------------------------------


def corpus() -> list[Chunk]:
    return [
        chunk("c1", "The Board must approve any deviation from the risk appetite.", "Risk"),
        chunk("c2", "Minimum paid up capital for a reinsurance company.", "Capital", "Article 2"),
        chunk("c3", "The actuarial function reports to the chief executive.", "Actuarial", "Article 3"),
    ]


def test_bm25_finds_the_obvious_match():
    hits = BM25Retriever(corpus()).retrieve("risk appetite deviation", k=3)
    assert hits[0].chunk.chunk_id == "c1"


def test_bm25_matches_on_heading_alone():
    """A query using only the section title must still reach the section."""
    hits = BM25Retriever(corpus()).retrieve("actuarial", k=3)
    assert hits[0].chunk.chunk_id == "c3"


def test_bm25_returns_at_most_k_ranked_from_one():
    hits = BM25Retriever(corpus()).retrieve("capital", k=2)
    assert len(hits) == 2
    assert [h.rank for h in hits] == [1, 2]


def test_bm25_is_deterministic_when_scores_tie():
    """Ties break on corpus order, so the results table cannot drift per run."""
    retriever = BM25Retriever(corpus())
    first = [h.chunk.chunk_id for h in retriever.retrieve("the", k=3)]
    for _ in range(5):
        assert [h.chunk.chunk_id for h in retriever.retrieve("the", k=3)] == first


def test_bm25_handles_a_query_with_no_usable_terms():
    assert BM25Retriever(corpus()).retrieve("!!!", k=5) == []


def test_bm25_rejects_an_empty_corpus():
    with pytest.raises(ValueError):
        BM25Retriever([])


# --- hybrid fusion ----------------------------------------------------------


class Fake:
    def __init__(self, name: str, chunks: list[Chunk]) -> None:
        self.name = name
        self._chunks = chunks

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        return [
            RetrievalResult(chunk=c, score=1.0 / rank, rank=rank)
            for rank, c in enumerate(self._chunks[:k], start=1)
        ]


def test_rrf_promotes_what_both_systems_rank_highly():
    a, b, c = chunk("a", "a"), chunk("b", "b"), chunk("c", "c")
    # 'b' is second in both; 'a' and 'c' are first in one and absent from the other.
    left = Fake("left", [a, b])
    right = Fake("right", [c, b])
    hits = HybridRetriever([left, right]).retrieve("q", k=3)
    assert hits[0].chunk.chunk_id == "b"


def test_rrf_score_matches_the_formula():
    a = chunk("a", "a")
    hits = HybridRetriever([Fake("l", [a]), Fake("r", [a])], rrf_k=60).retrieve("q", k=1)
    assert hits[0].score == pytest.approx(2 * (1 / 61))


def test_rrf_uses_rank_not_score():
    """A system with huge scores must not outvote one with small scores."""
    a, b = chunk("a", "a"), chunk("b", "b")

    class Loud(Fake):
        def retrieve(self, query, k):
            return [RetrievalResult(chunk=b, score=10_000.0, rank=1)]

    hits = HybridRetriever([Fake("quiet", [a]), Loud("loud", [])]).retrieve("q", k=2)
    assert {h.chunk.chunk_id for h in hits} == {"a", "b"}
    assert hits[0].score == pytest.approx(hits[1].score)


def test_hybrid_output_is_ranked_from_one_and_capped_at_k():
    chunks = [chunk(str(i), str(i)) for i in range(10)]
    hits = HybridRetriever([Fake("l", chunks), Fake("r", list(reversed(chunks)))]).retrieve("q", k=4)
    assert [h.rank for h in hits] == [1, 2, 3, 4]


def test_hybrid_needs_two_retrievers():
    with pytest.raises(ValueError):
        HybridRetriever([Fake("only", corpus())])


def test_hybrid_rejects_a_nonpositive_rrf_constant():
    with pytest.raises(ValueError):
        HybridRetriever([Fake("a", corpus()), Fake("b", corpus())], rrf_k=0)
