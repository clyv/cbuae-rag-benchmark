"""Evidence-grounded answering.

Phase 5. Two things here are measurable without legal expertise, and they are
the only things this module claims:

  1. **Abstention.** Does the system decline when the corpus does not support an
     answer? The `unanswerable` benchmark category tests exactly this.
  2. **Citation validity.** Does every claim point at a section that was
     actually retrieved, and does that section actually contain the words the
     claim rests on?

Neither is a claim about legal correctness, which this project does not make.

## Why the default answerer is extractive

It quotes the retrieved sections and attributes each quote. That is grounded by
construction: the answer *is* the cited text, so it cannot assert something the
source does not say, and citation validity is 1.0 by definition rather than by
measurement.

That sounds like cheating and is the point. It sets the bar an abstractive
generator has to clear: a model that paraphrases is more readable and can drop
below 1.0, and the gap between the two is the cost of fluency. Reporting the
extractive baseline first makes that cost visible instead of letting a model's
readability stand in for its faithfulness.

An abstractive generator plugs in behind `Generator`. None ships here - see the
README on why a local generative model was out of scope for this phase.

## Why abstention keys off the reranker's score

Deciding to decline needs a relevance score that means something on its own.
BM25 scores are unbounded and corpus-dependent; RRF fusion scores are a function
of rank position and say nothing about whether the top result is any good - a
document ranked first among rubbish scores exactly as highly as one ranked first
among excellent matches.

A cross-encoder logit is different: it is a judgement about *this* passage
against *this* question, comparable across queries. So the reranker earns a
second justification beyond the ranking quality reported in Phase 4 - it is what
makes abstention possible at all. Systems without it can still answer; they
cannot sensibly decline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from regulens.retrieval.base import RetrievalResult

# Words too common to count as evidence that a sentence came from a passage.
_STOPWORDS = frozenset(
    """a an and are as at be been but by for from had has have if in into is it its
    must no not of on or shall should such that the their there these this to was
    were which who will with within would""".split()
)


@dataclass(frozen=True)
class Citation:
    doc_id: str
    section: str
    quote: str
    url: str = ""

    @property
    def evidence_id(self) -> str:
        return f"{self.doc_id}::{self.section}"


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    abstained: bool = False
    context_used: list[RetrievalResult] = field(default_factory=list)
    reason: str = ""
    top_score: float | None = None


class Generator(Protocol):
    """Turns a question plus retrieved context into answer text and citations."""

    name: str

    def generate(self, question: str, context: list[RetrievalResult]) -> GroundedAnswer: ...


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _best_passage(chunk_text: str, question: str, max_chars: int) -> str:
    """The stretch of a section most likely to be the part that answers.

    Regulatory sections run to hundreds of words and quoting all of it is not an
    answer. Picking the sentences with the most overlap with the question is
    crude, but it is transparent and cannot introduce anything the section does
    not say, which a summariser could.
    """
    wanted = _tokens(question)
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+|\n+", chunk_text) if s.strip()]
    if not sentences:
        return chunk_text[:max_chars]

    scored = sorted(
        range(len(sentences)),
        key=lambda i: (-len(_tokens(sentences[i]) & wanted), i),
    )
    keep = sorted(scored[:3])
    quote = " ".join(sentences[i] for i in keep)
    return quote[:max_chars].rstrip()


class ExtractiveGenerator:
    """Quotes the retrieved sections and attributes each quote."""

    name = "extractive"

    def __init__(self, max_citations: int = 3, quote_chars: int = 400) -> None:
        self.max_citations = max_citations
        self.quote_chars = quote_chars

    def generate(self, question: str, context: list[RetrievalResult]) -> GroundedAnswer:
        citations: list[Citation] = []
        # One citation per section: several chunks of the same article are one
        # source, and listing it twice would overstate how much support there is.
        seen: set[str] = set()
        for result in context:
            key = f"{result.chunk.doc_id}::{result.chunk.section}"
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    doc_id=result.chunk.doc_id,
                    section=result.chunk.section,
                    quote=_best_passage(result.chunk.text, question, self.quote_chars),
                    url=result.chunk.metadata.get("url", ""),
                )
            )
            if len(citations) >= self.max_citations:
                break

        body = "\n\n".join(f"{c.evidence_id}:\n{c.quote}" for c in citations)
        return GroundedAnswer(text=body, citations=citations, context_used=context)


def answer_question(
    question: str,
    context: list[RetrievalResult],
    generator: Generator | None = None,
    threshold: float | None = None,
) -> GroundedAnswer:
    """Answer from the retrieved context, or decline.

    `threshold` applies to the top result's score. Above it the question is
    answered from the context; at or below it the system declines. Passing None
    disables abstention, which is the right setting when the retriever's scores
    are not comparable across queries - see the module docstring.
    """
    generator = generator or ExtractiveGenerator()

    if not context:
        return GroundedAnswer(
            text="The corpus does not contain material that answers this question.",
            abstained=True,
            reason="nothing retrieved",
        )

    top = context[0].score
    if threshold is not None and top <= threshold:
        return GroundedAnswer(
            text=(
                "The corpus does not appear to contain material that answers this "
                "question. Nothing retrieved was judged relevant enough to answer from."
            ),
            abstained=True,
            context_used=context,
            reason=f"top relevance {top:.3f} at or below threshold {threshold:.3f}",
            top_score=top,
        )

    answer = generator.generate(question, context)
    # A generator may decline on its own account - a model can judge that the
    # passages do not answer, which the score threshold above cannot see.
    # Overwriting that with False silently discards the refusal and reports a
    # decline as an answer with no citations.
    return GroundedAnswer(
        text=answer.text,
        citations=answer.citations,
        abstained=answer.abstained,
        context_used=context,
        reason=answer.reason,
        top_score=top,
    )


def validate_citations(
    answer: GroundedAnswer, min_overlap: int = 4, min_overlap_ratio: float = 0.0
) -> dict[str, float]:
    """Check every citation against the context it claims to come from.

    Two failures are counted separately because they are different faults:

    **Ungrounded** - the citation names a section that was not in the retrieved
    context at all. For a generated answer this is the citation being invented.

    **Unsupported** - the section was retrieved, but the quoted text does not
    appear in it. The citation points somewhere real and the words attributed to
    it are not there.

    An extractive answerer scores 1.0 on both by construction. That is the
    baseline an abstractive generator has to be measured against, not a result.
    """
    if answer.abstained:
        return {"citations": 0, "grounded": 1.0, "supported": 1.0, "abstained": 1.0}
    if not answer.citations:
        return {"citations": 0, "grounded": 0.0, "supported": 0.0, "abstained": 0.0}

    available = {
        f"{r.chunk.doc_id}::{r.chunk.section}": r.chunk.text for r in answer.context_used
    }

    grounded = 0
    supported = 0
    for citation in answer.citations:
        source = available.get(citation.evidence_id)
        if source is None:
            continue
        grounded += 1
        quoted = _tokens(citation.quote)
        if not quoted:
            continue
        # Verbatim first; fall back to token overlap so a quote that was
        # trimmed or rejoined across a line break is not counted as invented.
        #
        # `min_overlap_ratio` is off by default, which suits an extractive
        # answerer whose quote is the source text. For a generated claim the
        # absolute threshold is far too lenient - four shared content words is
        # nothing in a sentence about regulation, where "company", "board" and
        # "requirements" are everywhere - so the abstractive measurement sets a
        # ratio and requires most of the claim's vocabulary to come from the
        # section it cites.
        needed = max(
            min(min_overlap, len(quoted)),
            int(round(min_overlap_ratio * len(quoted))),
        )
        if citation.quote.strip() and citation.quote.strip() in source:
            supported += 1
        elif len(quoted & _tokens(source)) >= needed:
            supported += 1

    n = len(answer.citations)
    return {
        "citations": n,
        "grounded": grounded / n,
        "supported": supported / n,
        "abstained": 0.0,
    }
