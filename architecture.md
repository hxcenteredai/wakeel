# Wakeel — Architecture

This document describes the agent topology, the five feedback loops, and the
LLM client architecture.

> **Status:** v0 — foundational structure. Dev fills in implementation details
> and adds the topology diagram during the build.

## 1. System overview

Wakeel is a multi-agent system orchestrated by LangGraph, exposed via a
FastAPI server (port 8000) and a Streamlit chat UI (port 8001). All LLM access
goes through a single shared wrapper at `app/llm.py`.

```
┌─────────────────┐         ┌─────────────────┐
│  Streamlit UI   │────────▶│   FastAPI app   │
│   (port 8001)   │  HTTP   │   (port 8000)   │
└─────────────────┘         └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │  LangGraph App  │
                            │  (state machine)│
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │   app/llm.py    │
                            │   (LLM wrapper) │
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │  Compass / LLM  │
                            │   provider API  │
                            └─────────────────┘
```

## 2. Build mode topology

The Build mode graph (LangGraph) mints a new copilot from a user description.

**State type:** `BuildState` (see `app/state.py`)

**Nodes (agents):**
- `interviewer` — extracts structured requirements (accepts Arabic or English)
- `debater_strict` — argues conservative interpretation
- `debater_practical` — argues business-practical interpretation
- `architect` — synthesizes the debate; decides template and config
- `builder` — instantiates the copilot
- `validator` — runs sample inputs through the new copilot

**Edges and routing:**
- `START → interviewer`
- `interviewer → debater_strict` (if requirements complete) OR `interviewer → END` (with clarification request)
- `debater_strict → debater_practical → architect` (when debate round complete)
- `architect → interviewer` (Loop 3: requirements clarification needed) OR `architect → builder`
- `builder → validator`
- `validator → builder` (Loop 2: failed validation, max 3 iterations) OR `validator → END`

**Feedback loops:**
- **Loop 1 — Stance Debate:** debater_strict and debater_practical exchange arguments across 2–3 rounds. Each round is one trip through the cycle; Architect decides when convergence is reached.
- **Loop 2 — Validation Rejection:** Validator returns the new copilot to Builder with specific feedback. Max 3 iterations.
- **Loop 3 — Requirements Clarification:** Architect detects ambiguity and routes back to Interviewer for follow-up questions.

## 3. Use mode topology

The Use mode graph runs a configured copilot against a submitted document.

**State type:** `UseState` (see `app/state.py`)

**Nodes (agents):**
- `retrieve` — pulls relevant statute chunks from the corpus
- `reviewer` — produces findings against the org-tuned stance
- `citation_verifier` — validates every citation against the corpus
- `counter_drafter` — drafts replacement language for flagged clauses
- `synthesis` — assembles the final response

**Edges and routing:**
- `START → retrieve → reviewer`
- `reviewer → citation_verifier`
- `citation_verifier → reviewer` (Loop 4: citation rejected, max 3 retries per finding) OR `citation_verifier → counter_drafter`
- `counter_drafter → reviewer` (Loop 5: counter-proposal still violates law, max 3 retries) OR `counter_drafter → synthesis`
- `synthesis → END`

**Feedback loops:**
- **Loop 4 — Citation Rejection:** the killer feature. Citation Verifier performs exact-text retrieval and rejects findings where the cited article doesn't say what the Reviewer claims.
- **Loop 5 — Counter-Proposal Critique:** Drafter's replacement clauses are checked against the same statute that triggered the original flag.

## 4. LLM client architecture

See `docs/llm_client.md` for the full spec.

**One rule:** all LLM calls in the codebase go through `app/llm.py:chat()` or
`app/llm.py:embed()`. No agent imports `openai` directly. This gives us:
- Provider-agnosticism via env vars
- Audit trail attribution per agent
- Centralized retry, rate-limit, and sample-mode handling

## 5. Corpus and retrieval

**Store:** ChromaDB, local file-backed, at `data/corpus/chromadb/`.

**Chunking strategy:** by article. Each chunk's metadata includes:
- `law` (e.g. `"Federal Decree-Law 45 of 2021"`)
- `article` (e.g. `"Article 7"`)
- `exact_text` (the verbatim article text)
- `source_file`
- `chunk_index`

The Citation Verifier uses exact-text retrieval against `exact_text`, not just
semantic search, so hallucinated citations are detectable.

## 6. Org adaptation layer

**Schema:** see `app/org/config.py`.

**Sample:** `data/orgs/sample_fintech.json`.

Each copilot instance binds to one org config. Config fields override the base
template prompts and retrieval rules. This is the moat — public laws are
public; interpretations are private.

## 7. Logs and audit trail

Every request gets a unique `run_id` and writes to `logs/run_<run_id>.jsonl`.

Each line is a structured event:
```json
{
  "step": 3,
  "timestamp": 1716300000.123,
  "agent": "citation_verifier",
  "action": "rejected_citation",
  "detail": "Cited Article 43 of Labour Law; actual Article 43 covers working hours, not termination.",
  "metadata": {"finding_id": "f001", "retry_count": 1}
}
```

The audit trail is a first-class output, not a side artifact. It is included in
both API responses and surfaced in the UI sidebar.

---

> **TODO for dev:**
> - Generate visual topology diagrams (suggest mermaid or draw.io) and embed in
>   sections 2 and 3
> - Add sequence diagrams for each of the 5 feedback loops
> - Document the exact prompt structure for each agent once tuned
