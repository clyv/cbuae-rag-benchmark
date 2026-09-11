"""Tests for query rewriting.

The measured result is that rewriting does not help this corpus. That claim is
only worth making if the rewriters actually rewrote, so these check that they
change the query in the way they claim to - and that a failing generator degrades
to plain retrieval rather than taking the query down with it.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk, RetrievalResult
from regulens.retrieval.rewrite import (
    HypotheticalAnswerRewriter,
    PseudoRelevanceRewriter,
    RewrittenRetriever,
)


def chunk(text: str, section: str = "Article 1") -> Chunk:
    return Chunk(f"D::{section}", "D", section, text, {})


class Fixed:
    name = "fixed"

    def __init__(self, chunks):
        self.chunks = chunks
        self.asked: list[str] = []

    def retrieve(self, query: str, k: int):
        self.asked.append(query)
        return [
            RetrievalResult(chunk=c, score=10.0 - i, rank=i + 1)
            for i, c in enumerate(self.chunks[:k])
        ]


# --- pseudo-relevance feedback ---------------------------------------------


def test_expansion_adds_terms_from_the_first_results():
    base = Fixed([chunk("The actuary must certify the technical provisions annually.")])
    rewriter = PseudoRelevanceRewriter(base)
    terms = rewriter.expansion_terms("who signs off")
    assert "actuary" in terms
    assert "certify" in terms


def test_words_already_in_the_query_are_not_added_back():
    base = Fixed([chunk("The actuary must certify provisions.")])
    terms = PseudoRelevanceRewriter(base).expansion_terms("what does the actuary do")
    assert "actuary" not in terms


def test_domain_noise_is_not_used_as_an_expansion_term():
    """"insurance" and "company" appear in nearly every section of this corpus,
    so adding them discriminates between nothing."""
    base = Fixed([chunk("The insurance company shall notify the Central Bank.")])
    terms = PseudoRelevanceRewriter(base).expansion_terms("notification duty")
    assert "insurance" not in terms
    assert "company" not in terms


def test_english_stopwords_are_not_used_as_expansion_terms():
    """tokenize() does not strip these, because BM25's IDF discounts them
    anyway. Pseudo-relevance feedback counts raw occurrences and has no such
    protection - a first version of this appended "into related from this
    between" to every query."""
    base = Fixed([chunk("The actuary shall report from within the period between reviews.")])
    terms = PseudoRelevanceRewriter(base).expansion_terms("reporting duty")
    for noise in ("from", "within", "between", "shall", "this", "related"):
        assert noise not in terms


def test_short_terms_and_bare_numbers_are_skipped():
    base = Fixed([chunk("The fund shall hold AED 250 000 000 in reserve.")])
    terms = PseudoRelevanceRewriter(base).expansion_terms("how much")
    assert all(not t.isdigit() for t in terms)
    assert all(len(t) >= 4 for t in terms)


def test_a_term_repeated_in_one_passage_counts_once():
    """Twenty mentions in one section is not evidence that twenty sections are
    about it, so terms are counted per document."""
    base = Fixed([
        chunk("solvency solvency solvency solvency margin"),
        chunk("reserving margin", "Article 2"),
    ])
    terms = PseudoRelevanceRewriter(base, feedback_docs=2, terms=5).expansion_terms("capital")
    assert terms.index("margin") < terms.index("solvency")


def test_the_rewritten_query_keeps_the_original_words():
    base = Fixed([chunk("The actuary must certify provisions.")])
    rewritten = PseudoRelevanceRewriter(base).rewrite("who signs off")
    assert rewritten.startswith("who signs off")


def test_no_results_means_the_query_is_left_alone():
    assert PseudoRelevanceRewriter(Fixed([])).rewrite("anything") == "anything"


# --- HyDE -------------------------------------------------------------------


def test_the_hypothetical_passage_is_appended_to_the_query():
    rewriter = HypotheticalAnswerRewriter(lambda p: "The Board shall approve any deviation.")
    out = rewriter.rewrite("who approves a deviation")
    assert out.startswith("who approves a deviation")
    assert "The Board shall approve any deviation." in out


def test_the_question_can_be_dropped_entirely():
    rewriter = HypotheticalAnswerRewriter(lambda p: "The Board shall approve.", keep_question=False)
    assert rewriter.rewrite("who approves") == "The Board shall approve."


def test_a_generator_that_raises_falls_back_to_the_plain_query():
    """A model failing is a reason to retrieve normally, not to fail the query."""
    def explode(prompt):
        raise RuntimeError("out of memory")

    assert HypotheticalAnswerRewriter(explode).rewrite("who approves") == "who approves"


def test_an_empty_generation_falls_back_to_the_plain_query():
    assert HypotheticalAnswerRewriter(lambda p: "   ").rewrite("who approves") == "who approves"


def test_whitespace_in_the_generation_is_collapsed():
    rewriter = HypotheticalAnswerRewriter(lambda p: "The Board\n\n  shall   approve.")
    assert "The Board shall approve." in rewriter.rewrite("q")


# --- the wrapper ------------------------------------------------------------


def test_the_base_retriever_is_asked_the_rewritten_query():
    base = Fixed([chunk("text")])
    wrapped = RewrittenRetriever(base, HypotheticalAnswerRewriter(lambda p: "hypothetical passage"))
    wrapped.retrieve("original question", k=1)
    assert base.asked == ["original question hypothetical passage"]


def test_what_was_rewritten_is_recorded():
    """So a run can report what the rewriter did rather than asking the reader
    to trust that it did anything."""
    base = Fixed([chunk("text")])
    wrapped = RewrittenRetriever(base, HypotheticalAnswerRewriter(lambda p: "passage"))
    wrapped.retrieve("q", k=1)
    assert wrapped.rewrites["q"] == "q passage"
