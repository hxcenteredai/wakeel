"""Robustness regression tests for use-mode against live-model output drift.

The offline stub engine emits shape-perfect JSON, which hides whole classes of
failure that only show up against live GPT-5.1 / Compass. These tests
monkey-patch the LLM wrapper to return malformed responses we have actually
observed in the wild and assert the graph completes without crashing and the
API response remains schema-valid.

Cases mirror the two issues reported in the live PO acceptance run on
PR #2 / ``feat/m2-use-mode-delivery``:
  * Issue 1: Reviewer returns ``findings:[]`` or wraps payload in an envelope.
  * Issue 2: ``TypeError: 'int' object is not subscriptable`` after Loop 4 due
    to citation collapsing to a primitive in the re-cite response.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app import llm
from app.agents import use_agents
from app.graph import use_graph
from helpers import CUSTOMER_SCENARIOS, assert_valid_use_response


# --- Test infrastructure ------------------------------------------------------

class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.index = 0
        self.finish_reason = "stop"


class _FakeUsage:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()
        self.model = "fake-live-model"


def _patch_chat(monkeypatch, responder):
    """Replace ``app.llm.chat`` with a stub that calls ``responder(agent_name, messages)``."""

    def fake_chat(agent_name: str, tier: str, messages: list, **kwargs):
        content = responder(agent_name, messages, kwargs)
        return _FakeCompletion(content)

    monkeypatch.setattr(llm, "chat", fake_chat)
    # Both modules cache an alias at import time — patch those too.
    import app.agents.base as base_mod

    monkeypatch.setattr(base_mod, "chat", fake_chat)


def _is_recite_prompt(system_prompt: str) -> bool:
    """The recite prompt is the only one that opens with 'You are the Reviewer.
    The Citation Verifier rejected...'.
    """
    return "Citation Verifier rejected your prior citation" in system_prompt


def _is_critic_prompt(system_prompt: str) -> bool:
    """The critic prompt is the only one that opens with 'You are the Reviewer
    acting as critic'.
    """
    return "acting as critic" in system_prompt


@pytest.fixture()
def use_copilot(api):
    """Build a fresh fintech copilot for use-mode tests."""
    resp = api.post("/run", json={"mode": "build", "intake": CUSTOMER_SCENARIOS[0]["intake"]})
    assert resp.status_code == 200, resp.text
    return resp.json()["copilot_id"]


def _vendor_nda_document() -> dict[str, Any]:
    return {
        "type": "text",
        "title": "Vendor Master NDA — v1 (vendor-favourable)",
        "content": (
            "1. Confidential Information. Each party may disclose to the other "
            "certain confidential information.\n"
            "2. Cross-border transfers. Vendor may transfer Confidential Information "
            "to its banking partners outside the UAE without further notice.\n"
            "3. Termination. Either party may terminate on seven (7) days notice.\n"
            "4. Indemnity. Vendor's aggregate liability is capped at twelve (12) "
            "months of fees, irrespective of the nature of the breach."
        ),
    }


# --- Reviewer issue: zero findings + envelope wrapping ------------------------

def test_reviewer_envelope_wrapped_findings_are_unwrapped(api, use_copilot, monkeypatch):
    """Live GPT-5.1 sometimes wraps the payload in ``{"result": {...}}`` or
    ``{"analysis": {...}}``. The base helper must unwrap so findings survive.
    """

    def responder(agent_name, messages, kwargs):
        sys = messages[0]["content"]
        if agent_name == "Reviewer" and _is_recite_prompt(sys):
            return json.dumps({"citation": {"law": "PDPL", "article": "22"}})
        if agent_name == "Reviewer" and _is_critic_prompt(sys):
            return json.dumps({"accepted": True, "critique": "ok"})
        if agent_name == "Reviewer":
            # Initial review — wrap findings in an envelope.
            return json.dumps({
                "result": {
                    "findings": [
                        {
                            "clause": "Cross-border transfers to banking partners without notice",
                            "risk": "high",
                            "confidence": 0.92,
                            "citation": {"law": "PDPL", "article": "22"},
                            "rationale": "Cross-border transfer without explicit consent breaches PDPL.",
                        },
                        {
                            "clause": "Indemnity cap of twelve months",
                            "risk": "medium",
                            "confidence": 0.7,
                            "citation": {"law": "PDPL", "article": "7"},
                            "rationale": "Cap excludes data-protection breaches.",
                        },
                    ]
                }
            })
        if agent_name == "Counter-Proposal Drafter":
            return json.dumps({"draft_clause": "Vendor shall not transfer data abroad without consent.", "rationale": "Aligns with PDPL Art. 22."})
        if agent_name == "Synthesis":
            return json.dumps({"summary": {"recommendation": "DO NOT SIGN", "total_findings": 2}})
        return "{}"

    _patch_chat(monkeypatch, responder)

    resp = api.post(
        "/run",
        json={"mode": "use", "copilot_id": use_copilot, "document": _vendor_nda_document()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert_valid_use_response(body)
    assert len(body["findings"]) == 2, "envelope-wrapped findings were not unwrapped"


def test_reviewer_zero_findings_passes_through_cleanly(api, use_copilot, monkeypatch):
    """When the live model genuinely returns no findings, the response must
    still be schema-valid (empty list + structured summary)."""

    def responder(agent_name, messages, kwargs):
        sys = messages[0]["content"]
        if agent_name == "Reviewer" and _is_critic_prompt(sys):
            return json.dumps({"accepted": True, "critique": "ok"})
        if agent_name == "Reviewer":
            return json.dumps({"findings": []})
        if agent_name == "Synthesis":
            return json.dumps({"summary": {"recommendation": "Acceptable — no findings."}})
        return "{}"

    _patch_chat(monkeypatch, responder)

    resp = api.post(
        "/run",
        json={"mode": "use", "copilot_id": use_copilot, "document": _vendor_nda_document()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert_valid_use_response(body)
    assert body["findings"] == []
    assert isinstance(body["summary"], dict) and body["summary"]
    assert body["summary"]["total_findings"] == 0


# --- Issue 2: citation collapses to a primitive, crashes on subscript ---------

def test_recite_collapses_citation_to_int_no_crash(api, use_copilot, monkeypatch):
    """Live recite has been observed to return ``{"citation": 22}``.

    Previously this crashed in verifier_node with
    ``TypeError: 'int' object is not subscriptable``. The fix coerces every
    citation back to a ``{law, article}`` dict before mutation.
    """

    state = {"recite_calls": 0}

    def responder(agent_name, messages, kwargs):
        sys = messages[0]["content"]
        if agent_name == "Reviewer" and _is_recite_prompt(sys):
            state["recite_calls"] += 1
            # First two retries: collapsed-to-int citation (the live bug shape).
            if state["recite_calls"] <= 2:
                return json.dumps({"citation": 22})
            # Third retry: still bad — exhausts MAX_CITATION_RETRIES.
            return json.dumps({"citation": "Article 22"})
        if agent_name == "Reviewer" and _is_critic_prompt(sys):
            return json.dumps({"accepted": True, "critique": "ok"})
        if agent_name == "Reviewer":
            # Initial review — one high-risk finding with a citation Loop 4 will reject.
            return json.dumps({
                "findings": [
                    {
                        "clause": "Cross-border transfers without notice",
                        "risk": "high",
                        "confidence": 0.9,
                        "citation": {"law": "PDPL", "article": "9999"},  # hallucinated
                        "rationale": "Cross-border transfer breaches PDPL.",
                    }
                ]
            })
        if agent_name == "Counter-Proposal Drafter":
            return json.dumps({"draft_clause": "No cross-border transfer without explicit consent.", "rationale": "PDPL alignment."})
        if agent_name == "Synthesis":
            return json.dumps({"summary": {"recommendation": "DO NOT SIGN"}})
        return "{}"

    _patch_chat(monkeypatch, responder)

    resp = api.post(
        "/run",
        json={"mode": "use", "copilot_id": use_copilot, "document": _vendor_nda_document()},
    )
    assert resp.status_code == 200, f"use mode crashed on collapsed citation: {resp.text}"
    body = resp.json()
    assert_valid_use_response(body)
    # Citation Verifier must have fired at least once.
    assert body["summary"]["citation_rejections"] >= 1
    # The (now coerced) citation must be a dict with verified=False after retries exhausted.
    cite = body["findings"][0]["citation"]
    assert isinstance(cite, dict)
    assert "verified" in cite


def test_synthesis_returns_scalar_summary_is_coerced(api, use_copilot, monkeypatch):
    """Live synthesis has been observed to return ``{"summary": 1}`` or
    ``{"summary": "text"}``. The API response must still expose a dict-shaped
    summary so consumers can subscript ``body["summary"]["verified_citations"]``
    without crashing.
    """

    def responder(agent_name, messages, kwargs):
        sys = messages[0]["content"]
        if agent_name == "Reviewer" and _is_critic_prompt(sys):
            return json.dumps({"accepted": True, "critique": "ok"})
        if agent_name == "Reviewer":
            return json.dumps({
                "findings": [
                    {
                        "clause": "Cross-border transfers without notice",
                        "risk": "high",
                        "confidence": 0.9,
                        "citation": {"law": "PDPL", "article": "22"},
                        "rationale": "PDPL alignment.",
                    }
                ]
            })
        if agent_name == "Counter-Proposal Drafter":
            return json.dumps({"draft_clause": "Vendor shall not transfer abroad without consent.", "rationale": "PDPL Art. 22."})
        if agent_name == "Synthesis":
            # Pathological live shape: scalar summary.
            return json.dumps({"summary": 1})
        return "{}"

    _patch_chat(monkeypatch, responder)

    resp = api.post(
        "/run",
        json={"mode": "use", "copilot_id": use_copilot, "document": _vendor_nda_document()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert_valid_use_response(body)
    summary = body["summary"]
    assert isinstance(summary, dict)
    # All required scalar fields are filled in deterministically.
    for key in ("total_findings", "verified_citations", "citation_rejections", "draft_critiques", "recommendation"):
        assert key in summary, f"summary missing {key}"


def test_findings_with_non_dict_items_are_filtered(api, use_copilot, monkeypatch):
    """Defensive case: model returns ``{"findings": [1, 2, 3]}`` (the most
    extreme shape drift we've seen). The graph must not crash; non-dict
    entries are dropped at the boundary.
    """

    def responder(agent_name, messages, kwargs):
        sys = messages[0]["content"]
        if agent_name == "Reviewer" and _is_critic_prompt(sys):
            return json.dumps({"accepted": True, "critique": "ok"})
        if agent_name == "Reviewer":
            return json.dumps({"findings": [1, 2, 3]})
        if agent_name == "Synthesis":
            return json.dumps({"summary": {"recommendation": "Insufficient findings to assess."}})
        return "{}"

    _patch_chat(monkeypatch, responder)

    resp = api.post(
        "/run",
        json={"mode": "use", "copilot_id": use_copilot, "document": _vendor_nda_document()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert_valid_use_response(body)
    # Empty findings list is acceptable; the API contract just requires a list.
    assert isinstance(body["findings"], list)


# --- Wrapper JSON-mode behaviour ---------------------------------------------

def test_chat_passes_response_format_when_json_mode_set(monkeypatch):
    """When ``json_mode=True`` is passed to chat(), the wrapper must put
    ``response_format={"type":"json_object"}`` on the wire so GPT-5.1 stops
    wrapping payloads in prose. Verified against an offline-mode call so we
    don't need real credentials.
    """
    seen: dict[str, Any] = {}

    def fake_stub_chat(agent_name, messages):
        # Capture kwargs by inspecting the wrapper's intermediate state? The
        # offline path bypasses _online_chat, so we instead patch _online_chat
        # and force the wrapper into online mode for this assertion.
        return "{}"

    # Force online path so response_format reaches _online_chat.
    def fake_online_chat(model, messages, **kwargs):
        seen.update(kwargs)
        seen["model"] = model
        return _FakeCompletion("{}")

    monkeypatch.setattr(llm, "_online_chat", fake_online_chat)
    monkeypatch.setitem(llm._state, "offline", False)

    llm.chat(
        "Reviewer",
        "reasoning",
        [{"role": "user", "content": "hi"}],
        json_mode=True,
    )
    assert seen.get("response_format") == {"type": "json_object"}, seen


def test_chat_falls_back_when_gateway_rejects_response_format(monkeypatch):
    """If the gateway returns BadRequestError mentioning response_format, the
    wrapper retries once without it and the caller still gets a completion."""

    calls = {"count": 0, "kwargs": []}

    class _BadRequest(Exception):
        pass

    def fake_online_chat(model, messages, **kwargs):
        calls["count"] += 1
        calls["kwargs"].append(dict(kwargs))
        if "response_format" in kwargs:
            raise _BadRequest("Unsupported parameter: 'response_format' is not supported on this model.")
        return _FakeCompletion("{}")

    # Make _looks_like_response_format_rejection recognise our fake error.
    monkeypatch.setattr(llm, "_online_chat", fake_online_chat)
    monkeypatch.setitem(llm._state, "offline", False)

    # The default detector keys off the class name "BadRequest" + message
    # markers; rename our fake class to satisfy it.
    _BadRequest.__name__ = "BadRequestError"

    completion = llm.chat(
        "Reviewer",
        "reasoning",
        [{"role": "user", "content": "hi"}],
        json_mode=True,
    )
    assert completion is not None
    assert calls["count"] == 2, "wrapper should have retried exactly once"
    assert "response_format" not in calls["kwargs"][1]
