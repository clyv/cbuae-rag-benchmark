"""Tests for the embedding cache key.

The cache is a correctness risk, not just a speed feature: a stale hit would
serve vectors for text that no longer exists, silently, with results that look
plausible. These test the key rather than the caching, because the key is what
makes a stale hit impossible.

The encoder itself is not exercised - that would download a model to assert
something about numpy.
"""

from __future__ import annotations

from regulens.retrieval.dense import _fingerprint


def test_same_inputs_give_the_same_key():
    a = _fingerprint("model-a", ["one", "two"])
    b = _fingerprint("model-a", ["one", "two"])
    assert a == b


def test_changing_the_model_invalidates_the_cache():
    assert _fingerprint("model-a", ["one"]) != _fingerprint("model-b", ["one"])


def test_changing_any_text_invalidates_the_cache():
    assert _fingerprint("m", ["one", "two"]) != _fingerprint("m", ["one", "three"])


def test_reordering_invalidates_the_cache():
    """Row order is the mapping from vector to chunk; swapping it silently
    attaches every embedding to the wrong section."""
    assert _fingerprint("m", ["one", "two"]) != _fingerprint("m", ["two", "one"])


def test_adding_a_chunk_invalidates_the_cache():
    assert _fingerprint("m", ["one"]) != _fingerprint("m", ["one", "two"])


def test_concatenation_cannot_collide():
    """Without a separator, ['ab','c'] and ['a','bc'] would hash identically -
    a rebuild that only moved a chunk boundary would then reuse stale vectors."""
    assert _fingerprint("m", ["ab", "c"]) != _fingerprint("m", ["a", "bc"])
