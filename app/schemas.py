"""Pydantic request/response models for POST /run (PRD section 9)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class BuildIntake(BaseModel):
    workflow_description: str = Field(..., description="User's description (EN or AR).")
    org_id: Optional[str] = None
    document_type: Optional[str] = "nda"
    risk_appetite: Optional[str] = None
    language: Literal["en", "ar"] = "en"


class UseDocument(BaseModel):
    """Document submitted in use mode (PRD §9)."""

    type: Literal["text"] = "text"
    content: str = Field(..., description="Raw document text (e.g. NDA body).")
    title: Optional[str] = None


class RunRequest(BaseModel):
    mode: Literal["build", "use"]
    # Build mode
    intake: Optional[BuildIntake] = None
    # Use mode
    copilot_id: Optional[str] = None
    document: Optional[UseDocument] = None


class LLMConfigUpdate(BaseModel):
    """Runtime LLM settings editable from the front-end (provider flexibility)."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    reasoning_model: Optional[str] = None
    embedding_model: Optional[str] = None
    interviewer_model: Optional[str] = None
    offline: Optional[bool] = None


class BuildResponse(BaseModel):
    run_id: str
    mode: Literal["build"] = "build"
    copilot_id: str
    config: dict[str, Any]
    validation_results: dict[str, Any]
    audit_trail: list[dict[str, Any]]
    interviewer_response: str = ""


class Citation(BaseModel):
    law: str
    article: str
    verified: bool = False
    exact_text: Optional[str] = None
    verification_attempts: int = 1


class Finding(BaseModel):
    clause: str
    risk: Literal["high", "medium", "low"]
    confidence: float
    citation: Citation
    rationale: str
    counter_proposal: Optional[str] = None
    counter_proposal_iterations: int = 0


class UseSummary(BaseModel):
    total_findings: int = 0
    high_risk: int = 0
    medium_risk: int = 0
    low_risk: int = 0
    verified_citations: int = 0
    citation_rejections: int = 0
    draft_critiques: int = 0
    recommendation: str = ""


class UseResponse(BaseModel):
    run_id: str
    mode: Literal["use"] = "use"
    copilot_id: str
    findings: list[Finding]
    summary: UseSummary
    audit_trail: list[dict[str, Any]]
