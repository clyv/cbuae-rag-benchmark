"""System 3: hybrid lexical + dense, fused by reciprocal rank.

Reciprocal rank fusion is the default here because it needs no score
normalisation and no tuning. BM25 scores are unbounded and corpus-dependent;
cosine similarities sit in [-1, 1]. Combining them by weighted sum means first
inventing a way to make them commensurable, then defending the weights - two
choices to justify in an interview, both fitted to a 50-question benchmark that
cannot support the fitting.

RRF discards the scores entirely and uses only rank:

    score(chunk) = sum over systems of 1 / (rrf_k + rank in that system)

`rrf_k` = 60 is the value from the original paper. It is a smoothing constant:
larger flattens the contribution of top ranks, smaller sharpens it. It is not
tuned here, and that is the point - an untuned constant from the literature is
more defensible than one fitted to this benchmark.

If hybrid does not beat both parents, the README says so. A negative result that
can be explained is worth more than a positive one that cannot.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult, Retriever

DEFAULT_RRF_K = 60

# How deep to look in each parent system before fusing. A chunk ranked 200th by
# BM25 contributes 1/260 - noise - so fusing the whole corpus would cost time
# without changing the order.
DEFAULT_DEPTH = 100


class HybridRetriever:
    name = "hybrid-rrf"

    def __init__(
        self,
        retrievers: list[Retriever],
        rrf_k: int = DEFAULT_RRF_K,
        depth: int = DEFAULT_DEPTH,
    ) -> None:
        if len(retrievers) < 2:
            raise ValueError("hybrid fusion needs at least two retrievers")
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        self.retrievers = retrievers
        self.rrf_k = rrf_k
        self.depth = depth

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        fused: dict[str, float] = {}
        chunks: dict[str, Chunk] = {}
        # Tie-break by best rank achieved in any parent, so the order is
        # deterministic rather than dependent on dict insertion.
        best_rank: dict[str, int] = {}

        for retriever in self.retrievers:
            for result in retriever.retrieve(query, self.depth):
                key = result.chunk.chunk_id
                chunks[key] = result.chunk
                fused[key] = fused.get(key, 0.0) + 1.0 / (self.rrf_k + result.rank)
                best_rank[key] = min(best_rank.get(key, result.rank), result.rank)

        order = sorted(fused, key=lambda key: (-fused[key], best_rank[key], key))
        return [
            RetrievalResult(chunk=chunks[key], score=fused[key], rank=rank)
            for rank, key in enumerate(order[:k], start=1)
        ]
