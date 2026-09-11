"""What every system sees when it indexes a chunk.

Shared deliberately. If BM25 indexed the section heading and the dense system
did not, the comparison would be measuring two different corpora and any
difference between them would be uninterpretable. One definition, used by all
four systems, is the only way the results table means anything.
"""

from __future__ import annotations

import re

from regulens.retrieval.base import Chunk

# Tokenisation for lexical retrieval.
#
# Regulatory text is full of identifiers - "Article 5", "Article 5(2)",
# "C 25/2022", "AED 250,000,000" - and how they are split decides what BM25 can
# match. Splitting on any non-alphanumeric run means "Article 5(2)" becomes
# ["article", "5", "2"], so a query for Article 5 matches a mention of Article
# 5(2). That is the behaviour we want: sub-clause references should still hit
# the article. The cost is that "5" and "2" are separately matchable and
# extremely common, which BM25's inverse document frequency already discounts
# to near nothing.
#
# The alternative - keeping "5(2)" as one token - would make the two references
# unmatchable and is worse for a corpus where questions cite articles loosely.
TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def indexable_text(chunk: Chunk, include_doc_title: bool = False) -> str:
    """Heading plus body, and optionally the instrument's own title.

    ## Why the document title is a switch rather than always on

    This corpus contains matched instruments: a conventional regulation and its
    Takaful counterpart, a Regulation and its Standards. Their articles carry the
    same numbers, the same headings, and near-identical bodies. The only text
    that separates `INS-FIN-001::Section 2, Article 1` from
    `INS-FIN-002::Section 2, Article 1` is the word *Takaful*, and it appears in
    the document title alone - which `section_title` equals for only 44 of 763
    sections, so for the rest it is invisible to every retriever.

    `results/failures.md` measured what that costs: 15% of all missed evidence is
    the right provision retrieved from the wrong instrument.

    It is a switch because adding it is not free. Every chunk gains a dozen words
    of formal boilerplate - "Insurance Authority Board Decision Number (25) of
    2014 Pertinent to..." - which dilutes the body's own vocabulary in a dense
    embedding and adds terms to the lexical index. Whether the disambiguation is
    worth the dilution is an empirical question, so both settings are measured
    rather than one being assumed.

    The section heading carries the topical words a query is most likely to
    share - 'Grievance', 'Outsourcing', 'Actuarial Function' - and several
    sections in this corpus are titled by a heading that appears nowhere in
    their body, because the Rulebook prints the descriptive title and the
    article number as separate headings. Indexing the body alone would make
    those sections unreachable by their own subject.

    This is not leakage: the heading is part of the published document and is
    visible to any reader. It is included for every system equally.
    """
    title = chunk.metadata.get("section_title", "")
    heading = chunk.metadata.get("section_heading", "")
    doc_title = chunk.metadata.get("doc_title", "") if include_doc_title else ""
    # Not repeated when the section already carries it as its own title, which
    # happens on a document's opening section.
    if doc_title and doc_title in (title, heading):
        doc_title = ""
    parts = [p for p in (doc_title, title, heading, chunk.text) if p]
    return "\n".join(parts)
