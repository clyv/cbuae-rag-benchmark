"""System 4: hybrid retrieval followed by a cross-encoder reranker.

Retrieve a wide candidate set, score every candidate against the query with a
cross-encoder, keep the top k.

## Why this can beat the systems it is built on

Bi-encoders embed the query and the passage independently, so the passage vector
is fixed before the query is known. A cross-encoder reads both together, which
lets it judge whether *this* passage answers *this* question rather than whether
they occupy similar regions of a vector space. That extra power is why it is
used as a second stage.

It also caps what it can achieve: the reranker only reorders what hybrid
retrieval already found. If the required section is not in the candidate set, no
amount of reranking recovers it. Recall at the candidate depth is therefore the
ceiling on this system's recall@k, and worth reporting alongside it.

## The cost

Scoring 50 candidates means 50 forward passes per query, against one for a
bi-encoder. On CPU that is the difference between milliseconds and hundreds of
milliseconds, which is why run_eval.py reports median query latency next to the
accuracy figures. A system that is two points better and twenty times slower is
a trade-off, not an improvement, and the table should let a reader see that.

Default model is cross-encoder/ms-marco-MiniLM-L-6-v2 (~90 MB): far smaller than
the bge-reranker family and much faster on CPU, at some cost in quality. The
larger model is the obvious next experiment if the reranker earns its place.
"""

from __future__ import annotations

from regulens.retrieval.base import RetrievalResult, Retriever

DEFAULT_CANDIDATES = 50


def _wrapped_setting(retriever) -> bool:
    """Whether the system underneath indexes the document title."""
    if hasattr(retriever, "include_doc_title"):
        return bool(retriever.include_doc_title)
    for inner in getattr(retriever, "retrievers", []):
        if _wrapped_setting(inner):
            return True
    return False


class RerankedRetriever:
    name = "hybrid+reranker"

    def __init__(
        self,
        base: Retriever,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        candidates: int = DEFAULT_CANDIDATES,
        device: str = "cpu",
    ) -> None:
        from regulens.retrieval._sentence_transformers import load_cross_encoder

        CrossEncoder = load_cross_encoder()

        self.base = base
        self.model_name = model_name
        self.candidates = candidates
        self.device = device
        # CPU for the same reason as DenseRetriever: the installed torch build
        # cannot run kernels on this machine's GPU, and CPU latency is the
        # figure that describes what a reader reproducing this would measure.
        self.model = CrossEncoder(model_name, device=device)
        # Read off the wrapped system rather than set here: showing the reranker
        # more of the document than the stage that fed it would make a
        # difference between them uninterpretable.
        self.include_doc_title = _wrapped_setting(base)

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        pool = self.base.retrieve(query, self.candidates)
        if not pool:
            return []

        # The reranker sees the same text the first-stage systems indexed, so a
        # difference in results comes from the model rather than from one stage
        # being shown more of the document than another.
        from regulens.retrieval.text import indexable_text

        scores = self.model.predict(
            [(query, indexable_text(r.chunk, self.include_doc_title)) for r in pool],
            show_progress_bar=False,
        )

        order = sorted(
            range(len(pool)),
            key=lambda i: (-float(scores[i]), pool[i].rank),
        )
        return [
            RetrievalResult(chunk=pool[i].chunk, score=float(scores[i]), rank=rank)
            for rank, i in enumerate(order[:k], start=1)
        ]
