"""Contextual retrieval: give each chunk a sentence saying where it sits.

The technique, as published: before indexing a chunk, ask a model to write a
short passage situating it inside its document, and prepend that. A chunk saying
"the limit is 25%" becomes "This section of the Financial Regulations sets asset
concentration limits for conventional insurers. The limit is 25%." Reported
reductions in retrieval failure are large.

## Why this project has a specific reason to try it

Not because it is fashionable. `results/failures.md` classified every missed
section and found that **62% are the right instrument and the wrong article
inside it** - the system knows which regulation governs and cannot pick which of
its articles answers. A per-chunk context sentence is aimed exactly there: it
gives sibling articles, which share a document's vocabulary and much of its
phrasing, something that distinguishes them.

`results/doc_title.md` already tested the cheapest possible version of this -
prepend the instrument's title - and got +0.052. That worked, but mostly for the
wrong reason: the title carries the document's *topic*, and the four
matched-instrument confusions it was built to fix mostly did not move, because
those titles are near-duplicates of each other. A generated sentence can say
what a shared title cannot.

## Generation is cached, and the cache is keyed on what went into it

Writing 763 context sentences takes the better part of an hour on CPU. The cache
is keyed by model name plus the chunk text, so editing a chunk or changing the
model invalidates only what changed, and an interrupted run resumes rather than
starting again. Same reasoning as the embedding cache: a cache keyed on anything
less specific is a correctness bug waiting to happen.

## What it costs, stated up front

Every chunk gets a sentence written by a 0.5B model. That sentence can be wrong.
Unlike the document title - which is metadata and true by construction - this
puts *generated* text into the index, and a hallucinated context is indexed
alongside the real provision and retrieved with it. The write-up reports what
the model actually produced rather than only the score it produced.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from regulens.retrieval.base import Chunk

PROMPT = (
    "Below is a section from a UAE insurance regulation.\n\n"
    "Document: {title}\n"
    "Section: {section}\n\n"
    "{text}\n\n"
    "Write one short sentence that says what this section covers and who it "
    "applies to, so it can be told apart from other sections of the same "
    "document. Write only the sentence."
)

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "corpus" / "processed" / "contexts.json"

# How much of the section the model is shown. Prompt processing dominates the
# cost here - at 1400 characters a chunk took 10.6s and the whole corpus would
# have taken over two hours - and a section's subject is almost always settled by
# its opening. The trade is recorded because it is a real one: a context sentence
# written from the first 600 characters can miss something the section only says
# later.
PROMPT_CHARS = 600


def _key(model_name: str, chunk: Chunk) -> str:
    digest = hashlib.sha256(model_name.encode("utf-8"))
    digest.update(bytes([0]))
    digest.update(chunk.text.encode("utf-8"))
    return digest.hexdigest()[:32]


def _clean(text: str) -> str:
    """One sentence, no preamble, no quotes.

    Small models like to answer "Sure! Here is a sentence:" and to wrap the
    result in quotation marks. Both would be indexed verbatim otherwise.
    """
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(sure|certainly|here is|here's)[^:]*:\s*", "", text, flags=re.I)
    text = text.strip().strip('"').strip("'").strip()
    # Keep the first sentence only; anything after it is usually drift.
    match = re.match(r"^(.{20,400}?[.!?])(\s|$)", text)
    return (match.group(1) if match else text)[:400].strip()


class ContextCache:
    """Per-chunk context sentences, generated once and reused."""

    def __init__(self, model_name: str, path: Path = DEFAULT_CACHE) -> None:
        self.model_name = model_name
        self.path = path
        self.entries: dict[str, str] = {}
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                # A corrupt cache costs an hour, not correctness.
                self.entries = {}

    def get(self, chunk: Chunk) -> str | None:
        return self.entries.get(_key(self.model_name, chunk))

    def put(self, chunk: Chunk, context: str) -> None:
        self.entries[_key(self.model_name, chunk)] = context

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=1, ensure_ascii=False), encoding="utf-8")

    def __len__(self) -> int:
        return len(self.entries)


def build_context(generate, chunk: Chunk) -> str:
    """One situating sentence for a chunk, or "" if the model gives nothing usable."""
    prompt = PROMPT.format(
        title=chunk.metadata.get("doc_title", chunk.doc_id),
        section=chunk.section,
        text=chunk.text[:PROMPT_CHARS],
    )
    try:
        return _clean(generate(prompt))
    except Exception:
        # A chunk without a context is indexed as it always was. Failing the
        # whole build because one generation broke would be worse.
        return ""


def contextualise(chunks: list[Chunk], contexts: dict[str, str]) -> list[Chunk]:
    """Chunks with their context sentence prepended to the indexed text.

    `chunk_id`, `doc_id` and `section` are untouched, so `evidence_id` is stable
    and the benchmark labels stay valid - the same invariant that made the
    chunking ablation possible.
    """
    out = []
    for chunk in chunks:
        context = contexts.get(chunk.chunk_id, "")
        out.append(
            Chunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                section=chunk.section,
                text=f"{context}\n{chunk.text}" if context else chunk.text,
                metadata={**chunk.metadata, "context": context},
            )
        )
    return out
