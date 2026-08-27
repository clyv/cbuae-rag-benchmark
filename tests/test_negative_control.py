"""Tests for the label-verification control.

If the corruptions are implausible, the experiment measures nothing: a reviewer
would spot obviously-wrong evidence without exercising any judgement, and the
resulting detection rate would overstate how sound the real labels are.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "negative_control", REPO_ROOT / "scripts" / "negative_control.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def nc():
    return load_module()


ORDER = {
    "DOC-A": ["Preamble", "Article 1", "Article 2", "Article 3", "Article 4"],
    "DOC-B": ["Preamble", "Article 1", "Article 2"],
}


def item(evidence, category="cross_section"):
    return {
        "id": "Q001",
        "question": "Does it?",
        "category": category,
        "difficulty": "medium",
        "required_evidence": [
            {"doc_id": d, "section": s, "why": "needed"} for d, s in evidence
        ],
        "provenance": {"source": "hand_written", "labelled_on": "2026-08-25", "minutes_to_label": 3},
    }


def test_corruption_does_not_mutate_the_original(nc):
    original = item([("DOC-A", "Article 1"), ("DOC-A", "Article 3")])
    before = [dict(e) for e in original["required_evidence"]]
    nc.corrupt(original, ORDER, random.Random(1))
    assert original["required_evidence"] == before


def test_dropping_leaves_a_shorter_evidence_set(nc):
    for seed in range(40):
        broken, how = nc.corrupt(
            item([("DOC-A", "Article 1"), ("DOC-A", "Article 3")]), ORDER, random.Random(seed)
        )
        if how.startswith("dropped"):
            assert len(broken["required_evidence"]) == 1
            return
    pytest.fail("no seed produced a drop")


def test_added_and_swapped_sections_are_document_neighbours(nc):
    """The whole point: a plausible near-miss, not an unrelated section."""
    for seed in range(60):
        broken, how = nc.corrupt(
            item([("DOC-A", "Article 3")]), ORDER, random.Random(seed)
        )
        if how.startswith(("added", "swapped")):
            sections = {e["section"] for e in broken["required_evidence"]}
            introduced = sections - {"Article 3"}
            assert introduced <= {"Article 2", "Article 4"}, introduced


def test_corruption_stays_inside_the_same_document(nc):
    for seed in range(60):
        broken, how = nc.corrupt(item([("DOC-A", "Article 3")]), ORDER, random.Random(seed))
        if not how.startswith("dropped"):
            assert {e["doc_id"] for e in broken["required_evidence"]} == {"DOC-A"}


def test_a_corruption_always_changes_the_evidence(nc):
    """A 'corrupted' item that is identical would be scored as a miss unfairly."""
    for seed in range(60):
        original = item([("DOC-A", "Article 1"), ("DOC-A", "Article 3")])
        result = nc.corrupt(original, ORDER, random.Random(seed))
        if result is None:
            continue
        broken, _ = result
        assert broken["required_evidence"] != original["required_evidence"]


def test_unanswerable_items_are_broken_by_gaining_evidence(nc):
    broken, how = nc.corrupt(item([], category="unanswerable"), ORDER, random.Random(3))
    assert broken["required_evidence"]
    assert "unanswerable" in how


def test_single_section_item_is_never_emptied(nc):
    """Dropping the only section would make an answerable item unanswerable,
    which is a different and much more obvious error than a near-miss."""
    for seed in range(60):
        result = nc.corrupt(item([("DOC-A", "Article 3")]), ORDER, random.Random(seed))
        if result is None:
            continue
        broken, _ = result
        assert broken["required_evidence"], "left an answerable item with no evidence"


def test_isolated_section_cannot_be_corrupted_rather_than_corrupted_badly(nc):
    """A document with one section has no neighbour; the item must be skipped,
    not given evidence from somewhere implausible."""
    order = {"DOC-C": ["Article 1"]}
    result = nc.corrupt(item([("DOC-C", "Article 1")]), order, random.Random(0))
    assert result is None or result[0]["required_evidence"]
