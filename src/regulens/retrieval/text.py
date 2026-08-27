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


def indexable_text(chunk: Chunk) -> str:
    """Heading plus body.

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
    parts = [p for p in (title, heading, chunk.text) if p]
    return "\n".join(parts)
