"""CBUAE Rulebook HTML -> structured sections.

Phase 2. The stub that stood here assumed PDFs and heading heuristics. Neither
turned out to be necessary: the Rulebook publishes every instrument as HTML in
which each section is an `h2.page-title` followed by a `div.field--name-body`,
so the document's own structure is machine-readable and no layout inference is
needed. scripts/download_corpus.py stores that HTML in corpus/raw/.

The one hard requirement from the stub still holds and drives everything here:
every unit of text carries its doc_id and its section identifier as printed in
the document. `Chunk.evidence_id` is what benchmark labels are scored against,
so a section label that does not match what a human would write when labelling
silently breaks recall for that item.

Heading formats across the 46-document corpus, measured rather than assumed:

    Article (N)             60.2%   'Article (1)'
    prose heading           22.2%   'Definitions', 'General Provisions'
    Chapter/Part/Section     6.2%   'Chapter Two: Electronic Insurance Strategy'
    N. title                 5.0%   '1. Definitions'
    Article N                2.9%   'Article 2 Scope of Application'
    Annex/Appendix           2.6%   'Appendix (1)'
    N.N                      0.9%   '3.1 The Board'
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from regulens.retrieval.base import Chunk

HEADING_SELECTOR = "h2.page-title"
BODY_SELECTOR = "div.field--name-body"

# Text of the first section of any document. The Rulebook puts the instrument's
# preamble - its code, effective date and the "Having perused..." recitals -
# under the document title rather than under a numbered heading.
PREAMBLE_LABEL = "Preamble"


@dataclass(frozen=True)
class ParsedDocument:
    """One instrument, split into citable sections."""

    doc_id: str
    title: str
    sections: list[Chunk]
    warnings: list[str]


def _clean(text: str) -> str:
    """Normalise whitespace and unicode without altering the wording.

    The Rulebook uses non-breaking spaces and typographic quotes throughout.
    Left in place they make section labels compare unequal to the same label
    typed by hand into the benchmark, which would fail an evidence match for
    reasons that have nothing to do with retrieval.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def section_label(heading: str) -> str:
    """Reduce a heading to the identifier a person would cite it by.

    'Article (3): Effective Risk Management System' -> 'Article 3'
    'Article 2 Scope of Application'                -> 'Article 2'
    '3.1 The Board'                                 -> '3.1'
    '1. Definitions'                                -> '1'
    'Chapter Two: Electronic Insurance Strategy'    -> 'Chapter Two'
    'Appendix (1)'                                  -> 'Appendix 1'
    'Definitions'                                   -> 'Definitions'

    Headings carrying no printed identifier keep their full text, because that
    is what a labeller has available to cite. The complete heading is always
    preserved in chunk metadata as `section_title`, so nothing is lost.
    """
    text = _clean(heading)

    match = re.match(r"^Article\s*\(?\s*(\d+)\s*\)?", text, re.I)
    if match:
        return f"Article {int(match.group(1))}"

    # 'No.' is optional and must be consumed: without it the [A-Z] branch
    # matches the N of 'Schedule No. (1)' and every schedule collapses to
    # 'Schedule N'.
    match = re.match(
        r"^(Appendix|Annex|Schedule)\s*(?:No\.?)?\s*\(?\s*([0-9]+|[A-Z])\s*\)?",
        text,
        re.I,
    )
    if match:
        return f"{match.group(1).title()} {match.group(2)}"

    match = re.match(r"^(Chapter|Part|Section)\s*\(?\s*([A-Za-z]+|\d+)\s*\)?", text, re.I)
    if match:
        return f"{match.group(1).title()} {match.group(2).title()}"

    # Dotted numbering: '6.1.6 Something' -> '6.1.6'
    match = re.match(r"^(\d+(?:\.\d+)+)", text)
    if match:
        return match.group(1)

    # Flat numbering: '1. Definitions' -> '1'
    match = re.match(r"^(\d+)\s*[.)]\s+\S", text)
    if match:
        return match.group(1)

    return text


CONTAINER_RE = re.compile(r"^(Chapter|Part|Section)\b", re.I)


def _is_container(heading: str) -> bool:
    """True for headings that group the sections after them.

    Only Chapter/Part/Section qualify. Annex and Appendix are excluded on
    purpose: they hold substantive text and are cited as evidence in their own
    right, not as context for what follows.
    """
    return bool(CONTAINER_RE.match(heading))


def _body_for(heading: Tag) -> Tag | None:
    """The body block belonging to this heading, or None if it has no text.

    Guards against borrowing the next section's body. A heading with no body of
    its own - the Rulebook has a few, used purely as group labels - would
    otherwise silently absorb the following section's text and attach it to the
    wrong citation.
    """
    body = heading.find_next("div", class_="field--name-body")
    if body is None:
        return None
    if body.find_previous("h2", class_="page-title") is not heading:
        return None
    return body


def parse_html(html: str, doc_id: str) -> ParsedDocument:
    """Split one instrument's HTML into section-level chunks."""
    soup = BeautifulSoup(html, "lxml")
    headings = soup.select(HEADING_SELECTOR)
    warnings: list[str] = []

    if not headings:
        return ParsedDocument(doc_id, "", [], [f"{doc_id}: no {HEADING_SELECTOR} elements"])

    doc_title = _clean(headings[0].get_text(" ", strip=True))

    sections: list[Chunk] = []
    seen_labels: dict[str, int] = {}
    pending_title = ""
    container = ""

    for order, heading in enumerate(headings):
        heading_text = _clean(heading.get_text(" ", strip=True))
        body = _body_for(heading)
        text = _clean(body.get_text("\n", strip=True)) if body is not None else ""

        if not text:
            # A heading with no body of its own is not an empty section - it is
            # part of how the Rulebook titles things. Several instruments print
            # the descriptive title and the article number as consecutive
            # headings:
            #
            #     h2 'Definitions'   (no body)
            #     h2 'Article (1)'   (the definitions text)
            #
            # Dropping the first would throw away the topical words most likely
            # to match a query - 'Grievance', 'Penalties', 'Definitions' - and
            # leave the section titled only by its number.
            #
            # Structural headings (Chapter, Part, Annex) behave differently:
            # they govern every section until the next one, not just the next
            # section, so they are carried as running context instead.
            if _is_container(heading_text):
                container = heading_text
                pending_title = ""
            else:
                pending_title = heading_text
            continue

        label = PREAMBLE_LABEL if order == 0 else section_label(heading_text)

        # Qualify by the enclosing Chapter/Part/Section when there is one.
        #
        # Compound instruments restart their article numbering in each part.
        # INS-FIN-001 runs Article (1) to Article (11) under 'Section 1', then
        # begins again at Article (1) under 'Section (2)'. Bare 'Article 3'
        # names two different provisions there, so it cannot be an evidence id,
        # and a numeric suffix like 'Article 3 (2)' would be an invention of
        # this parser rather than something a labeller could read off the page.
        # 'Section 1, Article 3' is how the document addresses itself.
        if container and label != PREAMBLE_LABEL:
            label = f"{section_label(container)}, {label}"

        # Anything still colliding is a genuine ambiguity in the source. Keep it
        # distinguishable so the benchmark can reference both, and say so.
        count = seen_labels.get(label, 0) + 1
        seen_labels[label] = count
        if count > 1:
            warnings.append(
                f"{doc_id}: duplicate section label {label!r}, "
                f"stored as {label} ({count})"
            )
            label = f"{label} ({count})"

        if order == 0:
            title = doc_title
        elif pending_title:
            title = pending_title
        else:
            title = heading_text
        pending_title = ""

        sections.append(
            Chunk(
                chunk_id=f"{doc_id}::{label}",
                doc_id=doc_id,
                section=label,
                text=text,
                metadata={
                    "section_title": title,
                    "section_heading": heading_text,
                    "parent_heading": container,
                    "doc_title": doc_title,
                    "order": order,
                    "chars": len(text),
                },
            )
        )

    if not sections:
        warnings.append(f"{doc_id}: parsed to zero sections")

    return ParsedDocument(doc_id, doc_title, sections, warnings)


def parse_document(path: Path, doc_id: str) -> list[Chunk]:
    """Extract section-labelled chunks from one downloaded document."""
    return parse_html(path.read_text(encoding="utf-8"), doc_id).sections
