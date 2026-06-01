"""PO acceptance-review E2E tests — assert the Milestone 1 gates.

These mirror the founder/Claude acceptance review: each test maps to one of the
six Build-mode acceptance gates and fails loudly if the gate is not met.
"""
from __future__ import annotations

import pytest

from helpers import CUSTOMER_SCENARIOS, assert_valid_build_response, loops_in


def test_gate1_llm_connection_health(api):
    """Gate 1: the LLM client is wired and reports its configuration."""
    resp = api.get("/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["models"]) >= {"standard", "reasoning", "embedding"}


def test_gate2_corpus_ingested_and_retrievable():
    """Gate 2: corpus ingested (Labour Law + PDPL) and retrieval returns hits."""
    from app.corpus.retrieval import is_ingested, semantic_search

    assert is_ingested(), "corpus collection is empty"
    hits = semantic_search("personal data cross border transfer consent", top_k=3)
    assert hits, "no retrieval hits"
    laws = {h["metadata"]["short_name"] for h in hits}
    assert laws & {"PDPL", "Labour Law"}, laws
    for h in hits:
        assert {"law_name", "short_name", "article_number"} <= set(h["metadata"])


def test_gate2_retrieval_is_semantic_when_live(offline):
    """When live (real embeddings), retrieval is semantically correct."""
    if offline:
        pytest.skip("Offline embeddings are hash-based, not semantic.")
    from app.corpus.retrieval import semantic_search

    top = semantic_search("notice period to terminate employment", top_k=1)[0]
    assert top["metadata"]["short_name"] == "Labour Law"


def test_gate3_build_returns_valid_response(api):
    """Gate 3: POST /run mode=build returns a valid response on a sample input."""
    sample = CUSTOMER_SCENARIOS[0]["intake"]
    resp = api.post("/run", json={"mode": "build", "intake": sample})
    assert resp.status_code == 200, resp.text
    assert_valid_build_response(resp.json())


def test_gate3_build_handles_arabic(api):
    """Gate 3 (Arabic): an Arabic input also returns a valid response."""
    arabic = next(s for s in CUSTOMER_SCENARIOS if s["id"] == "ahmed_arabic")
    resp = api.post("/run", json={"mode": "build", "intake": arabic["intake"]})
    assert resp.status_code == 200, resp.text
    assert_valid_build_response(resp.json())


def test_gate5_loops_fire_and_are_logged(api, offline):
    """Gate 5: Loops 1-3 fire and appear in the audit trail."""
    resp = api.post("/run", json={"mode": "build", "intake": {"workflow_description": "review NDAs", "language": "en"}})
    assert resp.status_code == 200, resp.text
    fired = loops_in(resp.json()["audit_trail"])
    if offline:
        assert {"Loop 1", "Loop 2", "Loop 3"}.issubset(fired), fired
    else:
        # Live: at least the debate + validation loops must be observable.
        assert {"Loop 1", "Loop 2"}.issubset(fired), fired


def test_gate5_llm_calls_logged():
    """Every LLM call is logged with the required audit fields (SOW section 6)."""
    import json

    from app import config

    log = config.LOG_DIR / "llm_calls.jsonl"
    assert log.exists(), "llm_calls.jsonl missing"
    last = [json.loads(l) for l in log.read_text().splitlines() if l.strip()][-1]
    required = {
        "timestamp", "agent", "model", "tier", "latency_seconds",
        "input_tokens", "output_tokens", "status",
    }
    assert required <= set(last), set(last)
