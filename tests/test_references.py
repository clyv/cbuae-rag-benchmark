"""Tests for cross-reference extraction.

An edge here is a claim that one provision points at another, and a wrong edge
would inject an unrelated section into retrieval while looking like structure.
The rules that decide what resolves - and what is deliberately dropped - are
therefore pinned individually.
"""

from __future__ import annotations

from regulens.graph.references import (
    build_adjacency,
    companion_documents,
    extract_references,
    resolve_label,
    target_label,
)


def section(doc_id: str, label: str, text: str, title: str = "") -> dict:
    return {
        "doc_id": doc_id,
        "section": label,
        "text": text,
        "metadata": {"doc_title": title or f"{doc_id} Regulation"},
    }


def corpus() -> list[dict]:
    return [
        section("D1", "Article 1", "Definitions apply throughout."),
        section("D1", "Article 2", "The limits are as directed in Article (3)."),
        section("D1", "Article 3", "Counterparty limits are set out here."),
        section("D2", "Article 1", "Unrelated instrument."),
    ]


# --- resolving a bare reference ---------------------------------------------


def test_a_bare_reference_resolves_within_the_citing_document():
    references, _ = extract_references(corpus())
    assert [(r.source, r.target) for r in references] == [("D1::Article 2", "D1::Article 3")]


def test_a_compound_document_keeps_its_own_division():
    """Numbering restarts inside compound instruments, so Article 3 cited from
    Section 1 is Section 1's third article, not Section 2's."""
    assert target_label("Section 1, Article 2", 3) == "Section 1, Article 3"


def test_a_section_with_no_numbering_context_inherits_nothing():
    """A Preamble has no article number to carry over, and inventing one would
    manufacture edges out of front matter."""
    assert target_label("Preamble", 3) is None


def test_continuous_numbering_falls_back_to_a_unique_match():
    """Some instruments number articles straight through their chapters, so the
    citing chapter's prefix builds a label that does not exist. A single article
    with that number elsewhere in the document is unambiguous."""
    labels = {"Chapter One, Article 5", "Chapter Five, Article 39"}
    assert resolve_label(39, labels, "Chapter One, Article 5", None) == "Chapter Five, Article 39"


def test_an_ambiguous_number_resolves_to_nothing():
    """Article 3 exists in two divisions and the citing section names neither,
    so there is no fact of the matter and no edge."""
    labels = {"Section 1, Article 3", "Section 2, Article 3"}
    assert resolve_label(3, labels, "Preamble", None) is None


def test_an_explicit_division_beats_the_citing_context():
    labels = {"Section 1, Article 10", "Section 2, Article 10"}
    assert resolve_label(10, labels, "Section 1, Article 4", 2) == "Section 2, Article 10"


# --- what must not become an edge -------------------------------------------


def test_a_self_reference_is_not_an_edge():
    rows = [section("D1", "Article 2", "As stated in paragraph (1) of this Article (2), the rule holds.")]
    references, census = extract_references(rows)
    assert references == []


def test_a_reference_to_law_outside_the_corpus_is_dropped_and_counted():
    rows = [section("D1", "Article 2", "Pursuant to Article (5) of the Central Bank Law, the rule holds.")]
    references, census = extract_references(rows)
    assert references == []
    assert census["external"] == 1


def test_a_reference_to_a_section_that_does_not_exist_is_dropped():
    """Resolution is checked against the corpus, so a rule that guesses wrong
    produces no edge rather than a wrong one."""
    rows = [section("D1", "Article 2", "See Article (99).")]
    references, census = extract_references(rows)
    assert references == []
    assert census["unresolved_target"] == 1


def test_the_same_pair_is_not_counted_twice():
    rows = [
        section("D1", "Article 2", "See Article (3). And again, Article (3)."),
        section("D1", "Article 3", "Here."),
    ]
    references, _ = extract_references(rows)
    assert len(references) == 1


# --- ranges and lists -------------------------------------------------------


def test_a_range_produces_an_edge_for_every_article_in_it():
    rows = [
        section("D1", "Article 20", "Disclosures in Articles (2) to (4) apply."),
        section("D1", "Article 2", "a"),
        section("D1", "Article 3", "b"),
        section("D1", "Article 4", "c"),
    ]
    references, _ = extract_references(rows)
    assert sorted(r.target for r in references) == ["D1::Article 2", "D1::Article 3", "D1::Article 4"]


def test_a_list_produces_an_edge_for_each_listed_article():
    rows = [
        section("D1", "Article 20", "Requirements in Articles (2), (3) and (4) apply."),
        section("D1", "Article 2", "a"),
        section("D1", "Article 3", "b"),
        section("D1", "Article 4", "c"),
    ]
    references, _ = extract_references(rows)
    assert len(references) == 3


def test_a_sub_article_is_not_a_reference_to_that_article():
    """"Sub-Article (11) of Article (13)" points at article 13. Reading the
    first number as the reference takes a paragraph number for a provision."""
    rows = [
        section("D1", "Article 20", "As in Sub-Article (11) of Article (13) of this Regulation."),
        section("D1", "Article 11", "a"),
        section("D1", "Article 13", "b"),
    ]
    references, _ = extract_references(rows)
    assert [r.target for r in references] == ["D1::Article 13"]


def test_a_bare_number_after_a_reference_is_not_a_second_article():
    """"Article (5) and 3 years" names one article. Requiring parentheses on the
    continuation is what keeps a duration from becoming an edge."""
    rows = [
        section("D1", "Article 20", "Under Article (2) and 3 years thereafter."),
        section("D1", "Article 2", "a"),
        section("D1", "Article 3", "b"),
    ]
    references, _ = extract_references(rows)
    assert [r.target for r in references] == ["D1::Article 2"]


# --- companion instruments --------------------------------------------------


def test_a_regulation_and_its_standards_are_paired_by_title():
    rows = [
        section("R", "Article 1", "x", title="Corporate Governance Regulation for Insurance"),
        section("S", "Article 1", "y", title="Corporate Governance Standards for Insurance"),
    ]
    assert companion_documents(rows) == {"R": "S", "S": "R"}


def test_a_regulation_citing_the_standards_crosses_to_them():
    rows = [
        section("R", "Article 1", "As set out in Article (2) of the Standards.",
                title="Corporate Governance Regulation for Insurance"),
        section("S", "Article 2", "y", title="Corporate Governance Standards for Insurance"),
    ]
    references, _ = extract_references(rows)
    assert [(r.source, r.target) for r in references] == [("R::Article 1", "S::Article 2")]


def test_the_standards_citing_the_standards_means_itself():
    """Said from inside the Standards, "of the Standards" is not a pointer at the
    companion Regulation - reading it as one invents a cross-document edge."""
    rows = [
        section("S", "Article 1", "The criteria in Article (2) of the Standards apply.",
                title="Corporate Governance Standards for Insurance"),
        section("S", "Article 2", "y", title="Corporate Governance Standards for Insurance"),
        section("R", "Article 2", "z", title="Corporate Governance Regulation for Insurance"),
    ]
    references, _ = extract_references(rows)
    assert [(r.source, r.target) for r in references] == [("S::Article 1", "S::Article 2")]


# --- the graph --------------------------------------------------------------


def test_adjacency_is_undirected():
    """Which provision the drafter pointed from is not a fact about where the
    answer lives, so retrieval treats the pair as related both ways."""
    references, _ = extract_references(corpus())
    adjacency = build_adjacency(references)
    assert adjacency["D1::Article 2"] == ["D1::Article 3"]
    assert adjacency["D1::Article 3"] == ["D1::Article 2"]


def test_sections_with_no_references_are_absent_from_the_graph():
    adjacency = build_adjacency(extract_references(corpus())[0])
    assert "D2::Article 1" not in adjacency
