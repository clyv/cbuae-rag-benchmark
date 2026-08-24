"""Evidence-grounded answer generation.

STUB - Phase 5, and deliberately last.

Two non-negotiables, both of which are the actual selling points:

  1. The model answers ONLY from the retrieved passages, and must decline when
     the evidence does not support an answer. Test this with the
     'unanswerable' benchmark category.
  2. Every claim carries a citation to a doc_id and section. Then validate the
     citations programmatically - check the cited section was actually in the
     retrieved context. An uncited or mis-cited claim is a failure you can
     count without any legal expertise.

Citation validity is measurable and defensible. Legal correctness is not.
Report the first and disclaim the second.
"""

from __future__ import annotations

from dataclasses import dataclass

from regulens.retrieval.base import RetrievalResult


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: list[tuple[str, str]]
    abstained: bool
    context_used: list[RetrievalResult]


def generate_answer(question: str, context: list[RetrievalResult]) -> GroundedAnswer:
    raise NotImplementedError("Phase 5")


def validate_citations(answer: GroundedAnswer) -> dict[str, float]:
    """Fraction of citations that point at sections actually in the context."""
    raise NotImplementedError("Phase 5")
