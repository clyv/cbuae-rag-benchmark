"""System 2: dense embedding retrieval.

STUB - Phase 4.

Runs locally with no paid API. sentence-transformers with a BGE or E5 family
model on CPU is the usual starting point; a small model is fine and keeps
indexing time sane on a laptop.

Record in the README: which model, which dimension, how long indexing took,
and whether you normalised embeddings. Those are the questions you will be
asked.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult


class DenseRetriever:
    name = "dense"

    def __init__(self, chunks: list[Chunk], model_name: str) -> None:
        raise NotImplementedError("Phase 4")

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        raise NotImplementedError("Phase 4")
