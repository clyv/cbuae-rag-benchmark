"""System 5: learned sparse retrieval (SPLADE).

BM25 matches the words that are there. Dense retrieval matches meaning and
forgets the words. SPLADE is the third option: it produces a *sparse* vector over
the vocabulary, like BM25, but the weights are learned and the model may put
weight on terms that never appear in the passage at all.

That expansion is the interesting property for this corpus. A section about
"deviation from the Risk Appetite" can acquire weight on "exception", "breach",
"approval" - terms a reader would use and the drafter did not - while still
scoring through an inverted index rather than a 384-dimensional blur. It is the
one retrieval family that could plausibly fix the paraphrase cases BM25 misses
without giving up lexical precision.

## How the vector is computed

For each token position the model predicts a distribution over the vocabulary.
Take `log(1 + relu(logits))`, mask out padding, and take the maximum over
positions. The result is one weight per vocabulary term, mostly zero. Scoring is
a dot product, exactly as with BM25's inverted index.

This is the whole of SPLADE's inference path, which is why it is implemented here
rather than pulled in as a dependency: there is nothing to get subtly wrong
except the masking, and a wrong implementation is visible immediately in the
expansion terms - `expansion_for` prints them, and a model that is working puts
weight on words a human would recognise as related.

## Memory

The document matrix is vocabulary-wide and dense in memory: 30522 terms by ~950
chunks is about 116 MB in float32. That is more than the dense index (1.4 MB) and
still small enough not to need a sparse matrix library, which would be another
dependency to defend for no measurable gain at this corpus size.
"""

from __future__ import annotations

import numpy as np

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.text import indexable_text

# The OpenSearch checkpoint rather than naver/splade-cocondenser-ensembledistil,
# and the reason is an environment constraint worth recording rather than
# working around.
#
# The naver checkpoints publish only `pytorch_model.bin`. transformers refuses to
# load a pickle checkpoint unless torch is 2.6 or newer (CVE-2025-32434), and
# this project pins torch 2.5.1 - in requirements, in the Dockerfile, and in
# every measurement already reported. Upgrading torch to run one more experiment
# would mean every prior number was measured on a different stack, and loading
# the pickle anyway would be executing downloaded code past a check that exists
# for good reason.
#
# This checkpoint is the same family and the same inference path, encodes queries
# and documents symmetrically, and ships safetensors. `expansion_for` confirms it
# behaves: on a passage about deviation from risk appetite it weights "appetite",
# "deviation", "board" and "approval" from the text, and expands to "hunger",
# "risks" and "approved", which are not in it.
DEFAULT_MODEL = "opensearch-project/opensearch-neural-sparse-encoding-v2-distill"
MAX_LENGTH = 512


class SpladeRetriever:
    """Learned sparse retrieval over the vocabulary."""

    name = "splade"

    def __init__(
        self,
        chunks: list[Chunk],
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
        batch_size: int = 8,
        include_doc_title: bool = False,
    ) -> None:
        if not chunks:
            raise ValueError("SpladeRetriever needs at least one chunk")
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer

        self._torch = torch
        self.chunks = chunks
        self.model_name = model_name
        self.device = device
        self.include_doc_title = include_doc_title
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name).to(device).eval()

        texts = [indexable_text(c, include_doc_title) for c in chunks]
        self.matrix = np.vstack(
            [self._encode(texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
        )

    def _encode(self, texts: list[str]) -> np.ndarray:
        torch = self._torch
        batch = self.tokenizer(
            texts, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt"
        ).to(self.device)
        with torch.no_grad():
            logits = self.model(**batch).logits
        weighted = torch.log1p(torch.relu(logits))
        # Padding positions would otherwise contribute their own predictions to
        # the max, which is the one way to get this wrong quietly.
        masked = weighted * batch["attention_mask"].unsqueeze(-1)
        return torch.max(masked, dim=1).values.cpu().numpy().astype(np.float32)

    def expansion_for(self, text: str, top: int = 12) -> list[tuple[str, float]]:
        """The terms SPLADE puts weight on - the check that it is working.

        A correct implementation puts weight on words a reader would recognise as
        related to the passage, including ones absent from it. A broken one puts
        weight on punctuation and subword fragments.
        """
        vector = self._encode([text])[0]
        order = np.argsort(-vector)[:top]
        return [
            (self.tokenizer.convert_ids_to_tokens(int(i)), round(float(vector[i]), 3))
            for i in order
            if vector[i] > 0
        ]

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        vector = self._encode([query])[0]
        scores = self.matrix @ vector
        k = min(k, len(self.chunks))
        top = np.argpartition(-scores, k - 1)[:k]
        ranked = sorted(top, key=lambda i: (-scores[i], i))
        return [
            RetrievalResult(chunk=self.chunks[i], score=float(scores[i]), rank=rank)
            for rank, i in enumerate(ranked, start=1)
        ]
