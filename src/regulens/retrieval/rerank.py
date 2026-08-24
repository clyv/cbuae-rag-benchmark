"""System 4: hybrid + cross-encoder reranker.

STUB - Phase 4.

Retrieve a wide candidate set (say 50), rerank, keep the top k. A local
cross-encoder such as the bge-reranker family runs on CPU, slowly. Measure and
report the latency cost - the trade-off between accuracy and speed is exactly
what an interviewer will probe.
"""

from __future__ import annotations

from regulens.retrieval.base import RetrievalResult, Retriever


class RerankedRetriever:
    name = "hybrid+reranker"

    def __init__(self, base: Retriever, model_name: str, candidates: int = 50) -> None:
        raise NotImplementedError("Phase 4")

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        raise NotImplementedError("Phase 4")
