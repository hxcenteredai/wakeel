"""FastAPI application exposing POST /run (port 8000)."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app import copilot_registry, decision_history, llm
from app.graph.build_graph import run_build
from app.graph.use_graph import run_use
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


@app.get("/copilots")
def list_copilots() -> dict:
    """List copilots currently registered (built via mode=build)."""
    return {"copilots": copilot_registry.list_copilots()}


@app.get("/decisions/{copilot_id}")
def get_decisions(copilot_id: str) -> dict:
    """Return the full decision history for a copilot.

    Read-only wrapper around the existing ``logs/run_*.jsonl`` audit trails:
    scans every run, filters to runs that reference ``copilot_id``, groups
    the entries per run, and returns a structured response with per-run
    metadata (mode, timestamps, loops fired) alongside the raw entries.

    Pure file read. No new database, no schema, no new dependencies.
    """
    if copilot_registry.load(copilot_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown copilot_id: {copilot_id}")
    runs = decision_history.history_for_copilot(copilot_id)
    return {
        "copilot_id": copilot_id,
        "total_runs": len(runs),
        "total_decisions": sum(r["entry_count"] for r in runs),
        "runs": runs,
    }


@app.post("/run")
def run(req: RunRequest) -> dict:
    if req.mode == "build":
        if not req.intake or not req.intake.workflow_description.strip():
            raise HTTPException(
                status_code=422, detail="build mode requires intake.workflow_description"
            )
        return run_build(req.intake.model_dump())

    if req.mode == "use":
        if not req.copilot_id:
            raise HTTPException(status_code=422, detail="use mode requires copilot_id")
        if not req.document or not req.document.content.strip():
            raise HTTPException(
                status_code=422, detail="use mode requires document.content"
            )
        try:
            return run_use(req.copilot_id, req.document.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    raise HTTPException(status_code=422, detail=f"unknown mode: {req.mode}")
