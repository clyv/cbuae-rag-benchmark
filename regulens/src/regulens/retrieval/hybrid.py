"""System 3: hybrid lexical + dense.

STUB - Phase 4.

Reciprocal rank fusion is the sane default: it needs no score normalisation
and no tuning, which means one less thing to justify. Weighted score fusion is
the alternative but requires you to defend the weights.

If hybrid does NOT beat both parents, say so in the README. A negative result
you can explain is a stronger signal than a positive one you cannot.
"""

from __future__ import annotations

from regulens.retrieval.base import RetrievalResult, Retriever


class HybridRetriever:
    name = "hybrid-rrf"

    def __init__(self, retrievers: list[Retriever], rrf_k: int = 60) -> None:
        raise NotImplementedError("Phase 4")

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        raise NotImplementedError("Phase 4")
