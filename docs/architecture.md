# Wakeel Architecture

## 1. Agent topology

Wakeel is a 10-agent system across two modes. **Milestone 1 implements the six
build-mode agents** and Loops 1–3. Use-mode agents (Reviewer, Citation Verifier,
Counter-Proposal Drafter, Synthesis) and Loops 4–5 arrive in Milestone 2.

```
                          POST /run  { mode: "build" }
                                     │
                                     ▼
                          ┌────────────────────┐
                          │     Interviewer     │  tier: standard
                          │  (English / Arabic) │  replies in user's language
                          └─────────┬──────────┘
                                    │ structured intake (English)
            Loop 3 (clarification)  │  ◄──────────────────────────┐
                                    ▼                              │
                          ┌────────────────────┐                  │
                 ┌──────► │   Stance Debate     │  tier: reasoning │
                 │        │  Debater A (strict) │                  │
   Loop 1        │        │  Debater B (practical)                 │
 (debate rounds) │        └─────────┬──────────┘                  │
                 │                  │ debate transcript            │
                 │                  ▼                              │
                 │        ┌────────────────────┐                  │
                 └────────│      Architect      │ ─────────────────┘
                          │ (synthesize / escalate / request debate)
                          └─────────┬──────────┘  tier: reasoning
                                    │ config_outline
                                    ▼
                          ┌────────────────────┐
                 ┌──────► │      Builder        │  tier: standard
                 │        │ (prompts, schema,   │
   Loop 2        │        │  retrieval, thresholds)
 (validation)    │        └─────────┬──────────┘
                 │                  │ copilot_config
                 │                  ▼
                 │        ┌────────────────────┐
                 └────────│      Validator      │  tier: standard
                          │ (runs sample input) │
                          └─────────┬──────────┘
                                    │ pass
                                    ▼
                   copilot_id + config + validation + audit_trail
```

### Agent / tier mapping (PRD §7)

| Agent | Mode | Tier | Notes |
|---|---|---|---|
| Interviewer | build | standard | EN/AR input; structured English output. |
| Debater A — Strict | build | reasoning | Conservative interpretation. |
| Debater B — Practicality | build | reasoning | Workable positions. |
| Architect | build | reasoning | Synthesis + Loop 1/3 control. |
| Builder | build | standard | Instantiates the copilot config. |
| Validator | build | standard | Rejects substandard configs (Loop 2). |
| Reviewer / Citation Verifier / Drafter / Synthesis | use | — | Milestone 2. |

## 2. Feedback loops

| Loop | Trigger | Convergence cap |
|---|---|---|
| 1 — Stance debate | Architect requests ≥2 rounds before synthesis | 3 rounds |
| 2 — Validation reject | Validator fails the sample run → Builder revises | 3 iterations |
| 3 — Requirements clarification | Architect detects ambiguity → Interviewer follow-up | 2 escalations |

Routing lives in `app/graph/build_graph.py`. Routers are **read-only**; all state
mutation (loop counters, flags) happens inside nodes so counters survive routing.
Hard caps guarantee termination.

## 3. LLM client architecture (SOW §6)

```
       agents/*.py
          │  chat(agent_name, tier, messages)   embed(texts)
          ▼
   ┌──────────────────────────────────────────────┐
   │                 app/llm.py                     │
   │  • single shared OpenAI client (module load)   │
   │  • tier → model resolution (env vars)          │
   │  • tenacity retry (4 attempts, 2s–30s)         │
   │  • SAMPLE_MODE max_tokens cap                   │
   │  • OFFLINE_MODE deterministic stubs            │
   │  • per-call JSONL logging (logs/llm_calls.jsonl)│
   └──────────────────────────────────────────────┘
          │                         │
          ▼                         ▼
   Compass endpoint           app/offline_stubs.py
   (OpenAI-protocol)          (no network, zero quota)
```

**Invariants:** agents never import `OpenAI` or instantiate a client; they request
a *tier*, never a model name; `agent_name` is required for audit attribution.
Swapping models (incl. Jais for the Interviewer) is an env-var change only.

Every call logs: `timestamp, agent, model, tier, latency_seconds, input_tokens,
output_tokens, status, error_message`.

## 4. Corpus pipeline

- `data/corpus/corpus_config.json` declares each statute: `law_name`, `file`, and
  an `article_pattern` regex. Adding a statute is a config + data drop.
- `app/corpus/ingest.py` splits each statute by article, embeds via the wrapper,
  and stores in ChromaDB with metadata (`law_name`, `short_name`, `article_number`).
- `app/corpus/retrieval.py` exposes `semantic_search()` (Reviewer) and
  `get_article()` (exact-text lookup for the Citation Verifier in M2).

## 5. Audit trail

`app/logging_utils.py` defines `AuditTrail`, collecting one entry per agent action
(`agent, action, decision, reason, loop, details`). Entries are streamed to
`logs/run_<run_id>.jsonl` and returned in the API response, then rendered in the
Streamlit sidebar.

## 6. Services & ports

| Service | Entry | Port |
|---|---|---|
| API (FastAPI) | `run.py` → `app.api:app` | 8000 |
| UI (Streamlit) | `run_ui.py` | 8001 |

Both run together via `docker-entrypoint.sh` in the Docker image.
