"""Helpers shared across E2E tests and the acceptance report."""
from __future__ import annotations

import re

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def build_payload(description: str, language: str = "en", **intake) -> dict:
    payload_intake = {"workflow_description": description, "language": language}
    payload_intake.update(intake)
    return {"mode": "build", "intake": payload_intake}


def loops_in(audit_trail: list[dict]) -> set[str]:
    return {e["loop"] for e in audit_trail if e.get("loop")}


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


# Customer personas reused by tests and the PO acceptance report.
CUSTOMER_SCENARIOS = [
    {
        "id": "sarah_fintech_en",
        "persona": "Sarah — in-house counsel, Dubai fintech (English)",
        "intake": {
            "workflow_description": (
                "We are a Dubai fintech. Build a copilot that reviews vendor NDAs "
                "against our conservative data-handling stance under UAE PDPL, "
                "flagging cross-border transfer and consent clauses."
            ),
            "org_id": "fintech_co_001",
            "document_type": "nda",
            "risk_appetite": "conservative",
            "language": "en",
        },
        "expect_min_loops": {"Loop 1", "Loop 2"},
    },
    {
        "id": "ahmed_arabic",
        "persona": "Ahmed — compliance officer (Arabic intake)",
        "intake": {
            "workflow_description": (
                "\u0623\u062d\u062a\u0627\u062c \u0625\u0644\u0649 \u0645\u0631\u0627\u062c\u0639\u0629 "
                "\u0627\u062a\u0641\u0627\u0642\u064a\u0627\u062a \u0639\u062f\u0645 \u0627\u0644\u0625\u0641\u0635\u0627\u062d "
                "\u0645\u0639 \u0627\u0644\u0645\u0648\u0631\u062f\u064a\u0646 \u0648\u0641\u0642 \u0645\u0648\u0642\u0641 "
                "\u0634\u0631\u0643\u062a\u0646\u0627 \u0627\u0644\u0645\u062a\u062d\u0641\u0638 \u062a\u062c\u0627\u0647 "
                "\u062d\u0645\u0627\u064a\u0629 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a"
            ),
            "language": "ar",
        },
        "expect_min_loops": {"Loop 1", "Loop 2"},
    },
    {
        "id": "vague_request",
        "persona": "Walk-in user — vague request (should trigger clarification)",
        "intake": {"workflow_description": "review NDAs", "language": "en"},
        "expect_min_loops": {"Loop 1", "Loop 2"},
        "offline_expect_loops": {"Loop 1", "Loop 2", "Loop 3"},
    },
]


def assert_valid_build_response(body: dict) -> None:
    """Shape checks shared by tests and the report (PRD section 9)."""
    assert body.get("mode") == "build", body
    assert isinstance(body.get("run_id"), str) and body["run_id"], "missing run_id"
    assert str(body.get("copilot_id", "")).startswith("cp_"), body.get("copilot_id")
    assert isinstance(body.get("config"), dict) and body["config"], "empty config"
    assert isinstance(body.get("validation_results"), dict), "missing validation_results"
    assert isinstance(body.get("audit_trail"), list) and body["audit_trail"], "empty audit_trail"
    # Audit entries carry the required attribution fields.
    for entry in body["audit_trail"]:
        for key in ("agent", "action", "timestamp"):
            assert key in entry, f"audit entry missing {key}: {entry}"
