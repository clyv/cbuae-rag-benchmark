"""Was the provision this answer cites actually in force?

Every metric in this project is timeless. Recall asks whether the right section
was found; citation validity asks whether the words are really there. Neither
asks the question a compliance officer asks first: **is this the law today?**

That is not hypothetical here. Four instruments in the corpus are listed by the
Rulebook as In-Force while carrying a commencement date in the future - one on
2026-09-14 and three on 2027-07-15. They are indexed deliberately, as near-miss
distractors, and barred from the answer key. But nothing stops a retriever
returning them, and measurement shows it does: the shipped system surfaces a
not-yet-commenced section for 7 of 100 questions, twice at rank 1.

A reader gets a confident citation to an instrument that is not yet law, with
nothing on the page saying so.

## Unknown is not the same as future

Four other instruments publish no date at all. Treating a missing date as "not
in force" would suppress four perfectly citable documents; treating it as "in
force" would assert something the source does not say. `in_force_on` therefore
returns `None` for them, and callers decide - the API flags them as unknown
rather than either hiding or blessing them.

## What this does not do

It reads the commencement date the Rulebook prints. It does not interpret
transition provisions, grandfathering, or partial commencement, and it cannot
tell that an article of an in-force instrument was itself amended later. Which
instrument governs a given obligation on a given day is a legal judgement; this
is the arithmetic underneath it, and the distinction is the same one the corpus
notes already make.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

UNKNOWN = None


def load_commencements(registry: Path) -> dict[str, date | None]:
    """Each instrument's commencement date, or None where none is published."""
    out: dict[str, date | None] = {}
    with registry.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("commencement_date") or row.get("effective_date") or "").strip()
            out[row["doc_id"]] = date.fromisoformat(raw) if raw else UNKNOWN
    return out


def in_force_on(
    doc_id: str, as_of: date, commencements: dict[str, date | None]
) -> bool | None:
    """Whether an instrument had commenced by `as_of`.

    Returns None when the instrument publishes no date, or is not in the
    registry at all - both are "cannot say", and a caller that needs a decision
    has to make it explicitly rather than inherit one from a default.
    """
    if doc_id not in commencements:
        return UNKNOWN
    commenced = commencements[doc_id]
    if commenced is UNKNOWN:
        return UNKNOWN
    return commenced <= as_of


def not_yet_in_force(
    evidence_ids: list[str], as_of: date, commencements: dict[str, date | None]
) -> list[str]:
    """The cited sections whose instrument had not commenced by `as_of`.

    Unknown-date instruments are not included: this is the list of things known
    to be premature, not the list of things not known to be current.
    """
    flagged = []
    for evidence_id in evidence_ids:
        doc_id = evidence_id.partition("::")[0]
        if in_force_on(doc_id, as_of, commencements) is False:
            flagged.append(evidence_id)
    return flagged


def exposure(
    retrieved: list[str], as_of: date, commencements: dict[str, date | None]
) -> dict[str, object]:
    """Temporal exposure of one result list.

    `rank` is the position of the first premature section, 1-based, because a
    premature citation at rank 1 and one at rank 9 are not the same hazard.
    """
    flagged = not_yet_in_force(retrieved, as_of, commencements)
    rank = next(
        (i for i, e in enumerate(retrieved, start=1) if e in set(flagged)),
        0,
    )
    unknown = [
        e for e in retrieved
        if in_force_on(e.partition("::")[0], as_of, commencements) is UNKNOWN
    ]
    return {
        "premature": flagged,
        "premature_count": len(flagged),
        "first_premature_rank": rank,
        "unknown_date": unknown,
        "clean": not flagged,
    }
