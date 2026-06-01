"""FastAPI application exposing POST /run (port 8000)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app import llm
from app.graph.build_graph import run_build
from app.schemas import LLMConfigUpdate, RunRequest

app = FastAPI(title="Wakeel — Regulatory Agent Factory", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", **llm.current_config()}


@app.get("/config")
def get_config() -> dict:
    """Current LLM configuration (API key masked)."""
    return llm.current_config()


@app.post("/config")
def set_config(update: LLMConfigUpdate) -> dict:
    """Change the API key / endpoint / models at runtime (front-end provider switch)."""
    models = {
        "standard": update.default_model,
        "reasoning": update.reasoning_model,
        "embedding": update.embedding_model,
    }
    models = {tier: name for tier, name in models.items() if name}
    return llm.reconfigure(
        api_key=update.api_key,
        base_url=update.base_url,
        models=models or None,
        interviewer_model=update.interviewer_model,
        offline=update.offline,
    )


@app.post("/run")
def run(req: RunRequest) -> dict:
    if req.mode == "build":
        if not req.intake or not req.intake.workflow_description.strip():
            raise HTTPException(status_code=422, detail="build mode requires intake.workflow_description")
        return run_build(req.intake.model_dump())

    if req.mode == "use":
        # Use mode is delivered in a later milestone (Reviewer, Citation Verifier...).
        raise HTTPException(status_code=501, detail="mode=use not yet implemented (Milestone 2)")

    raise HTTPException(status_code=422, detail=f"unknown mode: {req.mode}")
