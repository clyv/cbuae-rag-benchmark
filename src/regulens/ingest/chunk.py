"""Section -> retrievable chunks.

Phase 2. Sections arrive from ingest/parse.py already carrying a citable label.
This module only changes their *size*, never their identity: every chunk keeps
the doc_id and section of the section it came from, so `Chunk.evidence_id` is
stable no matter how the text was split.

That invariant is what makes chunking safe to vary later. Fixed-size versus
section-aware chunking is a cheap ablation and a good README paragraph, and it
can be run without touching the benchmark labels, because the labels name
sections rather than chunks.

Token counting here is whitespace words, not model tokens. Sentence-transformer
tokenizers split subwords and typically produce 1.2-1.5x this count, so treat
`max_tokens` as a conservative proxy and verify against the real tokenizer in
Phase 4 when the embedding model is chosen. Using words keeps ingestion free of
a model dependency, which means the corpus can be rebuilt without downloading
weights.
"""

from __future__ import annotations

import re

from regulens.retrieval.base import Chunk

# A section shorter than this is left whole even if it would otherwise be merged;
# short regulatory sections ("This Regulation shall be published...") are common
# and self-contained.
DEFAULT_MAX_TOKENS = 512
DEFAULT_OVERLAP = 64


def count_tokens(text: str) -> int:
    """Whitespace word count - the proxy this module's budgets are expressed in."""
    return len(text.split())


def _paragraphs(text: str) -> list[str]:
    """Split on blank lines, falling back to single newlines.

    Rulebook bodies are lists of numbered clauses separated by newlines rather
    than blank lines, so splitting only on blank lines would leave most sections
    as one indivisible block.
    """
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) > 1:
        return parts
    return [p.strip() for p in text.split("\n") if p.strip()]


def _split_long_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    """Hard-split a paragraph that alone exceeds the budget, on sentence bounds."""
    sentences = re.split(r"(?<=[.;:])\s+", paragraph)
    out: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        n = count_tokens(sentence)
        if current and size + n > max_tokens:
            out.append(" ".join(current))
            current, size = [], 0
        current.append(sentence)
        size += n
    if current:
        out.append(" ".join(current))
    return out or [paragraph]


def _pack(
    paragraphs: list[str], max_tokens: int, overlap: int
) -> list[str]:
    """Greedily fill windows up to max_tokens, carrying `overlap` words forward."""
    windows: list[str] = []
    current: list[str] = []
    size = 0

    for paragraph in paragraphs:
        n = count_tokens(paragraph)

        if n > max_tokens:
            if current:
                windows.append("\n".join(current))
                current, size = [], 0
            windows.extend(_split_long_paragraph(paragraph, max_tokens))
            continue

        if current and size + n > max_tokens:
            windows.append("\n".join(current))
            if overlap > 0:
                tail = " ".join(windows[-1].split()[-overlap:])
                current, size = [tail], count_tokens(tail)
            else:
                current, size = [], 0

        current.append(paragraph)
        size += n

    if current:
        windows.append("\n".join(current))
    return windows


def chunk_sections(
    sections: list[Chunk],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split oversized sections, leaving section identity untouched.

    A section that fits the budget is returned unchanged, including its
    chunk_id, so the common case is a no-op. A section that does not fit becomes
    several chunks with ids suffixed `#1`, `#2`, ... - all sharing one
    evidence_id, which is exactly the situation metrics._top_k is written to
    handle: repeated sections consume retrieval budget rather than being
    collapsed for free.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")

    out: list[Chunk] = []
    for section in sections:
        if count_tokens(section.text) <= max_tokens:
            out.append(section)
            continue

        windows = _pack(_paragraphs(section.text), max_tokens, overlap)
        for index, window in enumerate(windows, start=1):
            out.append(
                Chunk(
                    chunk_id=f"{section.chunk_id}#{index}",
                    doc_id=section.doc_id,
                    section=section.section,
                    text=window,
                    metadata={
                        **section.metadata,
                        "part": index,
                        "parts": len(windows),
                        "chars": len(window),
                    },
                )
            )
    return out
