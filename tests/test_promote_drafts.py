"""Tests for the gate between drafted and benchmark questions.

The gate is the only mechanical guarantee that ground truth was checked by a
person. If it can be passed by an item nobody read, the project's one
substantive claim is unsupported and every measured number inherits that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "promote_drafts", REPO_ROOT / "scripts" / "promote_drafts.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def promote():
    return load_module()


def draft(**overrides):
    item = {
        "id": "D001",
        "question": "Who must approve a deviation from the risk appetite?",
        "category": "single_hop",
        "difficulty": "easy",
        "required_evidence": [{"doc_id": "INS-GOV-003", "section": "Article 3"}],
        "provenance": {
            "source": "llm_drafted_human_verified",
            "labelled_on": "2026-08-25",
            "minutes_to_label": 0,
        },
    }
    item.update(overrides)
    return item


def verified(**overrides):
    item = draft(**overrides)
    item["provenance"] = {**item["provenance"], "minutes_to_label": 7, "confidence": "high"}
    return item


def test_an_unverified_draft_is_blocked(promote):
    reasons = promote.blocking_reasons(draft())
    assert any("not yet verified" in r for r in reasons)
    assert any("confidence" in r for r in reasons)


def test_recording_time_alone_is_not_enough(promote):
    item = draft()
    item["provenance"]["minutes_to_label"] = 7
    reasons = promote.blocking_reasons(item)
    assert reasons == ["provenance.confidence is unset"]


def test_a_verified_draft_passes(promote):
    assert promote.blocking_reasons(verified()) == []


def test_low_confidence_still_passes(promote):
    """Low confidence is an honest answer, not a failed check."""
    item = verified()
    item["provenance"]["confidence"] = "low"
    assert promote.blocking_reasons(item) == []


def test_nonsense_confidence_is_rejected(promote):
    item = verified()
    item["provenance"]["confidence"] = "pretty sure"
    assert promote.blocking_reasons(item)


@pytest.mark.parametrize("minutes", [0, -5, None, "seven"])
def test_missing_or_impossible_labelling_time_is_rejected(promote, minutes):
    item = verified()
    item["provenance"]["minutes_to_label"] = minutes
    assert any("minutes_to_label" in r for r in promote.blocking_reasons(item))


def test_unanswerable_item_with_evidence_is_rejected(promote):
    item = verified(category="unanswerable")
    assert any("empty required_evidence" in r for r in promote.blocking_reasons(item))


def test_unanswerable_item_without_evidence_passes(promote):
    item = verified(category="unanswerable", required_evidence=[])
    assert promote.blocking_reasons(item) == []


def test_answerable_item_without_evidence_is_rejected(promote):
    item = verified(required_evidence=[])
    assert any("no required_evidence" in r for r in promote.blocking_reasons(item))


def test_ids_continue_from_the_existing_benchmark(promote):
    assert promote.next_question_number([]) == 1
    assert promote.next_question_number([{"id": "Q001"}, {"id": "Q017"}]) == 18
    # A retired id must not be handed out again.
    assert promote.next_question_number([{"id": "Q005"}, {"id": "Q003"}]) == 6


def test_no_unverified_draft_in_the_repo_can_promote(promote):
    """The invariant, checked against the real drafts file.

    An earlier version of this asserted that *every* draft was blocked, which
    was true only until the first one was verified. That is a snapshot, not an
    invariant, and it fails the moment the workflow is used as intended. What
    must always hold is narrower: a draft promotes if and only if a human
    recorded both how long verification took and how confident they are.
    """
    drafts = promote.read_jsonl(REPO_ROOT / "benchmark" / "drafts.jsonl")
    assert drafts, "drafts.jsonl is empty"
    for item in drafts:
        prov = item.get("provenance", {})
        minutes = prov.get("minutes_to_label")
        human_checked = (
            isinstance(minutes, (int, float))
            and minutes > 0
            and prov.get("confidence") in promote.VALID_CONFIDENCE
        )
        blocked = bool(promote.blocking_reasons(item))
        assert blocked != human_checked, (
            f"{item['id']}: human_checked={human_checked} but blocked={blocked}"
        )
