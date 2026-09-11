"""Rewriting the question before retrieving.

The standard argument: a user's question and the passage answering it are
different kinds of text. A question asks; a regulation asserts. "Who signs off on
exceeding the risk appetite?" shares little surface vocabulary with "A documented
process for the Board's approval for any deviation from the Risk Appetite." So
rewrite the query into something that looks more like the answer.

Two ways to do that are implemented here:

**Pseudo-relevance feedback** (`PseudoRelevanceRewriter`) assumes the top few
results are roughly right, harvests their distinctive terms, and re-queries with
those added. No model, no extra latency worth measuring. It is the oldest trick
in information retrieval and it still works when the first pass is decent.

**HyDE** (`HypotheticalAnswerRewriter`) asks a language model to *write* the
passage it thinks would answer, then retrieves with that. The hypothetical text
is usually wrong on facts and right on register, which is the point - it is used
as a query, never shown to anyone.

## The prediction, written down first

Both should disappoint on this corpus, and the reason is measured rather than
guessed. `results/failures.md` classified all 39 missed sections and found
**lexical gap explains exactly one of them**. Query rewriting attacks vocabulary
mismatch. Vocabulary mismatch is not what is failing here - 62% of misses are the
right instrument and the wrong article inside it, where the question already
shares the document's vocabulary and rewriting adds nothing that discriminates.

Worse, there is a specific way it could hurt. Expansion pulls terms from the top
results, and this corpus contains matched instruments whose articles are
near-identical. Harvesting terms from a Takaful standard to sharpen a query about
its conventional counterpart would drag retrieval further toward the wrong twin.

Running it anyway, because "the obvious technique does not help here" is only
worth saying with a number attached.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Protocol

from regulens.retrieval.base import RetrievalResult, Retriever
from regulens.retrieval.text import indexable_text, tokenize

# Terms too common in this corpus to discriminate between its own documents.
# Harvested from the corpus rather than a general stoplist: "insurance" carries
# no information here, however informative it is in English at large.
DOMAIN_NOISE = frozenset(
    """insurance insurer company companies central bank authority regulation
    regulations article articles section sections shall must may board
    provisions accordance provided respect relevant applicable""".split()
)


class Rewriter(Protocol):
    name: str

    def rewrite(self, query: str) -> str: ...


class PseudoRelevanceRewriter:
    """Expand the query with distinctive terms from its own first results."""

    name = "prf"

    def __init__(
        self,
        base: Retriever,
        feedback_docs: int = 3,
        terms: int = 8,
        min_length: int = 4,
    ) -> None:
        self.base = base
        self.feedback_docs = feedback_docs
        self.terms = terms
        self.min_length = min_length

    def expansion_terms(self, query: str) -> list[str]:
        results = self.base.retrieve(query, self.feedback_docs)
        if not results:
            return []
        seen = set(tokenize(query))
        counts: Counter[str] = Counter()
        for result in results:
            # Count each term once per document: a word repeated twenty times in
            # one passage is not evidence that twenty passages are about it.
            for term in set(tokenize(indexable_text(result.chunk))):
                if (
                    term not in seen
                    and term not in DOMAIN_NOISE
                    and len(term) >= self.min_length
                    and not term.isdigit()
                ):
                    counts[term] += 1
        return [term for term, _ in counts.most_common(self.terms)]

    def rewrite(self, query: str) -> str:
        added = self.expansion_terms(query)
        return f"{query} {' '.join(added)}" if added else query


class HypotheticalAnswerRewriter:
    """Retrieve with a passage a model imagines, rather than with the question."""

    name = "hyde"

    PROMPT = (
        "Write one or two sentences of UAE insurance regulation that would answer "
        "the question below. Write it as regulatory text - an obligation, not an "
        "explanation. Do not say you are unsure and do not mention the question.\n\n"
        "Question: {question}\n\nRegulation:"
    )

    def __init__(self, generate, keep_question: bool = True) -> None:
        """`generate` takes a prompt and returns text. Kept as a callable rather
        than a model so this is testable without loading one."""
        self.generate = generate
        self.keep_question = keep_question

    def rewrite(self, query: str) -> str:
        try:
            hypothetical = self.generate(self.PROMPT.format(question=query)).strip()
        except Exception:
            # A generator failing is a reason to retrieve normally, not to fail
            # the query. Silent fallback is the right behaviour and the run
            # reports how often it happened.
            return query
        hypothetical = re.sub(r"\s+", " ", hypothetical)
        if not hypothetical:
            return query
        return f"{query} {hypothetical}" if self.keep_question else hypothetical


class RewrittenRetriever:
    """Any retriever, asked with a rewritten query."""

    def __init__(self, base: Retriever, rewriter: Rewriter) -> None:
        self.base = base
        self.rewriter = rewriter
        self.name = f"{base.name}+{rewriter.name}"
        self.rewrites: dict[str, str] = {}

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        rewritten = self.rewriter.rewrite(query)
        # Kept so a run can report what the rewriter actually did, rather than
        # leaving the reader to trust that it did anything.
        self.rewrites[query] = rewritten
        return self.base.retrieve(rewritten, k)
