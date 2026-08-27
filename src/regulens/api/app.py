"""HTTP API over the retrieval and answering stack. Phase 5.

    python -m uvicorn regulens.api.app:app --reload
    # then open http://127.0.0.1:8000

## What this deliberately does not serve

`SOURCES.md` records that CBUAE terms permit download for non-commercial use but
**not redistribution**. A demo that returned the full text of an article for any
question asked would be a mirror of the Rulebook wearing a search box, which is
the thing those terms do not allow.

So a response carries the citation, a short excerpt, and a deep link back to the
Rulebook. `MAX_EXCERPT_CHARS` is enforced here rather than left to the answerer,
because this is the boundary where text leaves the machine. The excerpt is
enough to see why a section was retrieved; reading the provision means following
the link to the source, which is where a regulatory answer should be read
anyway.

## Why the index builds lazily

Loading the embedding model, embedding 954 chunks and loading the cross-encoder
takes about ninety seconds. Doing that at import time makes the process look
hung and breaks `--reload`. The first request pays the cost; `/health` reports
whether it has been paid yet.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from regulens.api.index import Index, load_chunks

# The excerpt cap. See the module docstring: this is a licensing boundary, not a
# display preference.
MAX_EXCERPT_CHARS = 320

app = FastAPI(
    title="ReguLens",
    description=(
        "Retrieval over CBUAE insurance regulation. Returns citations and short "
        "excerpts with links to the source. Not legal or compliance advice."
    ),
    version="0.1.0",
)

_index: Index | None = None
_index_error: str | None = None
_lock = threading.Lock()


def get_index() -> Index:
    global _index, _index_error
    with _lock:
        if _index is None and _index_error is None:
            try:
                _index = Index(load_chunks())
            except Exception as exc:  # surfaced through /health and /ask
                _index_error = f"{type(exc).__name__}: {exc}"
    if _index is None:
        raise HTTPException(503, detail=f"index unavailable: {_index_error}")
    return _index


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    k: int = Field(default=5, ge=1, le=20)
    rerank: bool = Field(default=True, description="slower, better ranked, enables abstention")
    threshold: float | None = Field(
        default=None,
        description=(
            "decline when the top relevance score is at or below this. "
            "No default: see results/abstention.md for why one is not shipped."
        ),
    )


class CitationOut(BaseModel):
    doc_id: str
    section: str
    document: str
    excerpt: str
    url: str
    score: float


class AskResponse(BaseModel):
    question: str
    abstained: bool
    reason: str
    citations: list[CitationOut]
    top_score: float | None
    elapsed_ms: float
    disclaimer: str = (
        "Retrieval output over a snapshot of the CBUAE Rulebook. Excerpts are "
        "shown for identification; read the provision at the linked source. "
        "Not legal, regulatory or compliance advice."
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "index_ready": _index is not None,
        "index_error": _index_error,
        "chunks": _index.size if _index else None,
    }


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    index = get_index()
    started = time.perf_counter()
    answer, results = index.answer(
        request.question, k=request.k, rerank=request.rerank, threshold=request.threshold
    )

    by_section = {f"{r.chunk.doc_id}::{r.chunk.section}": r for r in results}
    citations = []
    for citation in answer.citations:
        result = by_section.get(citation.evidence_id)
        citations.append(
            CitationOut(
                doc_id=citation.doc_id,
                section=citation.section,
                document=(result.chunk.metadata.get("title", "") if result else ""),
                excerpt=citation.quote[:MAX_EXCERPT_CHARS].rstrip(),
                url=citation.url,
                score=round(result.score, 3) if result else 0.0,
            )
        )

    return AskResponse(
        question=request.question,
        abstained=answer.abstained,
        reason=answer.reason,
        citations=citations,
        top_score=round(answer.top_score, 3) if answer.top_score is not None else None,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
    )


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
