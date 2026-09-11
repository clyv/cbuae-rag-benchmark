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

## Why the embeddings are cached

Encoding 954 chunks on CPU takes most of a minute, and it produces the same
vectors every time. The cache turns a cold start from about ninety seconds into
a few, which is the difference between a deployable service and one that looks
hung on its first request.

The cache key is a hash of the model name and every text encoded, so changing
the model or rebuilding the corpus with different chunking invalidates it
automatically. Keying on anything less specific would let a stale cache serve
vectors for text that no longer exists - silently, with no error, and with no
way to notice from the results.

## Why there is no FAISS here

954 chunks by 384 dimensions is a 1.4 MB matrix. A brute-force matrix multiply
searches it in about a millisecond, so an approximate index would add a
dependency, a build step and a recall-versus-speed knob to defend, in exchange
for nothing measurable. FAISS earns its place somewhere above a hundred thousand
vectors; this corpus is two orders of magnitude short of that.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.text import indexable_text

QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "corpus" / "processed" / "embeddings.npz"


SEPARATOR = bytes([0])


def _fingerprint(model_name: str, texts: list[str]) -> str:
    """Identity of an embedding set: the model plus exactly what it encoded.

    A cache keyed on anything less specific is a correctness bug waiting to
    happen - rebuild the corpus with different chunking and a stale cache would
    silently serve vectors for text that no longer exists, with no error and no
    way to notice from the results.
    """
    digest = hashlib.sha256(model_name.encode("utf-8"))
    for text in texts:
        digest.update(SEPARATOR)
        digest.update(text.encode("utf-8"))
    return digest.hexdigest()


class DenseRetriever:
    name = "dense"

    def __init__(
        self,
        chunks: list[Chunk],
        model_name: str = "BAAI/bge-small-en-v1.5",
        batch_size: int = 32,
        device: str = "cpu",
        cache: Path | None = DEFAULT_CACHE,
        include_doc_title: bool = False,
    ) -> None:
        if not chunks:
            raise ValueError("DenseRetriever needs at least one chunk")
        from regulens.retrieval._sentence_transformers import load_sentence_transformer

        SentenceTransformer = load_sentence_transformer()

        self.chunks = chunks
        self.model_name = model_name
        self.device = device
        self.model = SentenceTransformer(model_name, device=device)

        self.include_doc_title = include_doc_title
        texts = [indexable_text(c, include_doc_title) for c in chunks]
        key = _fingerprint(model_name, texts)
        self.cached = False

        if cache is not None and cache.exists():
            try:
                stored = np.load(cache, allow_pickle=False)
                if str(stored["key"]) == key:
                    self.embeddings = stored["embeddings"].astype(np.float32)
                    self.cached = True
            except Exception:
                # A corrupt or unreadable cache is not worth failing over; the
                # embeddings can always be recomputed.
                pass

        if not self.cached:
            self.embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).astype(np.float32)
            if cache is not None:
                try:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(cache, key=np.array(key), embeddings=self.embeddings)
                except OSError:
                    pass

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
