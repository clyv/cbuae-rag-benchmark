"""Obligation strength, and whether an answer preserves it.

Regulation is not prose with facts in it. Nearly every sentence carries a
*force*: a company **shall** maintain a risk register, **may** outsource the
function, **must not** delegate the Board's responsibility, **should** review it
annually. Those four words are the whole content of a compliance obligation, and
a system that reports one where the text says another has not made a small
wording error - it has told a regulated firm the wrong thing about what is
required of it.

Standard RAG metrics are blind to this. Citation validity asks whether the words
of a claim appear in the cited section, and a claim can score perfectly while
inverting the obligation: "an insurer may appoint an actuary" shares almost all
its vocabulary with "an insurer shall appoint an actuary". Faithfulness scores
computed by an LLM judge inherit the same blindness, and worse, correlate with
human judgement at around 0.55 on published measurements.

So this module measures the thing the domain actually cares about: given a claim
and the section it cites, does the claim keep the source's obligation strength?

## The ordering

Forces are ranked so that "drift" has a direction:

    prohibitive  >  mandatory  >  permissive  >  advisory  >  none

Strengthening (permissive source reported as mandatory) and weakening (mandatory
source reported as permissive) are counted separately, because they are
different failures. Strengthening tells a firm to do something it need not do -
wasteful. Weakening tells a firm it may skip something it must do - which is the
one that ends in an enforcement action.

## Negation is matched first, and that is not a detail

"may not" contains "may"; "shall not" contains "shall". Matching the positive
forms first would read every prohibition as its own opposite - the single most
damaging error this module could make. Prohibitive spans are therefore found and
removed before anything else is matched.
"""

from __future__ import annotations

import re

MANDATORY = "mandatory"
PROHIBITIVE = "prohibitive"
PERMISSIVE = "permissive"
ADVISORY = "advisory"
NONE = "none"

# Strongest first. The index in this list is the force's rank.
ORDER = [PROHIBITIVE, MANDATORY, PERMISSIVE, ADVISORY, NONE]

# Matched first, and removed from the text before anything else is looked for.
PROHIBITIVE_RE = re.compile(
    r"\b(?:shall\s+not|must\s+not|may\s+not|cannot|can\s+not|is\s+not\s+permitted"
    r"|are\s+not\s+permitted|shall\s+refrain|prohibited|forbidden|no\s+\w+\s+shall)\b",
    re.I,
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (MANDATORY, re.compile(
        r"\b(?:shall|must|is\s+required\s+to|are\s+required\s+to|is\s+obliged\s+to"
        r"|required\s+to|obligated\s+to|has\s+to|have\s+to)\b", re.I)),
    (PERMISSIVE, re.compile(
        r"\b(?:may|is\s+permitted|are\s+permitted|is\s+allowed|are\s+allowed"
        r"|is\s+entitled|are\s+entitled|can\b|at\s+its\s+discretion)\b", re.I)),
    (ADVISORY, re.compile(
        r"\b(?:should|ought\s+to|is\s+encouraged|are\s+encouraged|is\s+expected\s+to"
        r"|are\s+expected\s+to|best\s+practice|recommended)\b", re.I)),
]


def forces(text: str) -> set[str]:
    """Every obligation force present in a passage.

    A regulatory section commonly carries several - an obligation plus an
    exception to it - so this returns a set rather than one label.
    """
    found: set[str] = set()
    remainder = text
    if PROHIBITIVE_RE.search(remainder):
        found.add(PROHIBITIVE)
        remainder = PROHIBITIVE_RE.sub(" ", remainder)
    for force, pattern in PATTERNS:
        if pattern.search(remainder):
            found.add(force)
    return found or {NONE}


def strongest(text: str) -> str:
    """The strongest force a passage carries - what it obliges at its highest."""
    present = forces(text)
    for force in ORDER:
        if force in present:
            return force
    return NONE


def drift(claim: str, source: str) -> str:
    """How a claim's obligation strength compares with the section it cites.

    Returns one of:

    `preserved`    the claim asserts a force the source actually carries
    `strengthened` the claim obliges more than the source does
    `weakened`     the claim obliges less than the source does - the dangerous one
    `no_force`     the claim states no obligation at all, so there is none to get
                   wrong; counted apart rather than as a pass
    """
    claim_force = strongest(claim)
    if claim_force == NONE:
        return "no_force"

    # A claim is faithful if the force it states is one the source actually
    # carries, not merely if it matches the source's *strongest* one. A section
    # that mandates one thing and permits another supports either claim.
    if claim_force in forces(source):
        return "preserved"

    source_force = strongest(source)
    return "strengthened" if ORDER.index(claim_force) < ORDER.index(source_force) else "weakened"


def score_claims(pairs: list[tuple[str, str]]) -> dict[str, float]:
    """Aggregate drift over (claim, cited source) pairs.

    `obligation_fidelity` is the share of force-bearing claims that keep a force
    the source carries. Claims stating no obligation are excluded from it rather
    than counted as correct, because a metric that rewards saying nothing is not
    measuring faithfulness.
    """
    tally = {"preserved": 0, "strengthened": 0, "weakened": 0, "no_force": 0}
    for claim, source in pairs:
        tally[drift(claim, source)] += 1

    bearing = tally["preserved"] + tally["strengthened"] + tally["weakened"]
    return {
        **tally,
        "claims": len(pairs),
        "force_bearing": bearing,
        "obligation_fidelity": tally["preserved"] / bearing if bearing else 1.0,
    }
