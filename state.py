"""
Wakeel — Shared State Types

LangGraph requires explicit state. This module defines the TypedDicts that flow
between agents in both build mode and use mode. Keeping state types in one place
makes the agent topology legible and easier to audit.
"""

from typing import TypedDict, Literal, Any
from dataclasses import dataclass, field


# =============================================================================
# Audit trail (shared by both modes)
# =============================================================================

class AuditEntry(TypedDict):
    """One step in the multi-agent audit trail."""
    step: int
    timestamp: float
    agent: str
    action: str            # e.g. "extracted_requirements", "rejected_citation"
    detail: str            # human-readable summary
    metadata: dict[str, Any]  # structured detail (decision, scores, etc.)


# =============================================================================
# BUILD MODE — Factory state
# =============================================================================

class IntakeRequest(TypedDict, total=False):
    """Initial user-facing request that kicks off build mode."""
    workflow_description: str
    org_id: str
    document_type: Literal["nda", "employment", "services", "commercial"]
    risk_appetite: Literal["conservative", "balanced", "permissive"]
    language: Literal["en", "ar"]


class StructuredRequirements(TypedDict, total=False):
    """Interviewer's structured output, consumed by Debaters & Architect."""
    domain: str
    document_type: str
    org_type: str
    risk_appetite: str
    regulatory_focus_areas: list[str]
    specific_concerns: list[str]
    ambiguities_flagged: list[str]
    original_language: Literal["en", "ar"]


class DebateRound(TypedDict):
    """One round of strict-vs-practical debate."""
    round_number: int
    strict_argument: str
    practical_argument: str
    points_of_convergence: list[str]
    points_of_divergence: list[str]


class CopilotConfig(TypedDict, total=False):
    """The Architect/Builder output — the configured copilot."""
    copilot_id: str
    org_id: str
    template: Literal["nda_review", "employment_review", "services_review"]
    interpretation_overrides: list[dict[str, Any]]
    risk_thresholds: dict[str, Any]
    internal_corpus_additions: list[str]
    output_preferences: dict[str, Any]
    system_prompts: dict[str, str]  # per-agent prompt overrides
    retrieval_rules: dict[str, Any]


class ValidationResult(TypedDict):
    """Validator's verdict on a freshly minted copilot."""
    passed: bool
    sample_runs: list[dict[str, Any]]
    issues: list[str]
    iteration: int


class BuildState(TypedDict, total=False):
    """LangGraph state for build mode (factory)."""
    # Inputs
    request: IntakeRequest
    # Interviewer output
    requirements: StructuredRequirements
    interviewer_followups: list[str]
    # Debate
    debate_rounds: list[DebateRound]
    current_debate_round: int
    # Architect / Builder
    copilot_config: CopilotConfig
    # Validator
    validation: ValidationResult
    builder_iteration: int
    # Final output
    copilot_id: str
    # Cross-cutting
    audit_trail: list[AuditEntry]
    error: str


# =============================================================================
# USE MODE — Copilot review state
# =============================================================================

class Document(TypedDict):
    """The document under review."""
    type: Literal["text", "pdf"]
    content: str
    filename: str


class Citation(TypedDict, total=False):
    """A regulatory citation that must be verified."""
    law: str               # e.g. "Federal Decree-Law 45 of 2021"
    article: str           # e.g. "Article 7"
    quoted_text: str       # the exact statute text the agent claims supports the finding
    verified: bool
    verifier_confidence: float
    verifier_notes: str
    retrieval_match_score: float


class Finding(TypedDict, total=False):
    """One issue identified by the Reviewer."""
    finding_id: str
    clause_id: str
    clause_text: str
    issue: str
    risk_level: Literal["high", "medium", "low"]
    confidence: float
    citation: Citation
    counter_proposal: str
    counter_proposal_iterations: int
    reviewer_iterations: int


class UseState(TypedDict, total=False):
    """LangGraph state for use mode (the copilot reviewing a document)."""
    # Inputs
    copilot_id: str
    copilot_config: CopilotConfig
    document: Document
    # Retrieval
    retrieved_law_chunks: list[dict[str, Any]]
    # Reviewer output (in progress)
    pending_findings: list[Finding]
    verified_findings: list[Finding]
    rejected_findings: list[Finding]
    # Loop counters
    citation_retries: dict[str, int]      # finding_id -> retry count
    counter_proposal_retries: dict[str, int]
    # Final output
    summary: dict[str, Any]
    # Cross-cutting
    audit_trail: list[AuditEntry]
    error: str


# =============================================================================
# Helpers
# =============================================================================

def make_audit_entry(
    step: int,
    agent: str,
    action: str,
    detail: str,
    **metadata: Any,
) -> AuditEntry:
    """Construct an audit entry with current timestamp."""
    import time
    return AuditEntry(
        step=step,
        timestamp=time.time(),
        agent=agent,
        action=action,
        detail=detail,
        metadata=metadata,
    )
