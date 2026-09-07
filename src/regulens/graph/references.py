"""Extract the cross-references regulation makes to itself.

Phase 6. Regulatory text points at other provisions constantly - "as directed in
Article (3)", "stipulated in Article (10) of Chapter 1 of the Financial
Regulations". Those pointers are a graph the retriever cannot see: embeddings and
BM25 both score a passage on its own words, so a section that says "the limits in
Article (3) apply" scores poorly for a question about limits even though it names
exactly where the answer is.

This module builds that graph. What it does *not* do is assume the graph is
useful - `scripts/run_graph_eval.py` measures whether following the edges finds
evidence that retrieval missed, and reports the answer either way.

## What counts as a reference

Only `Article (N)` and `Clause (N)`. Deliberately not `Section (N)`: in this
corpus a Section is a group of articles, so a Section reference points at a dozen
provisions at once, and - worse - every Preamble lists its document's sections as
a table of contents. Treating those listings as references would make each
preamble a hub connected to everything, which would look like a rich graph and
mean nothing.

## How a reference is resolved

A bare `Article (3)` means article 3 *of the citing document*, and in the
compound instruments it means article 3 of the citing document's own Section or
Chapter - numbering restarts inside them, so "Article 3" cited from
`Section 1, Article 2` resolves to `Section 1, Article 3`, not to some other
section's third article.

Every resolution is then checked against the corpus: an edge exists only if the
section it points at is real. That makes the resolver self-validating - a rule
that guesses wrong produces no edge rather than a wrong one - and it is why the
build report counts unresolved references instead of hiding them.

References to instruments outside the corpus (the Central Bank Law, Federal
decree-laws, Cabinet resolutions not in the registry) are recognised and dropped,
because there is nothing to point at. They are counted separately so the report
distinguishes "we could not resolve this" from "this leaves the corpus".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Article (3)", "Article 3", "Articles (8)", "Clause (2)". The trailing group
# allows sub-numbering like Article (8.5/b), whose sub-part is discarded: the
# corpus is indexed at article granularity, so 8.5 and 8.6 are the same target.
#
# "Sub-Article (11) of Article (13)" is excluded by the lookbehind. A sub-article
# is a part of an article, not a reference to one, and matching it takes the
# wrong number - the target there is article 13, and 11 is a paragraph inside it.
REFERENCE_RE = re.compile(
    r"(?<!sub-)(?<!sub )\b(?:Article|Clause)s?\s*\(?(\d{1,3})(?:[.\-/][\w.]+)?\)?", re.I
)

# Text right after the number that says the citing instrument is meant. Both
# halves matter: "of this Regulation" and "of the Regulations herein" are the
# same statement, and the corpus uses the second form as often as the first.
_INSTRUMENT_WORD = (
    r"(?:Regulation|Regulations|Standard|Standards|Instruction|Instructions"
    r"|Decision|Resolution|Law|Section|Chapter|Article)"
)
SAME_INSTRUMENT_RE = re.compile(
    r"^\s*(?:above|below|herein|hereof)?\s*(?:of|in|to)?\s*"
    rf"(?:(?:this|these|the\s+present)\s+{_INSTRUMENT_WORD}"
    rf"|the\s+{_INSTRUMENT_WORD}\s+herein)",
    re.I,
)
SELF_RE = re.compile(r"^\s*(?:of\s+)?this\s+Article", re.I)

# "of the Standards" cited from a Regulation means that Regulation's own paired
# Standards, and the other way round. The Rulebook issues them in pairs under
# one name, so the pairing is read off the registry titles rather than listed
# here - see `companion_documents`.
COMPANION_RE = re.compile(r"^\s*of\s+the\s+(Standards?|Regulations?)\b", re.I)

# A number list or range continuing the reference: "(3), (4) and (5)",
# "(8) to (13)". Without this a reference to a run of articles produces one edge
# and drops the rest. The parentheses are required, not optional: "Article (5)
# and 3 years" would otherwise read "3" as a second article.
CONTINUATION_RE = re.compile(r"\s*(,|and|to|through|&)\s*\((\d{1,3})\)", re.I)
MAX_RANGE = 20

# "Article (10) of Chapter 1", "Article (8) of Chapter II". The compound
# instruments call their divisions Sections while the text citing them says
# Chapter, so both words are accepted and only the number is kept.
QUALIFIER_RE = re.compile(r"^\s*of\s+(?:Chapter|Section|Part)\s+\(?([IVXLC]+|\d{1,2})\)?", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}
QUALIFIED_LABEL_RE = re.compile(
    r"^(?:Section|Chapter|Part)\s+(?P<division>\d{1,2}),\s*Article\s+(?P<number>\d+)\s*$", re.I
)

# Instruments that exist outside this corpus. A reference to one is not a failure
# to resolve, it is a pointer out of the collection, and the two are different.
EXTERNAL_RE = re.compile(
    r"^\s*of\s+(?:the\s+)?(?:Central\s+Bank\s+Law|Federal\s+Law|Federal\s+Decree"
    r"|Decretal\s+Federal|Cabinet\s+Resolution|Law\s+No|Executive\s+Regulations?"
    r"|Implementing\s+Regulations?|Commercial\s+Companies)",
    re.I,
)

# Names the corpus uses for its own instruments. Kept explicit rather than matched
# against registry titles: the titles are long formal strings ("Insurance
# Authority Board Decision Number (25) of 2014 Pertinent to Financial
# Regulations...") and fuzzy-matching one against a three-word mention produces
# confident nonsense. This is a small enough set to be honest about by hand, and
# the build report says how many references were left unresolved.
#
# "the Financial Regulations" is genuinely ambiguous - INS-FIN-001 is the
# conventional instrument and INS-FIN-002 its Takaful counterpart - so it
# resolves to whichever matches the citing document's own kind.
ALIASES: dict[str, str] = {
    "financial regulations": "INS-FIN-001",
    "risk management and internal controls regulation": "INS-GOV-003",
    "risk management and internal controls standards": "INS-GOV-004",
    "corporate governance regulation": "INS-GOV-001",
    "corporate governance standards": "INS-GOV-002",
    "insurance group supervision regulation": "INS-OTH-003",
    "climate-related financial risk management regulation": "INS-GOV-007",
    "regulation regarding takaful insurance": "INS-TAK-001",
    "takaful insurance regulation": "INS-TAK-001",
}

# Takaful instruments citing a shared name mean the Takaful counterpart.
TAKAFUL_COUNTERPART = {"INS-FIN-001": "INS-FIN-002"}

ARTICLE_LABEL_RE = re.compile(r"^(?P<prefix>.*?,\s*)?Article\s+(?P<number>\d+)\s*$", re.I)


@dataclass(frozen=True)
class Reference:
    """One resolved pointer from a section to another section."""

    source: str  # "DOC::Section"
    target: str  # "DOC::Section"
    number: int
    phrase: str  # the words that produced it, for auditing

    @property
    def cross_document(self) -> bool:
        return self.source.split("::")[0] != self.target.split("::")[0]


def target_label(citing_section: str, number: int) -> str | None:
    """The label a bare `Article (number)` means, cited from `citing_section`.

    Numbering restarts inside compound instruments, so the citing section's own
    qualifier carries over: from `Section 1, Article 2`, "Article 3" is
    `Section 1, Article 3`. Returns None when the citing section is not an
    article at all - a Preamble or a Schedule has no numbering context to
    inherit, and guessing one would invent edges.
    """
    match = ARTICLE_LABEL_RE.match(citing_section.strip())
    if not match:
        return None
    prefix = match.group("prefix") or ""
    return f"{prefix}Article {number}"


def document_roles(sections: list[dict]) -> dict[str, str]:
    """Whether each document calls itself a Regulation or a Standard.

    Needed because "of the Standards" means something different depending on who
    says it: from a Regulation it points at the paired Standards, but from
    inside the Standards it means the citing document itself.
    """
    roles: dict[str, str] = {}
    for section in sections:
        title = section["metadata"].get("doc_title", "").lower()
        if "standard" in title:
            roles[section["doc_id"]] = "standards"
        elif "regulation" in title:
            roles[section["doc_id"]] = "regulation"
    return roles


def companion_documents(sections: list[dict]) -> dict[str, str]:
    """Pair each Regulation with its own Standards, by title.

    The Rulebook issues these as matched instruments under one name - "Risk
    Management and Internal Controls Regulation for Insurance Companies" and
    "... Standards for Insurance Companies" - and each cites the other as simply
    "the Standards" or "the Regulation". Reading the pairing off the titles keeps
    it a fact about the corpus rather than a list to maintain by hand.
    """
    roles = document_roles(sections)
    titles = {s["doc_id"]: s["metadata"].get("doc_title", "").lower() for s in sections}
    by_stem: dict[str, dict[str, str]] = {}
    for doc_id, role in roles.items():
        stem = titles[doc_id].replace("standards", "@").replace("standard", "@")
        stem = stem.replace("regulations", "@").replace("regulation", "@")
        by_stem.setdefault(stem, {})[role] = doc_id

    companions: dict[str, str] = {}
    for pair in by_stem.values():
        if len(pair) == 2:
            companions[pair["regulation"]] = pair["standards"]
            companions[pair["standards"]] = pair["regulation"]
    return companions


def _named_role(word: str) -> str:
    return "standards" if word.lower().startswith("standard") else "regulation"


def _kind(doc_id: str) -> str:
    return "takaful" if "TAK" in doc_id or doc_id == "INS-FIN-002" else "conventional"


def _numbers(text: str, first: int, position: int) -> tuple[list[int], int]:
    """Every article number in one reference, and where the reference ends.

    "Articles (8) to (13)" is thirteen minus eight plus one pointers, not one.
    """
    numbers = [first]
    cursor = position
    while match := CONTINUATION_RE.match(text, cursor):
        connector, value = match.group(1).lower(), int(match.group(2))
        if connector in {"to", "through"} and 0 < value - numbers[-1] <= MAX_RANGE:
            numbers.extend(range(numbers[-1] + 1, value + 1))
        elif value not in numbers:
            numbers.append(value)
        cursor = match.end()
    return numbers, cursor


def _division(tail: str) -> int | None:
    """The Chapter or Section number a reference names, if it names one."""
    match = QUALIFIER_RE.match(tail)
    if not match:
        return None
    raw = match.group(1)
    return int(raw) if raw.isdigit() else ROMAN.get(raw.lower())


def resolve_label(
    number: int,
    labels: set[str],
    citing_section: str | None,
    division: int | None,
) -> str | None:
    """Which section of the target document `Article number` means.

    Three rules, in order, and none of them guesses:

    1. An explicit qualifier in the reference wins - "Article (10) of Chapter 1".
    2. Otherwise the citing section's own qualifier carries over, because
       numbering restarts inside the compound instruments.
    3. Otherwise, if exactly one section in the document is that article number,
       it is that one. This is what catches the instruments that number their
       articles continuously across chapters, where rule 2 builds a label that
       does not exist. More than one match is ambiguous and resolves to nothing.
    """
    if division is not None:
        for label in sorted(labels):
            match = QUALIFIED_LABEL_RE.match(label)
            if match and int(match.group("division")) == division:
                if int(match.group("number")) == number:
                    return label

    if citing_section is not None:
        inherited = target_label(citing_section, number)
        if inherited and inherited in labels:
            return inherited

    matches = []
    for label in labels:
        match = ARTICLE_LABEL_RE.match(label)
        if match and int(match.group("number")) == number:
            matches.append(label)
    return matches[0] if len(matches) == 1 else None


def _resolve_alias(tail: str, citing_doc: str) -> str | None:
    lowered = tail.lower()
    for name, doc_id in ALIASES.items():
        if re.match(rf"^\s*of\s+(?:the\s+|these\s+)?{re.escape(name)}", lowered):
            if _kind(citing_doc) == "takaful" and doc_id in TAKAFUL_COUNTERPART:
                return TAKAFUL_COUNTERPART[doc_id]
            return doc_id
    return None


def extract_references(sections: list[dict]) -> tuple[list[Reference], dict[str, int]]:
    """Every resolvable Article/Clause reference in the corpus, plus a census.

    The census is returned rather than logged because the counts are the result:
    a graph is only worth following if the edges exist, and the ratio of resolved
    to dropped says how much of the text's own cross-referencing survives.
    """
    known = {f"{s['doc_id']}::{s['section']}" for s in sections}
    labels_by_doc: dict[str, set[str]] = {}
    for section in sections:
        labels_by_doc.setdefault(section["doc_id"], set()).add(section["section"])

    companions = companion_documents(sections)
    roles = document_roles(sections)

    references: list[Reference] = []
    census = dict.fromkeys(
        [
            "mentions",
            "self",
            "external",
            "unresolved_other_instrument",
            "unresolved_target",
            "resolved_intra",
            "resolved_cross",
        ],
        0,
    )
    seen: set[tuple[str, str]] = set()

    for section in sections:
        source = f"{section['doc_id']}::{section['section']}"
        text = section["text"]
        for match in REFERENCE_RE.finditer(text):
            first = int(match.group(1))
            numbers, end = _numbers(text, first, match.end())
            census["mentions"] += len(numbers)
            tail = text[end : end + 80]
            before = text[max(0, match.start() - 25) : match.start()]

            if SELF_RE.match(tail) or re.search(r"\bthis\s+$", before, re.I):
                census["self"] += len(numbers)
                continue
            if EXTERNAL_RE.match(tail):
                census["external"] += len(numbers)
                continue

            division = _division(tail)
            # A division qualifier sits between the number and the instrument
            # name: "Article (10) of Chapter 1 of the Financial Regulations".
            after_division = tail
            if division is not None:
                qualifier = QUALIFIER_RE.match(tail)
                after_division = tail[qualifier.end() :] if qualifier else tail

            target_doc = section["doc_id"]
            if not SAME_INSTRUMENT_RE.match(after_division):
                alias = _resolve_alias(after_division, section["doc_id"])
                named = COMPANION_RE.match(after_division)
                # "of the Standards" said by the Standards means this document,
                # not its companion - the cross-over only happens when the kind
                # named is not the kind the citing document already is.
                crosses = (
                    named
                    and roles.get(section["doc_id"]) != _named_role(named.group(1))
                    and companions.get(section["doc_id"])
                )
                if alias:
                    target_doc = alias
                elif crosses:
                    target_doc = companions[section["doc_id"]]
                elif named:
                    pass  # the citing instrument, by another name
                elif re.match(r"^\s*of\s+(?:the|these)\s+[A-Z]", after_division):
                    # Names an instrument, and not one this module knows.
                    census["unresolved_other_instrument"] += len(numbers)
                    continue

            labels = labels_by_doc.get(target_doc, set())
            # The citing section's qualifier only carries over inside its own
            # document; across instruments it says nothing about the target.
            citing = section["section"] if target_doc == section["doc_id"] else None

            for number in numbers:
                label = resolve_label(number, labels, citing, division)
                if label is None:
                    census["unresolved_target"] += 1
                    continue

                target = f"{target_doc}::{label}"
                if target not in known:
                    census["unresolved_target"] += 1
                    continue
                if target == source:
                    census["self"] += 1
                    continue

                key = (source, target)
                if key in seen:
                    continue
                seen.add(key)
                phrase = text[max(0, match.start() - 40) : end + 40].replace("\n", " ")
                reference = Reference(
                    source=source, target=target, number=number, phrase=" ".join(phrase.split())
                )
                references.append(reference)
                census["resolved_cross" if reference.cross_document else "resolved_intra"] += 1

    return references, census


def build_adjacency(references: list[Reference]) -> dict[str, list[str]]:
    """Undirected adjacency.

    A section that cites another is related to it in both directions for
    retrieval: the answer may be in either provision, and which one the drafter
    happened to point from is not a fact about where the answer lives.
    """
    adjacency: dict[str, set[str]] = {}
    for reference in references:
        adjacency.setdefault(reference.source, set()).add(reference.target)
        adjacency.setdefault(reference.target, set()).add(reference.source)
    return {node: sorted(neighbours) for node, neighbours in adjacency.items()}
