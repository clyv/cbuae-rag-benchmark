"""Tests for in-force checking.

The distinction that matters most is between "not yet law" and "we cannot say".
Collapsing the two either suppresses four citable instruments or asserts
something the Rulebook does not print, so it is pinned in both directions.
"""

from __future__ import annotations

from datetime import date

from regulens.evaluation.temporal import (
    exposure,
    in_force_on,
    not_yet_in_force,
)

TODAY = date(2026, 9, 11)
COMMENCEMENTS = {
    "INS-GOV-003": date(2022, 12, 30),
    "INS-TAK-001": date(2026, 9, 14),   # commences in three days
    "INS-TAK-006": date(2027, 7, 15),   # commences in ten months
    "INS-GOV-008": None,                # publishes no date at all
}


def test_an_instrument_that_has_commenced_is_in_force():
    assert in_force_on("INS-GOV-003", TODAY, COMMENCEMENTS) is True


def test_an_instrument_commencing_later_is_not_in_force():
    assert in_force_on("INS-TAK-001", TODAY, COMMENCEMENTS) is False
    assert in_force_on("INS-TAK-006", TODAY, COMMENCEMENTS) is False


def test_commencing_today_counts_as_in_force():
    """A provision commencing on the date asked about is law that day."""
    assert in_force_on("INS-TAK-001", date(2026, 9, 14), COMMENCEMENTS) is True


def test_a_missing_date_is_unknown_not_false():
    """Four instruments publish no date. Reading that as "not in force" would
    suppress four perfectly citable documents."""
    assert in_force_on("INS-GOV-008", TODAY, COMMENCEMENTS) is None


def test_an_unregistered_document_is_unknown_not_false():
    assert in_force_on("INS-XXX-999", TODAY, COMMENCEMENTS) is None


def test_the_answer_changes_with_the_date_asked_about():
    """The same citation is premature today and sound next year - which is the
    whole reason the check takes a date rather than reading the clock."""
    assert in_force_on("INS-TAK-006", TODAY, COMMENCEMENTS) is False
    assert in_force_on("INS-TAK-006", date(2027, 8, 1), COMMENCEMENTS) is True


# --- flagging a result list -------------------------------------------------


def test_only_the_premature_sections_are_flagged():
    retrieved = ["INS-GOV-003::Article 3", "INS-TAK-006::Article 1", "INS-GOV-008::Article 2"]
    assert not_yet_in_force(retrieved, TODAY, COMMENCEMENTS) == ["INS-TAK-006::Article 1"]


def test_unknown_dates_are_not_flagged_as_premature():
    """This is the list of things known to be premature, not the list of things
    not known to be current."""
    retrieved = ["INS-GOV-008::Article 2"]
    assert not_yet_in_force(retrieved, TODAY, COMMENCEMENTS) == []


def test_exposure_records_where_the_first_premature_hit_ranked():
    """A premature citation at rank 1 and one at rank 9 are not the same
    hazard, so the rank is reported rather than just a count."""
    retrieved = ["INS-GOV-003::Article 3", "INS-TAK-001::Article 1", "INS-TAK-006::Article 1"]
    result = exposure(retrieved, TODAY, COMMENCEMENTS)
    assert result["premature_count"] == 2
    assert result["first_premature_rank"] == 2
    assert result["clean"] is False


def test_a_clean_result_list_reports_no_rank():
    result = exposure(["INS-GOV-003::Article 3"], TODAY, COMMENCEMENTS)
    assert result["clean"] is True
    assert result["first_premature_rank"] == 0
    assert result["premature"] == []


def test_unknown_dated_sections_are_reported_separately():
    result = exposure(["INS-GOV-008::Article 2"], TODAY, COMMENCEMENTS)
    assert result["clean"] is True
    assert result["unknown_date"] == ["INS-GOV-008::Article 2"]
