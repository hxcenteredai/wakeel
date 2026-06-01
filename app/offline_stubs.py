"""Deterministic stub responses for OFFLINE_MODE.

These let the entire build-mode graph, all feedback loops, the UI, and the audit
logs run end-to-end with no Compass credentials and zero quota usage. Each agent
passes a small JSON "context" block (marker ``@@CTX@@``) in its prompt; the stub
reads it to produce coherent, schema-valid output and to drive loop behaviour
(e.g. the Validator rejects on iteration 1, accepts on iteration 2 to exercise
Loop 2). When real Compass creds are configured, OFFLINE_MODE is off and none of
this runs — the wrapper calls the live endpoint instead.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

CTX_MARKER = "@@CTX@@"
_EMBED_DIM = 256


def _extract_ctx(messages: list) -> dict[str, Any]:
    for msg in reversed(messages):
        content = str(msg.get("content", ""))
        if CTX_MARKER in content:
            raw = content.split(CTX_MARKER, 1)[1].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
    return {}


def _looks_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# --- Per-agent stub generators -------------------------------------------------

def _interviewer(ctx: dict[str, Any]) -> str:
    description = ctx.get("workflow_description", "")
    is_arabic = ctx.get("language") == "ar" or _looks_arabic(description)
    # Loop 3 support: when the Architect escalates, it sets clarification_round.
    clarification_round = ctx.get("clarification_round", 0)

    # Heuristic: treat very short or org-less descriptions as ambiguous on the
    # first pass so Loop 3 (requirements clarification) can demonstrably fire.
    has_org = bool(ctx.get("org_id")) or "org" in description.lower()
    ambiguous = (len(description.split()) < 12 or not has_org) and clarification_round == 0

    follow_up_en = (
        "To tailor the copilot, which organization is this for, and what is your "
        "risk appetite (conservative / balanced / permissive)?"
    )
    follow_up_ar = (
        "\u0644\u062a\u062e\u0635\u064a\u0635 \u0627\u0644\u0645\u0633\u0627\u0639\u062f\u060c "
        "\u0645\u0627 \u0647\u064a \u0627\u0644\u0645\u0624\u0633\u0633\u0629 \u0648\u0645\u0627 \u0645\u062f\u0649 "
        "\u062a\u062d\u0641\u0638\u0643 \u062a\u062c\u0627\u0647 \u0627\u0644\u0645\u062e\u0627\u0637\u0631\u061f"
    )

    result = {
        "language": "ar" if is_arabic else "en",
        "workflow_description_en": (
            "Review vendor NDAs against the organization's data-handling stance "
            "under UAE PDPL and Labour Law."
            if is_arabic
            else (description or "Review vendor NDAs against our data-handling stance.")
        ),
        "org_id": ctx.get("org_id") or "fintech_co_001",
        "document_type": "nda",
        "risk_appetite": ctx.get("risk_appetite") or "conservative",
        "key_concerns": [
            "data_transfer_abroad",
            "consent_reconfirmation",
            "confidentiality_duration",
        ],
        "needs_clarification": bool(ambiguous),
        "follow_up_question": (
            (follow_up_ar if is_arabic else follow_up_en) if ambiguous else ""
        ),
        "response_to_user": (
            (follow_up_ar if is_arabic else follow_up_en)
            if ambiguous
            else (
                "\u062a\u0645 \u0627\u0633\u062a\u0644\u0627\u0645 \u0637\u0644\u0628\u0643. "
                "\u062c\u0627\u0631\u064d \u0628\u0646\u0627\u0621 \u0627\u0644\u0645\u0633\u0627\u0639\u062f."
                if is_arabic
                else "Got it — building your copilot now."
            )
        ),
    }
    return _json(result)


def _debater_a(ctx: dict[str, Any]) -> str:
    rnd = ctx.get("round", 1)
    return _json(
        {
            "stance": "strict_compliance",
            "round": rnd,
            "arguments": [
                "PDPL Article 7 consent must be explicit and re-confirmed for any "
                "cross-border transfer to banking partners.",
                "Confidentiality obligations should survive termination indefinitely "
                "for personal data categories.",
                "Indemnity caps below full liability expose the org under PDPL breach "
                "notification duties.",
            ],
            "rebuttal": "Business convenience cannot override statutory consent duties.",
            "concession": "Standard commercial terms acceptable where no personal data flows.",
        }
    )


def _debater_b(ctx: dict[str, Any]) -> str:
    rnd = ctx.get("round", 1)
    return _json(
        {
            "stance": "business_practicality",
            "round": rnd,
            "arguments": [
                "Indefinite confidentiality is rarely accepted by vendors; a 5-year "
                "tail post-termination is market-standard and enforceable.",
                "Blanket re-consent on every transfer creates operational friction; "
                "a documented standing consent with audit log meets PDPL intent.",
                "Mutual indemnity caps at 12 months fees are commercially reasonable.",
            ],
            "rebuttal": "Over-conservative terms stall deals without reducing real risk.",
            "concession": "Cross-border transfers to non-adequate jurisdictions warrant explicit consent.",
        }
    )


def _architect(ctx: dict[str, Any]) -> str:
    debate_rounds = ctx.get("debate_rounds", 0)
    clarification_round = ctx.get("clarification_round", 0)
    intake = ctx.get("intake", {})

    # Loop 3: if the intake still flags clarification and we have not yet
    # escalated, ask the Interviewer for a follow-up (once).
    if intake.get("needs_clarification") and clarification_round == 0:
        return _json(
            {
                "decision": "needs_clarification",
                "needs_clarification": True,
                "clarification_request": "Confirm org_id and risk appetite before synthesis.",
                "request_more_debate": False,
            }
        )

    # Loop 1: request one extra debate round if fewer than 2 have run.
    if debate_rounds < 2:
        return _json(
            {
                "decision": "request_more_debate",
                "needs_clarification": False,
                "request_more_debate": True,
                "reason": "Need at least two rounds to resolve the cross-border consent split.",
            }
        )

    # Otherwise synthesize the config outline.
    return _json(
        {
            "decision": "synthesize",
            "needs_clarification": False,
            "request_more_debate": False,
            "config_outline": {
                "interpretation_overrides": [
                    {
                        "law": "Federal Decree-Law 45 of 2021",
                        "article": "Article 7",
                        "stance": "Require explicit consent re-confirmation for cross-border "
                        "transfers to banking partners.",
                        "rationale": "Conservative posture from strict-compliance debate.",
                    }
                ],
                "risk_thresholds": {
                    "high_flag_confidence_min": 0.80,
                    "medium_flag_confidence_min": 0.60,
                    "auto_escalate_to_human": ["data_transfer_abroad", "indemnity_caps"],
                },
                "confidentiality_tail_years": 5,
                "rationale": "Balanced synthesis: strict on PDPL consent, market-standard on tails.",
            },
        }
    )


def _builder(ctx: dict[str, Any]) -> str:
    intake = ctx.get("intake", {})
    outline = ctx.get("config_outline", {})
    org_id = intake.get("org_id", "org_default")
    return _json(
        {
            "copilot_id": ctx.get("copilot_id", "cp_pending"),
            "template": "nda_review",
            "org_id": org_id,
            "system_prompts": {
                "reviewer": "You review NDAs against the org's tuned PDPL/Labour stance. "
                "Flag clauses with confidence scores; cite exact articles.",
                "citation_verifier": "Verify every cited article against the corpus via "
                "exact-text retrieval; reject hallucinated citations.",
            },
            "output_schema": {
                "findings": [
                    {
                        "clause": "str",
                        "risk": "high|medium|low",
                        "confidence": "float",
                        "citation": {"law": "str", "article": "str"},
                        "rationale": "str",
                    }
                ]
            },
            "retrieval_rules": {
                "laws": [
                    "Federal Decree-Law 33 of 2021",
                    "Federal Decree-Law 45 of 2021",
                ],
                "top_k": 5,
                "chunk_by": "article",
            },
            "risk_thresholds": outline.get(
                "risk_thresholds",
                {"high_flag_confidence_min": 0.80, "medium_flag_confidence_min": 0.60},
            ),
            "interpretation_overrides": outline.get("interpretation_overrides", []),
        }
    )


def _validator(ctx: dict[str, Any]) -> str:
    iteration = ctx.get("iteration", 1)
    # Loop 2: reject the first build, accept the revised one.
    if iteration < 2:
        return _json(
            {
                "passed": False,
                "score": 0.62,
                "issues": [
                    "Reviewer prompt does not enforce citation on every regulatory claim.",
                    "Risk threshold for data_transfer_abroad not wired to auto-escalation.",
                ],
                "feedback": "Tighten reviewer prompt to mandate citations; wire escalation list.",
            }
        )
    return _json(
        {
            "passed": True,
            "score": 0.91,
            "issues": [],
            "feedback": "Sample NDA produced 3 well-cited findings; thresholds applied correctly.",
        }
    )


_AGENTS = {
    "Interviewer": _interviewer,
    "Debater A": _debater_a,
    "Debater B": _debater_b,
    "Architect": _architect,
    "Builder": _builder,
    "Validator": _validator,
}


def stub_chat(agent_name: str, messages: list) -> str:
    ctx = _extract_ctx(messages)
    generator = _AGENTS.get(agent_name)
    if generator is None:
        return _json({"note": f"offline stub for {agent_name}", "ok": True})
    return generator(ctx)


def stub_embed(text: str) -> list[float]:
    """Deterministic pseudo-embedding from a hash, normalized to unit length.

    Good enough for offline retrieval smoke tests; real embeddings come from the
    configured model when OFFLINE_MODE is off.
    """
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    raw = [b - 128 for b in digest]
    vec = [raw[i % len(raw)] * (1 + (i // len(raw))) for i in range(_EMBED_DIM)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
