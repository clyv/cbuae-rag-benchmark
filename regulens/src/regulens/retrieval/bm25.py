"""System 1: lexical baseline (BM25).

STUB - Phase 4, but build this FIRST. It is the cheapest system to stand up
and it sets the bar every later system must beat. If BM25 already scores well
on your benchmark, your questions are too easy - fix the benchmark before
building anything more sophisticated.

Implementation note: rank_bm25 is the path of least resistance. Tokenisation
matters more than you expect on regulatory text - decide how to handle
"Article 5" vs "Article 5(2)" and write the decision down.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[Chunk]) -> None:
        raise NotImplementedError("Phase 4")

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        raise NotImplementedError("Phase 4")
