"""Tests for obligation strength.

Every number in `results/obligation.md` rests on these rules. Reading "may not"
as permission would invert a prohibition, which is the single most damaging
mistake this module could make, so the negated forms are pinned first and
individually.
"""

from __future__ import annotations

from regulens.evaluation.obligation import (
    ADVISORY,
    MANDATORY,
    NONE,
    PERMISSIVE,
    PROHIBITIVE,
    drift,
    forces,
    score_claims,
    strongest,
)


# --- negation, which must be matched before anything else ------------------


def test_may_not_is_a_prohibition_not_a_permission():
    """"may not" contains "may". Matching the positive form first would read a
    prohibition as its own opposite."""
    assert strongest("The head of control may not underwrite.") == PROHIBITIVE


def test_shall_not_is_a_prohibition_not_an_obligation():
    assert strongest("The Board shall not delegate this responsibility.") == PROHIBITIVE


def test_must_not_is_a_prohibition():
    assert strongest("A Company must not commence before registration.") == PROHIBITIVE


def test_a_prohibition_does_not_also_register_as_mandatory():
    assert forces("The Company shall not invest in such assets.") == {PROHIBITIVE}


# --- the four forces --------------------------------------------------------


def test_shall_and_must_are_mandatory():
    assert strongest("An insurer shall maintain a register.") == MANDATORY
    assert strongest("An insurer must maintain a register.") == MANDATORY


def test_may_is_permissive():
    assert strongest("An insurer may outsource the function.") == PERMISSIVE


def test_should_is_advisory():
    assert strongest("An insurer should review it annually.") == ADVISORY


def test_text_with_no_obligation_carries_none():
    assert strongest("This Regulation was published in the Official Gazette.") == NONE


def test_a_section_can_carry_several_forces():
    """An obligation plus an exception to it is the normal shape of a provision."""
    text = "The Company shall appoint an actuary, but may outsource the valuation."
    assert forces(text) == {MANDATORY, PERMISSIVE}


def test_the_strongest_force_wins_for_a_single_label():
    assert strongest("The Company shall appoint an actuary, but may outsource it.") == MANDATORY


# --- drift ------------------------------------------------------------------


def test_a_claim_matching_the_source_is_preserved():
    assert drift("The insurer must appoint an actuary.",
                 "The Company shall appoint an actuary.") == "preserved"


def test_reporting_a_permission_as_an_obligation_is_strengthening():
    assert drift("The insurer must outsource the valuation.",
                 "The Company may outsource the valuation.") == "strengthened"


def test_reporting_an_obligation_as_a_permission_is_weakening():
    """The failure that ends in an enforcement action: a firm told it may skip
    something it must do."""
    assert drift("The insurer may appoint an actuary.",
                 "The Company shall appoint an actuary.") == "weakened"


def test_a_claim_may_match_any_force_the_source_carries_not_only_the_strongest():
    """A section that mandates one thing and permits another supports a claim
    about either. Comparing against the strongest force alone would score the
    permissive half as a weakening."""
    source = "The Company shall appoint an actuary, but may outsource the valuation."
    assert drift("The insurer may outsource the valuation.", source) == "preserved"


def test_a_claim_with_no_obligation_is_counted_apart():
    assert drift("The actuary is appointed annually.",
                 "The Company shall appoint an actuary.") == "no_force"


def test_advisory_reported_as_mandatory_is_strengthening():
    assert drift("The insurer must review it annually.",
                 "The insurer should review it annually.") == "strengthened"


# --- aggregation ------------------------------------------------------------


def test_fidelity_counts_only_force_bearing_claims():
    """A metric that rewards saying nothing is not measuring faithfulness, so
    claims stating no obligation are excluded rather than counted as correct."""
    scores = score_claims([
        ("The insurer must appoint an actuary.", "The Company shall appoint an actuary."),
        ("The actuary is appointed annually.", "The Company shall appoint an actuary."),
    ])
    assert scores["claims"] == 2
    assert scores["force_bearing"] == 1
    assert scores["obligation_fidelity"] == 1.0
    assert scores["no_force"] == 1


def test_fidelity_falls_when_a_claim_inverts_the_source():
    scores = score_claims([
        ("The insurer must appoint an actuary.", "The Company shall appoint an actuary."),
        ("The insurer may appoint an actuary.", "The Company shall appoint an actuary."),
    ])
    assert scores["obligation_fidelity"] == 0.5
    assert scores["weakened"] == 1


def test_an_extractive_quote_cannot_drift():
    """The answerer that ships quotes its source, so the claim is a substring of
    it and the force is whatever the source said. This is the baseline the
    generative number is measured against."""
    source = "The Company shall appoint an actuary, but may outsource the valuation."
    assert score_claims([(source, source)])["obligation_fidelity"] == 1.0


def test_no_claims_is_not_a_failure():
    assert score_claims([])["obligation_fidelity"] == 1.0
