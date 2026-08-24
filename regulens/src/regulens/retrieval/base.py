"""Common interface for every retrieval system under comparison.

The whole point of the project is that four systems are swapped behind one
interface and measured on identical inputs. Keep this stable; if a system
needs something outside this contract, that is a finding worth writing up,
not a reason to special-case the harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Chunk:
    """One indexed unit of text, carrying enough metadata to be cited."""

    chunk_id: str
    doc_id: str
    section: str
    text: str
    metadata: dict = field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        return f"{self.doc_id}::{self.section}"


@dataclass(frozen=True)
class RetrievalResult:
    chunk: Chunk
    score: float
    rank: int


@runtime_checkable
class Retriever(Protocol):
    """Anything the eval harness can score."""

    name: str

    def retrieve(self, query: str, k: int) -> list[RetrievalResult]:
        """Return up to k results, best first."""
        ...
