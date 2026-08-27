"""The retrieval stack the API serves.

Kept apart from app.py so the wiring can be built and tested without starting a
web server, and so the API layer holds only HTTP concerns.

Both configurations are built once and share their components: the reranked
system wraps the same hybrid retriever the fast path uses, so choosing `rerank`
per request costs a cross-encoder pass and nothing else.
"""

from __future__ import annotations

import json
from pathlib import Path

from regulens.generation.answer import ExtractiveGenerator, GroundedAnswer, answer_question
from regulens.retrieval.base import Chunk, RetrievalResult

REPO_ROOT = Path(__file__).resolve().parents[3]
CHUNKS = REPO_ROOT / "corpus" / "processed" / "chunks.jsonl"

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def load_chunks(path: Path | None = None) -> list[Chunk]:
    path = path or CHUNKS
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/download_corpus.py then scripts/build_corpus.py."
        )
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            chunks.append(
                Chunk(
                    chunk_id=raw["chunk_id"],
                    doc_id=raw["doc_id"],
                    section=raw["section"],
                    text=raw["text"],
                    metadata=raw.get("metadata", {}),
                )
            )
    if not chunks:
        raise ValueError(f"{path} is empty")
    return chunks


class Index:
    """Hybrid retrieval, optionally reranked, plus the extractive answerer."""

    def __init__(self, chunks: list[Chunk]) -> None:
        from regulens.retrieval.bm25 import BM25Retriever
        from regulens.retrieval.dense import DenseRetriever
        from regulens.retrieval.hybrid import HybridRetriever
        from regulens.retrieval.rerank import RerankedRetriever

        self.chunks = chunks
        self.hybrid = HybridRetriever(
            [BM25Retriever(chunks), DenseRetriever(chunks, DENSE_MODEL)]
        )
        self.reranked = RerankedRetriever(self.hybrid, RERANK_MODEL)
        self.generator = ExtractiveGenerator()

    @property
    def size(self) -> int:
        return len(self.chunks)

    def answer(
        self,
        question: str,
        k: int = 5,
        rerank: bool = True,
        threshold: float | None = None,
    ) -> tuple[GroundedAnswer, list[RetrievalResult]]:
        system = self.reranked if rerank else self.hybrid
        results = system.retrieve(question, k)

        # Abstention needs a score comparable across questions, which only the
        # cross-encoder gives. RRF scores encode rank position, so a threshold
        # on them would decline based on how many systems agreed rather than on
        # whether the top passage is any good. Ignore it rather than mislead.
        effective = threshold if rerank else None
        answer = answer_question(
            question, results, generator=self.generator, threshold=effective
        )
        if threshold is not None and not rerank:
            answer = GroundedAnswer(
                text=answer.text,
                citations=answer.citations,
                abstained=answer.abstained,
                context_used=answer.context_used,
                reason="threshold ignored: fusion scores are not comparable across questions",
                top_score=answer.top_score,
            )
        return answer, results
