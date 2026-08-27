"""System 2: dense embedding retrieval.

Runs locally on CPU with no paid API. Defaults to BAAI/bge-small-en-v1.5:
384 dimensions, ~130 MB, and strong on retrieval benchmarks for its size.

## Two decisions that change the numbers

**Embeddings are L2-normalised**, so an inner product is cosine similarity. If
they were not, longer sections would score higher purely for having more
magnitude, and the ranking would partly reflect section length.

**Queries get an instruction prefix, passages do not.** The BGE family is
trained asymmetrically: the query side expects "Represent this sentence for
searching relevant passages:". Omitting it is a silent quality loss rather than
an error, which is exactly the kind of thing that makes a dense baseline look
worse than it is and a comparison misleading.

## Why this pins to CPU

sentence-transformers selects CUDA whenever torch reports a GPU, and on this
machine that fails: torch is a cu121 build against a device with no matching
kernel image, so the first forward pass raises "no kernel image is available for
execution on the device". Pinning the device removes that dependency on what
happens to be installed.

It is also the honest configuration for this project. The claim is that
everything runs locally on a laptop with no paid API, and CPU timings are the
ones that support it - a latency figure measured on a GPU would not describe
what a reader reproducing this would see.

## Why there is no FAISS here

954 chunks by 384 dimensions is a 1.4 MB matrix. A brute-force matrix multiply
searches it in about a millisecond, so an approximate index would add a
dependency, a build step and a recall-versus-speed knob to defend, in exchange
for nothing measurable. FAISS earns its place somewhere above a hundred thousand
vectors; this corpus is two orders of magnitude short of that.
"""

from __future__ import annotations

import numpy as np

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.text import indexable_text

QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class DenseRetriever:
    name = "dense"

    def __init__(
        self,
        chunks: list[Chunk],
        model_name: str = "BAAI/bge-small-en-v1.5",
        batch_size: int = 32,
        device: str = "cpu",
    ) -> None:
        if not chunks:
            raise ValueError("DenseRetriever needs at least one chunk")
        from regulens.retrieval._sentence_transformers import load_sentence_transformer

        SentenceTransformer = load_sentence_transformer()

        self.chunks = chunks
        self.model_name = model_name
        self.device = device
        self.model = SentenceTransformer(model_name, device=device)
        self.embeddings = self.model.encode(
            [indexable_text(c) for c in chunks],
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

    @property
    def dimension(self) -> int:
        return int(self.embeddings.shape[1])

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        vector = self.model.encode(
            QUERY_INSTRUCTION + query,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

        scores = self.embeddings @ vector
        k = min(k, len(self.chunks))
        # argpartition finds the top k without sorting the other 900-odd rows.
        top = np.argpartition(-scores, k - 1)[:k]
        ranked = sorted(top, key=lambda i: (-scores[i], i))
        return [
            RetrievalResult(chunk=self.chunks[i], score=float(scores[i]), rank=rank)
            for rank, i in enumerate(ranked, start=1)
        ]
