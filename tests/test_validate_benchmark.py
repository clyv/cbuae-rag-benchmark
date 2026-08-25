"""Tests for the two checks that stop a question failing silently.

A mistyped section label and a citation of an instrument that must not be cited
both produce the same symptom once results are being measured - the question
scores zero forever - and both look like retrieval failures rather than
labelling failures. These are the guards against that.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    """Import the script by path; scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "validate_benchmark", REPO_ROOT / "scripts" / "validate_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validator(tmp_path, monkeypatch):
    module = load_validator()
    registry = tmp_path / "registry.csv"
    registry.write_text(
        "doc_id,title,labelling_eligible,labelling_note\n"
        "DOC-OK,Fine,true,\n"
        "DOC-FUTURE,Not yet,false,commences 2027-07-15\n"
        "DOC-BLANK,No column value,,\n",
        encoding="utf-8",
    )
    sections = tmp_path / "sections.jsonl"
    sections.write_text(
        "\n".join(
            json.dumps({"doc_id": d, "section": s})
            for d, s in [("DOC-OK", "Article 1"), ("DOC-FUTURE", "Article 1")]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "REGISTRY", registry)
    monkeypatch.setattr(module, "SECTIONS", sections)
    return module


def test_only_explicit_false_is_ineligible(validator):
    """A blank or missing column must not silently make a document uncitable."""
    ineligible = validator.labelling_eligibility()
    assert set(ineligible) == {"DOC-FUTURE"}
    assert "commences 2027-07-15" in ineligible["DOC-FUTURE"]


def test_corpus_evidence_ids_are_doc_and_section(validator):
    assert validator.corpus_evidence_ids() == {
        "DOC-OK::Article 1",
        "DOC-FUTURE::Article 1",
    }


def test_missing_corpus_file_disables_the_check_rather_than_failing(validator, tmp_path):
    """No parsed corpus yet is a normal state, not an error."""
    validator.SECTIONS = tmp_path / "absent.jsonl"
    assert validator.corpus_evidence_ids() == set()


def test_missing_registry_treats_everything_as_eligible(validator, tmp_path):
    validator.REGISTRY = tmp_path / "absent.csv"
    assert validator.labelling_eligibility() == {}


def test_real_registry_marks_the_future_takaful_instruments():
    """Guards the actual project data, not just the parsing of it."""
    module = load_validator()
    ineligible = module.labelling_eligibility()
    assert "INS-TAK-006" in ineligible
    # Anything ineligible must still be present in the corpus - the whole point
    # is that these are indexed as distractors rather than removed.
    corpus_docs = {key.split("::", 1)[0] for key in module.corpus_evidence_ids()}
    assert corpus_docs, "run scripts/build_corpus.py first"
    for doc_id in ineligible:
        assert doc_id in corpus_docs, f"{doc_id} is ineligible but not indexed"
