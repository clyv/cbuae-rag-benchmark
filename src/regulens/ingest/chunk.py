"""Section -> retrievable chunks.

STUB - Phase 2.

Long sections need splitting; short ones may need merging. Whatever you do,
preserve the section label on every resulting chunk, and record the chunking
parameters in results/ so a run can be reproduced.

Worth testing as an ablation later: fixed-size vs section-aware chunking is a
cheap experiment and a good README paragraph.
"""

from __future__ import annotations

from regulens.retrieval.base import Chunk


def chunk_sections(sections: list[Chunk], max_tokens: int = 512, overlap: int = 64) -> list[Chunk]:
    raise NotImplementedError("Phase 2")
