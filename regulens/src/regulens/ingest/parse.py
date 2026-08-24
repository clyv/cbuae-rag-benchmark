"""PDF -> structured sections.

STUB - Phase 2. Fill this in once you can see what the CBUAE documents
actually look like. Do not design it in advance; regulatory PDFs vary and the
parsing strategy should follow the evidence.

The one hard requirement: every unit of text must carry its doc_id and its
section identifier as printed in the document. Without that, nothing
downstream can be cited or scored.
"""

from __future__ import annotations

from pathlib import Path

from regulens.retrieval.base import Chunk


def parse_document(path: Path, doc_id: str) -> list[Chunk]:
    """Extract section-labelled chunks from one source document.

    Suggested order of attack, cheapest first:
      1. pdfplumber or pymupdf text extraction; check whether section headings
         survive as detectable patterns ("Article 5", "6.1.2", etc.)
      2. If headings are reliable, split on them - this is the good case.
      3. If not, fall back to page-level chunks and record the page number as
         the section. Weaker citations, but honest ones.
      4. Only reach for layout-aware tools if 1-3 genuinely fail. Note in the
         README which route you took and why.
    """
    raise NotImplementedError("Phase 2: implement after inspecting real documents")
