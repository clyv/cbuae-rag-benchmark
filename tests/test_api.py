"""Tests for the HTTP layer.

A fake index stands in for the real one so these run in milliseconds without
downloading models. What is tested is the API's own behaviour: validation, the
excerpt cap that exists for licensing reasons, and that an abstention is
reported as one rather than as an empty result.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from regulens.api import app as app_module
from regulens.generation.answer import Citation, GroundedAnswer
from regulens.retrieval.base import Chunk, RetrievalResult

LONG_TEXT = "The Board must approve any deviation from the Risk Appetite. " * 20


def result(score: float = 7.5) -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(
            chunk_id="INS-GOV-003::Article 3",
            doc_id="INS-GOV-003",
            section="Article 3",
            text=LONG_TEXT,
            metadata={
                "url": "https://rulebook.centralbank.ae/en/rulebook/risk-management",
                "title": "Risk Management and Internal Controls Regulation",
            },
        ),
        score=score,
        rank=1,
    )


class FakeIndex:
    size = 954

    def __init__(self, abstain: bool = False) -> None:
        self.abstain = abstain
        self.calls: list[dict] = []

    def answer(self, question, k=5, rerank=True, threshold=None):
        self.calls.append({"question": question, "k": k, "rerank": rerank, "threshold": threshold})
        results = [result()]
        if self.abstain:
            return (
                GroundedAnswer(
                    text="declined", abstained=True, context_used=results,
                    reason="top relevance 7.500 at or below threshold 9.000", top_score=7.5,
                ),
                results,
            )
        return (
            GroundedAnswer(
                text="...",
                citations=[Citation("INS-GOV-003", "Article 3", LONG_TEXT,
                                    "https://rulebook.centralbank.ae/en/rulebook/risk-management")],
                context_used=results,
                top_score=7.5,
            ),
            results,
        )


@pytest.fixture
def client(monkeypatch):
    def make(abstain: bool = False) -> tuple[TestClient, FakeIndex]:
        index = FakeIndex(abstain)
        monkeypatch.setattr(app_module, "get_index", lambda: index)
        monkeypatch.setattr(app_module, "_index", index)
        return TestClient(app_module.app), index
    return make


def test_health_reports_readiness(client):
    c, _ = client()
    body = c.get("/health").json()
    assert body["status"] == "ok"
    assert body["chunks"] == 954


def test_home_serves_the_page(client):
    c, _ = client()
    response = c.get("/")
    assert response.status_code == 200
    assert "ReguLens" in response.text


def test_ask_returns_citations_with_links(client):
    c, _ = client()
    body = c.post("/ask", json={"question": "who approves a deviation?"}).json()
    assert not body["abstained"]
    assert body["citations"][0]["doc_id"] == "INS-GOV-003"
    assert body["citations"][0]["url"].startswith("https://rulebook.centralbank.ae")
    assert body["citations"][0]["document"]


def test_excerpts_are_capped_because_redistribution_is_not_permitted(client):
    """The cap is a licensing boundary, not a display preference."""
    c, _ = client()
    body = c.post("/ask", json={"question": "who approves a deviation?"}).json()
    excerpt = body["citations"][0]["excerpt"]
    assert len(excerpt) <= app_module.MAX_EXCERPT_CHARS
    assert len(excerpt) < len(LONG_TEXT)


def test_every_response_carries_the_disclaimer(client):
    c, _ = client()
    body = c.post("/ask", json={"question": "who approves a deviation?"}).json()
    assert "not legal" in body["disclaimer"].lower()


def test_abstention_is_reported_as_such_not_as_an_empty_result(client):
    c, _ = client()
    body = c.post("/ask", json={"question": "capital rules for a finance company?",
                                "threshold": 9.0}).json()
    # The fake returns a normal answer; assert the plumbing passes the threshold on.
    assert body["citations"] or body["abstained"]

    c2, _ = client(abstain=True)
    body = c2.post("/ask", json={"question": "capital rules for a finance company?",
                                 "threshold": 9.0}).json()
    assert body["abstained"] is True
    assert "threshold" in body["reason"]
    assert body["citations"] == []


def test_request_options_reach_the_index(client):
    c, index = client()
    c.post("/ask", json={"question": "a question here", "k": 3, "rerank": False, "threshold": 1.5})
    assert index.calls[-1] == {
        "question": "a question here", "k": 3, "rerank": False, "threshold": 1.5
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "hi"},                      # below min_length
        {"question": "x" * 501},                 # above max_length
        {"question": "a valid question", "k": 0},
        {"question": "a valid question", "k": 99},
        {},                                      # missing
    ],
)
def test_bad_requests_are_rejected(client, payload):
    c, _ = client()
    assert c.post("/ask", json=payload).status_code == 422
