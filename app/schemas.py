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


class RunRequest(BaseModel):
    mode: Literal["build", "use"]
    # Build mode
    intake: Optional[BuildIntake] = None
    # Use mode (implemented in a later milestone; accepted here for forward-compat)
    copilot_id: Optional[str] = None
    document: Optional[dict[str, Any]] = None


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
