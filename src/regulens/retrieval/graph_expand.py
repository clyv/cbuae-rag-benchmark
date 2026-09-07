"""Retrieval widened along the corpus's own cross-references.

Phase 6. The idea is the one every graph-RAG write-up starts from: regulation
names the provisions it depends on, so after retrieving a section you can follow
its references and pick up the provisions it points at, even when those score
badly on their own words.

It sits *between* retrieval and reranking, not after it. Expansion adds
candidates; the cross-encoder then decides whether any of them deserve a place
in the top k. Adding sections after reranking would push scored results out of
the way with unscored ones, which measures the ordering of the wrapper rather
than the value of the graph.

The measured answer for this corpus is in `results/graph.md`, and it is that the
graph cannot help: only 2 of 59 co-required section pairs in the benchmark are
joined by an explicit reference, so the structure this class follows is mostly
not the structure the questions need. The class is kept because that conclusion
is worth being able to re-run, and because the ceiling it fails to reach is a
property of this corpus rather than of the idea.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult, Retriever

DEFAULT_POOL = 20
DEFAULT_MAX_ADDED = 15


class GraphExpandedRetriever:
    """Wraps a retriever, adding the sections its results point at."""

    name = "graph-expanded"

    def __init__(
        self,
        base: Retriever,
        adjacency: dict[str, list[str]],
        chunks: list[Chunk],
        pool: int = DEFAULT_POOL,
        max_added: int = DEFAULT_MAX_ADDED,
    ) -> None:
        self.base = base
        self.adjacency = adjacency
        self.pool = pool
        self.max_added = max_added
        # A section can be several chunks, and a reference points at the whole
        # provision, so every chunk of a referenced section is a candidate.
        self.by_section: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            self.by_section.setdefault(chunk.evidence_id, []).append(chunk)

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        found = self.base.retrieve(query, max(self.pool, k))
        present = {result.chunk.evidence_id for result in found}

        added: list[RetrievalResult] = []
        for result in found:
            if len(added) >= self.max_added:
                break
            for neighbour in self.adjacency.get(result.chunk.evidence_id, []):
                if neighbour in present or len(added) >= self.max_added:
                    continue
                present.add(neighbour)
                for chunk in self.by_section.get(neighbour, []):
                    # Inherit the referring result's score, decayed, so a
                    # neighbour ranks just below the passage that named it. Only
                    # the ordering matters: a reranker rescores everything, and
                    # without one this at least keeps added sections from
                    # displacing the results that found them.
                    added.append(
                        RetrievalResult(
                            chunk=chunk,
                            score=result.score - 1e-3 * (len(added) + 1),
                            rank=0,
                        )
                    )

        # Everything found plus everything added, and deliberately *not* capped
        # at k. Truncating here would drop the added sections first - they sort
        # below the results that named them - so expansion would silently do
        # nothing while appearing to run. Handing the caller a wider pool than it
        # asked for gives the graph a candidate budget the baseline does not
        # have, which biases in the graph's favour: a null result under those
        # conditions cannot be blamed on crowding it out.
        merged = found + added
        return [
            RetrievalResult(chunk=result.chunk, score=result.score, rank=rank)
            for rank, result in enumerate(merged, start=1)
        ]

    def expansion_size(self, query: str) -> int:
        """How many sections expansion adds for one query - reported rather than
        assumed, because a graph that adds nothing and one that adds noise fail
        in different ways."""
        found = self.base.retrieve(query, self.pool)
        present = {result.chunk.evidence_id for result in found}
        return len({
            neighbour
            for result in found
            for neighbour in self.adjacency.get(result.chunk.evidence_id, [])
            if neighbour not in present
        })
