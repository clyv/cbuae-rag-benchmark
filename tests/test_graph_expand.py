"""Tests for retrieval widened along cross-references.

The measurement in `results/graph.md` is a null result, and a null result is only
worth anything if the thing being measured actually ran. These check that
expansion puts sections in front of the ranker rather than quietly doing nothing.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.graph_expand import GraphExpandedRetriever

CHUNKS = [
    Chunk("D::Article 1", "D", "Article 1", "definitions", {}),
    Chunk("D::Article 2", "D", "Article 2", "the limits in Article 3 apply", {}),
    Chunk("D::Article 3", "D", "Article 3", "counterparty limits", {}),
    Chunk("D::Article 4#1", "D", "Article 4", "first half", {}),
    Chunk("D::Article 4#2", "D", "Article 4", "second half", {}),
]
ADJACENCY = {
    "D::Article 2": ["D::Article 3", "D::Article 4"],
    "D::Article 3": ["D::Article 2"],
    "D::Article 4": ["D::Article 2"],
}


class Fixed:
    """A retriever that always returns the same thing, so what changes in a test
    is the expansion and nothing else."""

    name = "fixed"

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        return [
            RetrievalResult(chunk=c, score=10.0 - i, rank=i + 1)
            for i, c in enumerate(self.chunks[:k])
        ]


def expander(base_chunks: list[Chunk], **kwargs) -> GraphExpandedRetriever:
    return GraphExpandedRetriever(Fixed(base_chunks), ADJACENCY, CHUNKS, **kwargs)


def sections(results: list[RetrievalResult]) -> list[str]:
    return [r.chunk.evidence_id for r in results]


def test_a_referenced_section_is_added():
    results = expander([CHUNKS[1]]).retrieve("limits", k=5)
    assert "D::Article 3" in sections(results)


def test_the_results_that_were_found_are_kept():
    results = expander([CHUNKS[1]]).retrieve("limits", k=5)
    assert sections(results)[0] == "D::Article 2"


def test_expansion_survives_a_k_smaller_than_the_result_set():
    """The reranker asks for a wide candidate pool, and truncating to k drops the
    added sections first - they sort below the results that named them. That
    would make expansion a no-op that still looked like it ran."""
    results = expander([CHUNKS[1]]).retrieve("limits", k=1)
    assert "D::Article 3" in sections(results)


def test_every_chunk_of_a_referenced_section_is_added():
    """A reference points at a provision, not at whichever piece of it the
    splitter happened to produce."""
    results = expander([CHUNKS[1]]).retrieve("limits", k=5)
    ids = [r.chunk.chunk_id for r in results]
    assert "D::Article 4#1" in ids and "D::Article 4#2" in ids


def test_a_section_already_retrieved_is_not_added_twice():
    results = expander([CHUNKS[1], CHUNKS[2]]).retrieve("limits", k=5)
    found = sections(results)
    assert found.count("D::Article 3") == 1


def test_added_sections_rank_below_the_result_that_named_them():
    results = expander([CHUNKS[1]]).retrieve("limits", k=5)
    scores = {r.chunk.evidence_id: r.score for r in results}
    assert scores["D::Article 3"] < scores["D::Article 2"]


def test_nothing_is_added_when_no_result_has_a_reference():
    results = expander([CHUNKS[0]]).retrieve("definitions", k=5)
    assert sections(results) == ["D::Article 1"]


def test_the_added_count_is_capped():
    results = expander([CHUNKS[1]], max_added=1).retrieve("limits", k=5)
    assert len(sections(results)) == 2


def test_ranks_are_renumbered_contiguously():
    results = expander([CHUNKS[1]]).retrieve("limits", k=5)
    assert [r.rank for r in results] == list(range(1, len(results) + 1))


def test_expansion_size_counts_sections_not_chunks():
    """Article 4 is two chunks and one provision. Counting chunks would overstate
    how much the graph contributes."""
    assert expander([CHUNKS[1]]).expansion_size("limits") == 2
