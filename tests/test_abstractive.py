"""Tests for resolving a model's citation tags into evidence ids.

The measurement in `results/abstractive.md` rests entirely on these rules: a tag
that resolves becomes a citation and is checked, a tag that does not is lost.
Getting them wrong would move the headline number without any model behaving
differently, so they are tested directly. The model is never loaded.
"""

from __future__ import annotations

from regulens.generation.abstractive import parse_answer, split_claims
from regulens.generation.answer import validate_citations
from regulens.retrieval.base import Chunk, RetrievalResult

FIRST = "The Board must approve the Risk Appetite statement in writing."
SECOND = "The head of a control function must not underwrite or invest."


def result(section: str, text: str, rank: int) -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(f"D::{section}", "D", section, text, {"url": "https://example.invalid"}),
        score=5.0,
        rank=rank,
    )


def context() -> list[RetrievalResult]:
    return [result("Article 3", FIRST, 1), result("Article 5", SECOND, 2)]


def test_a_tag_resolves_to_the_passage_it_numbers():
    answer = parse_answer("The Board approves it. [1]", context())
    assert [c.evidence_id for c in answer.citations] == ["D::Article 3"]


def test_the_quote_is_the_claim_not_the_source():
    """validate_citations then asks whether the section contains the claim's
    words. Storing the source text instead would make every citation supported
    by definition and the measurement meaningless."""
    answer = parse_answer("Deviations need Board approval. [1]", context())
    assert answer.citations[0].quote == "Deviations need Board approval."


def test_an_out_of_range_tag_is_dropped_not_clamped():
    """A number the model invented is not a citation to anything. Clamping it to
    the nearest passage would manufacture a grounded citation out of an error."""
    answer = parse_answer("Something about capital. [7]", context())
    assert answer.citations == []


def test_one_bad_tag_does_not_discard_the_good_one():
    answer = parse_answer("A claim. [1][9]", context())
    assert [c.evidence_id for c in answer.citations] == ["D::Article 3"]


def test_a_claim_tagged_to_several_passages_cites_all_of_them():
    """This is the over-attribution the results write-up measures: one claim
    credited to two sections, checked against both."""
    answer = parse_answer("A claim drawn from both. [1][2]", context())
    assert len(answer.citations) == 2


def test_over_attribution_is_visible_to_validation():
    """The sentence is verbatim from passage 1, so the citation to passage 2
    must fail support rather than ride along on it."""
    answer = parse_answer(f"{FIRST} [1][2]", context())
    scores = validate_citations(answer, min_overlap_ratio=0.6)
    assert scores["grounded"] == 1.0
    assert scores["supported"] == 0.5


def test_comma_separated_tags_resolve():
    assert len(parse_answer("A claim. [1, 2]", context()).citations) == 2


def test_a_section_cited_twice_is_one_citation():
    answer = parse_answer("First claim. [1] Second claim. [1]", context())
    assert len(answer.citations) == 1


def test_the_refusal_string_is_an_abstention():
    answer = parse_answer("Not covered by these passages.", context())
    assert answer.abstained
    assert not answer.citations
    assert validate_citations(answer)["abstained"] == 1.0


def test_a_refusal_is_recognised_regardless_of_case():
    assert parse_answer("not covered by these passages", context()).abstained


def test_prose_that_merely_mentions_the_refusal_still_answers():
    """Only a reply that opens with the refusal is a refusal. Matching anywhere
    would let a real answer discussing coverage be recorded as a decline."""
    answer = parse_answer(
        "This is not covered by these passages except in Article 3. [1]", context()
    )
    assert not answer.abstained
    assert answer.citations


def test_a_trailing_tag_belongs_to_the_claim_before_it():
    """The prompt asks for the numbers at the end of each sentence, so this is
    the shape the model actually produces. Splitting on the full stop stranded
    the tag at the head of the next segment, which quoted the wrong claim."""
    claims = split_claims("Deviations need approval. [1] A different point. [2]")
    assert claims == [("Deviations need approval.", [1]), ("A different point.", [2])]


def test_a_leading_tag_belongs_to_the_claim_after_it():
    assert split_claims("[1] The Board approves it.") == [("The Board approves it.", [1])]


def test_the_last_citation_quotes_its_claim_not_nothing():
    """An empty quote has no words to check, so a correct citation scored as
    unsupported. This is the regression that moved the measured number."""
    answer = parse_answer(f"{FIRST} [1]", context())
    assert answer.citations[0].quote == FIRST


def test_adjacent_tags_are_one_cluster_sharing_one_claim():
    assert split_claims("A claim. [2][3]") == [("A claim.", [2, 3])]


def test_a_bare_tag_with_no_prose_is_not_a_citation():
    assert parse_answer("[1]", context()).citations == []


def test_an_untagged_answer_carries_no_citations():
    """Fluent prose with no tags is not evidence of anything, and scores zero
    rather than being credited to whatever was retrieved."""
    answer = parse_answer("The Board approves it.", context())
    assert answer.citations == []
    assert validate_citations(answer)["grounded"] == 0.0
