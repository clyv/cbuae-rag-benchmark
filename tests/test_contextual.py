"""Tests for contextual retrieval.

Context sentences are *generated text put into the index*, which makes them
unlike every other input this project handles. The model is never loaded here -
what is pinned is the cleaning that decides what gets indexed, and the invariant
that contextualising never changes a chunk's identity.
"""

from __future__ import annotations

from pathlib import Path

from regulens.retrieval.base import Chunk
from regulens.retrieval.contextual import (
    ContextCache,
    _clean,
    build_context,
    contextualise,
)


def chunk(chunk_id: str = "D::Article 1", text: str = "The Board shall approve.") -> Chunk:
    return Chunk(chunk_id, "D", "Article 1", text, {"doc_title": "Governance Regulation"})


# --- cleaning what the model produced ---------------------------------------


def test_a_chatty_preamble_is_stripped():
    """Small models answer "Sure! Here is a sentence:" and it would be indexed
    verbatim otherwise."""
    assert _clean("Sure! Here is a sentence: This section covers licensing.") == \
        "This section covers licensing."


def test_surrounding_quotes_are_stripped():
    assert _clean('"This section covers licensing."') == "This section covers licensing."


def test_only_the_first_sentence_is_kept():
    """Anything after the first sentence is usually drift, and drift indexed
    beside a provision is retrieved with it."""
    out = _clean("This section covers licensing. I hope this helps! Let me know.")
    assert out == "This section covers licensing."


def test_whitespace_and_newlines_are_collapsed():
    assert _clean("This  section\n\n covers   licensing.") == "This section covers licensing."


def test_a_very_long_generation_is_truncated():
    assert len(_clean("x" * 900)) <= 400


# --- failure is not fatal ---------------------------------------------------


def test_a_generator_that_raises_yields_no_context():
    """A chunk without a context is indexed as it always was. Failing the whole
    build because one generation broke would be worse."""
    def explode(prompt):
        raise RuntimeError("out of memory")

    assert build_context(explode, chunk()) == ""


def test_the_prompt_carries_the_document_title_and_section():
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return "A sentence about it."

    build_context(capture, chunk())
    assert "Governance Regulation" in seen["prompt"]
    assert "Article 1" in seen["prompt"]


# --- contextualising --------------------------------------------------------


def test_the_context_is_prepended_to_the_indexed_text():
    out = contextualise([chunk()], {"D::Article 1": "This section covers approvals."})
    assert out[0].text.startswith("This section covers approvals.")
    assert "The Board shall approve." in out[0].text


def test_identity_is_untouched_so_the_labels_stay_valid():
    """The same invariant that made the chunking ablation possible: benchmark
    labels name sections, so anything that changes text but not identity can be
    measured without relabelling."""
    original = chunk()
    out = contextualise([original], {"D::Article 1": "Context."})[0]
    assert out.chunk_id == original.chunk_id
    assert out.doc_id == original.doc_id
    assert out.section == original.section
    assert out.evidence_id == original.evidence_id


def test_a_chunk_with_no_context_is_passed_through_unchanged():
    out = contextualise([chunk()], {})
    assert out[0].text == "The Board shall approve."


def test_the_context_is_kept_in_metadata_for_auditing():
    out = contextualise([chunk()], {"D::Article 1": "Context."})
    assert out[0].metadata["context"] == "Context."


# --- the cache --------------------------------------------------------------


def test_the_cache_round_trips(tmp_path: Path):
    cache = ContextCache("model-a", tmp_path / "c.json")
    cache.put(chunk(), "A context.")
    cache.save()
    assert ContextCache("model-a", tmp_path / "c.json").get(chunk()) == "A context."


def test_changing_the_model_invalidates_the_entry(tmp_path: Path):
    cache = ContextCache("model-a", tmp_path / "c.json")
    cache.put(chunk(), "A context.")
    cache.save()
    assert ContextCache("model-b", tmp_path / "c.json").get(chunk()) is None


def test_changing_the_chunk_text_invalidates_the_entry(tmp_path: Path):
    """Editing a section must not leave a context describing the old one."""
    cache = ContextCache("model-a", tmp_path / "c.json")
    cache.put(chunk(), "A context.")
    cache.save()
    reloaded = ContextCache("model-a", tmp_path / "c.json")
    assert reloaded.get(chunk(text="Different text entirely.")) is None


def test_a_corrupt_cache_costs_time_not_correctness(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text("{not json", encoding="utf-8")
    assert len(ContextCache("model-a", path)) == 0
