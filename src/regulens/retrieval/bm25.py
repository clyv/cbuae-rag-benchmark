"""System 1: lexical baseline (BM25).

Built first, on purpose. It is the cheapest system to stand up and it sets the
bar every later system must beat. If BM25 already scores well here, the
questions are too easy and the benchmark is what needs fixing.

Tokenisation and the indexed field are shared with every other system - see
regulens.retrieval.text - so that differences in the results table come from
retrieval strategy rather than from what each system was allowed to see.
"""

from __future__ import annotations

from rank_bm25 import BM25Okapi

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.text import indexable_text, tokenize


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[Chunk], include_doc_title: bool = False) -> None:
        if not chunks:
            raise ValueError("BM25Retriever needs at least one chunk")
        self.chunks = chunks
        self.include_doc_title = include_doc_title
        self._index = BM25Okapi(
            [tokenize(indexable_text(c, include_doc_title)) for c in chunks]
        )

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        terms = tokenize(query)
        if not terms:
            return []
        scores = self._index.get_scores(terms)

        # argsort descending, then take k. Ties are broken by corpus order,
        # which is document order - stable, and not a source of run-to-run
        # variation in the results table.
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
        return [
            RetrievalResult(chunk=self.chunks[i], score=float(scores[i]), rank=rank)
            for rank, i in enumerate(ranked, start=1)
        ]
