"""Tests for Phase 2 parsing and chunking.

The property that matters throughout: a chunk's evidence_id must be the section
a human would cite. Everything else about ingestion can be changed later without
invalidating benchmark labels; that cannot.
"""

from __future__ import annotations

import pytest

from regulens.ingest.chunk import chunk_sections, count_tokens
from regulens.ingest.parse import parse_html, section_label
from regulens.retrieval.base import Chunk


def page(*sections: tuple[str, str]) -> str:
    """Build Rulebook-shaped HTML: h2.page-title followed by div.field--name-body.

    Includes the three empty chrome blocks that precede all content on every
    real page, so the tests exercise the same layout the parser meets.
    """
    chrome = '<div class="content"><div class="field--name-body"></div></div>' * 3
    body = "".join(
        f'<h2 class="page-title">{h}</h2>'
        f'<div class="field--name-body">{t}</div>'
        for h, t in sections
    )
    return f"<html><body>{chrome}{body}</body></html>"


# --- section_label ----------------------------------------------------------


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("Article (3): Effective Risk Management System", "Article 3"),
        ("Article (1)", "Article 1"),
        ("Article 2 Scope of Application", "Article 2"),
        ("Article (10): Actuarial Function", "Article 10"),
        ("3.1 The Board", "3.1"),
        ("6.1.6 Something Specific", "6.1.6"),
        ("1. Definitions", "1"),
        ("Chapter Two: Electronic Insurance Strategy", "Chapter Two"),
        ("Appendix (1)", "Appendix 1"),
        ("Appendix 1 Financial Statement Forms", "Appendix 1"),
        ("Schedule No. (1)", "Schedule 1"),
        ("Annex A", "Annex A"),
        ("Section (2) Regulations Pertinent to the Solvency Margin", "Section 2"),
        ("Definitions", "Definitions"),
        ("General Provisions", "General Provisions"),
    ],
)
def test_section_label_matches_what_a_labeller_would_write(heading, expected):
    assert section_label(heading) == expected


def test_article_numbering_is_canonical_across_printed_variants():
    """'Article (5)' and 'Article 5' are the same section and must not diverge."""
    assert section_label("Article (5)") == section_label("Article 5 Control Functions")


def test_typographic_quotes_are_normalised():
    """A curly apostrophe in a label would never match one typed by hand."""
    assert "’" not in section_label("Shari’ah Governance")
    assert section_label("Shari’ah Governance") == "Shari'ah Governance"


# --- parse_html -------------------------------------------------------------


def test_chrome_blocks_are_not_mistaken_for_sections():
    doc = parse_html(page(("Doc Title", "preamble"), ("Article (1)", "text")), "D1")
    assert [s.section for s in doc.sections] == ["Preamble", "Article 1"]


def test_first_section_is_the_preamble():
    doc = parse_html(page(("Some Regulation", "Having perused..."), ("Article (1)", "x")), "D1")
    assert doc.sections[0].section == "Preamble"
    assert doc.sections[0].metadata["doc_title"] == "Some Regulation"


def test_evidence_id_is_doc_and_section():
    doc = parse_html(page(("T", "p"), ("Article (7): Risk", "body")), "INS-GOV-003")
    article = doc.sections[1]
    assert article.evidence_id == "INS-GOV-003::Article 7"


def test_bodiless_heading_titles_the_next_section_rather_than_stealing_it():
    """The Rulebook prints 'Definitions' then 'Article (1)' as separate headings.

    The descriptive one carries no body. It must neither absorb the next
    section's text nor be discarded - it is the section's title, and the words
    most likely to match a query.
    """
    html = (
        '<html><body>'
        '<h2 class="page-title">Doc</h2><div class="field--name-body">pre</div>'
        '<h2 class="page-title">Grievance</h2>'
        '<h2 class="page-title">Article (1)</h2>'
        '<div class="field--name-body">the real text</div>'
        "</body></html>"
    )
    doc = parse_html(html, "D1")
    assert [s.section for s in doc.sections] == ["Preamble", "Article 1"]
    assert doc.sections[1].text == "the real text"
    assert doc.sections[1].metadata["section_title"] == "Grievance"
    assert doc.sections[1].metadata["section_heading"] == "Article (1)"


def test_a_title_applies_only_to_the_next_section():
    doc = parse_html(
        '<html><body>'
        '<h2 class="page-title">Doc</h2><div class="field--name-body">pre</div>'
        '<h2 class="page-title">Penalties</h2>'
        '<h2 class="page-title">Article (1)</h2><div class="field--name-body">a</div>'
        '<h2 class="page-title">Article (2)</h2><div class="field--name-body">b</div>'
        "</body></html>",
        "D1",
    )
    assert doc.sections[1].metadata["section_title"] == "Penalties"
    # Article 2 has no title of its own; it must not inherit Article 1's.
    assert doc.sections[2].metadata["section_title"] == "Article (2)"


def test_compound_instrument_labels_are_qualified_by_their_section():
    """Article numbering restarts per Part in some instruments (INS-FIN-001).

    Bare 'Article 1' would name two different provisions, so it cannot serve as
    an evidence id. The qualifier must come from the document's own addressing,
    not from a counter invented by the parser.
    """
    doc = parse_html(
        '<html><body>'
        '<h2 class="page-title">Doc</h2><div class="field--name-body">pre</div>'
        '<h2 class="page-title">Section 1 Investments</h2>'
        '<h2 class="page-title">Article (1)</h2><div class="field--name-body">a</div>'
        '<h2 class="page-title">Section (2) Solvency</h2>'
        '<h2 class="page-title">Article (1)</h2><div class="field--name-body">b</div>'
        "</body></html>",
        "INS-FIN-001",
    )
    labels = [s.section for s in doc.sections]
    assert labels == ["Preamble", "Section 1, Article 1", "Section 2, Article 1"]
    assert len({s.evidence_id for s in doc.sections}) == 3
    # No parser-invented counter should appear.
    assert not any("(2)" in label for label in labels)
    assert doc.warnings == []


def test_structural_headings_are_carried_as_running_context():
    """A Chapter governs every following section, not just the next one."""
    doc = parse_html(
        '<html><body>'
        '<h2 class="page-title">Doc</h2><div class="field--name-body">pre</div>'
        '<h2 class="page-title">Chapter Two</h2>'
        '<h2 class="page-title">Article (1)</h2><div class="field--name-body">a</div>'
        '<h2 class="page-title">Article (2)</h2><div class="field--name-body">b</div>'
        "</body></html>",
        "D1",
    )
    assert doc.sections[1].metadata["parent_heading"] == "Chapter Two"
    assert doc.sections[2].metadata["parent_heading"] == "Chapter Two"


def test_duplicate_labels_are_disambiguated_and_warned():
    doc = parse_html(
        page(("T", "p"), ("Definitions", "first"), ("Definitions", "second")), "D1"
    )
    assert [s.section for s in doc.sections] == ["Preamble", "Definitions", "Definitions (2)"]
    assert len({s.evidence_id for s in doc.sections}) == 3
    assert any("duplicate section label" in w for w in doc.warnings)


def test_empty_document_is_reported_not_raised():
    doc = parse_html("<html><body></body></html>", "D1")
    assert doc.sections == []
    assert doc.warnings


# --- chunk_sections ---------------------------------------------------------


def section(text: str, doc_id: str = "D1", label: str = "Article 1") -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}::{label}",
        doc_id=doc_id,
        section=label,
        text=text,
        metadata={"section_title": label},
    )


def test_short_sections_pass_through_untouched():
    original = section("a b c")
    assert chunk_sections([original], max_tokens=10, overlap=0) == [original]


def test_long_section_splits_but_keeps_one_evidence_id():
    long_text = "\n".join(f"clause {i} " + "word " * 40 for i in range(20))
    chunks = chunk_sections([section(long_text)], max_tokens=100, overlap=10)
    assert len(chunks) > 1
    assert {c.evidence_id for c in chunks} == {"D1::Article 1"}
    assert {c.section for c in chunks} == {"Article 1"}


def test_split_chunk_ids_are_unique():
    long_text = "\n".join("word " * 60 for _ in range(10))
    chunks = chunk_sections([section(long_text)], max_tokens=100, overlap=0)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_no_chunk_greatly_exceeds_the_budget():
    long_text = "\n".join("word " * 30 for _ in range(40))
    chunks = chunk_sections([section(long_text)], max_tokens=120, overlap=20)
    # Overlap is prepended before the next paragraph, so a chunk may exceed the
    # budget by up to one paragraph. It must not run away beyond that.
    assert all(count_tokens(c.text) <= 120 + 30 for c in chunks)


def test_paragraph_longer_than_budget_is_still_split():
    """A single unbroken clause must not produce one oversized chunk."""
    one_paragraph = ". ".join("word " * 50 for _ in range(10))
    chunks = chunk_sections([section(one_paragraph)], max_tokens=100, overlap=0)
    assert len(chunks) > 1


def test_no_text_is_lost_when_overlap_is_zero():
    paragraphs = [f"para{i} " + "word " * 30 for i in range(10)]
    chunks = chunk_sections([section("\n".join(paragraphs))], max_tokens=100, overlap=0)
    joined = " ".join(c.text for c in chunks)
    for i in range(10):
        assert f"para{i}" in joined


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        chunk_sections([section("x")], max_tokens=0)
    with pytest.raises(ValueError):
        chunk_sections([section("x")], max_tokens=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_sections([section("x")], max_tokens=100, overlap=-1)
