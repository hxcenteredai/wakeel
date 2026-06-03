# Wakeel Architecture

## 1. Agent topology

Wakeel is a 10-agent system across two modes. **Both modes are implemented:**
Milestone 1 delivered the six build-mode agents (Loops 1–3); Milestone 2 added
the four use-mode agents (Reviewer, Citation Verifier, Counter-Proposal Drafter,
Synthesis) and Loops 4–5.

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
| Builder | build | standard | Instantiates the copilot config; config persists to `data/copilots/`. |
| Validator | build | standard | Rejects substandard configs (Loop 2). |
| Reviewer | use | reasoning | Emits findings with citation. Re-cites on Loop 4. Critiques drafts on Loop 5. |
| Citation Verifier | use | standard | Orchestrator-driven exact-text lookup against the corpus (Loop 4). |
| Counter-Proposal Drafter | use | standard | Drafts replacement clauses for flagged findings; revises on Loop 5 critique. |
| Synthesis | use | standard | Assembles final findings, summary, and recommendation. |

## 2. Feedback loops

| Loop | Trigger | Convergence cap |
|---|---|---|
| 1 — Stance debate | Architect requests ≥2 rounds before synthesis | 3 rounds |
| 2 — Validation reject | Validator fails the sample run → Builder revises | 3 iterations |
| 3 — Requirements clarification | Architect detects ambiguity → Interviewer follow-up | 2 escalations |
| 4 — Citation rejection | Reviewer's citation not found in corpus → re-cite from semantic-search candidates | 3 per finding |
| 5 — Counter-proposal critique | Reviewer-as-critic rejects a Drafter clause → Drafter revises | 3 per finding |

Routing lives in `app/graph/build_graph.py` (build) and `app/graph/use_graph.py`
(use). Routers are **read-only**; all state mutation (loop counters, flags)
happens inside nodes so counters survive routing. Hard caps guarantee termination.

### Loop 4 — Citation rejection (the killer feature, PRD §16)

The Citation Verifier is **not an LLM call** — it is orchestrator-driven
exact-text retrieval against ChromaDB. Every Reviewer finding emits a citation
`{law, article}`; the verifier looks up the exact article by ID (e.g.
`PDPL:art-7`). On a miss, the verifier asks the corpus for the top-3 semantic
candidates and feeds them back to the Reviewer for re-cite. The result: a
hallucinated citation cannot survive the audit trail — the audit shows the
rejection moment with the actual exact text of the eventually-cited article.

Canonical evidence: `logs/samples/use_mode_run_loops_4_5.jsonl`.

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
   Live endpoint (env)        app/offline_stubs.py
   OpenAI direct or Compass   (no network, zero quota)
```

**Endpoints (same code, swap via `.env`):**

| Profile | `OPENAI_BASE_URL` |
|---|---|
| Developer | `https://api.openai.com/v1` |
| Compass (M1/M2 acceptance) | `https://compass.core42.ai/v1` |

**Model tiers** (confirmed on Compass; defaults in `.env.example`):

| Tier | Env var | Model |
|---|---|---|
| Standard | `DEFAULT_MODEL` | `gpt-4.1` |
| Reasoning | `REASONING_MODEL` | `gpt-5.1` |
| Embedding | `EMBEDDING_MODEL` | `text-embedding-3-large` |

Optional: `INTERVIEWER_MODEL=G42-INCEPTION-GPT41-MSA` for the sovereign-AI demo
(Inception Arabic on Compass) — per-agent override only.

**Invariants:** agents never import `OpenAI` or instantiate a client; they request
a *tier*, never a model name; `agent_name` is required for audit attribution.
Swapping endpoints or models is an env-var change only.

Every call logs: `timestamp, agent, model, tier, latency_seconds, input_tokens,
output_tokens, status, error_message`.

## 4. Corpus pipeline

- `data/corpus/corpus_config.json` declares each statute: `law_name`, `file`, and
  an `article_pattern` regex. Adding a statute is a config + data drop.
- `app/corpus/ingest.py` splits each statute by article, embeds via the wrapper,
  and stores in ChromaDB with metadata (`law_name`, `short_name`, `article_number`).
- `app/corpus/retrieval.py` exposes `semantic_search()` (Reviewer) and
  `get_article()` (exact-text lookup for the Citation Verifier).

**Current corpus (PRD §5):**

| Law | Short name | Articles ingested |
|---|---|---|
| Federal Decree-Law 33 of 2021 | Labour Law | 8 |
| Federal Decree-Law 45 of 2021 | PDPL | 8 |
| Federal Law 18 of 1993 | Commercial Transactions Law | 6 |
| Federal Law 5 of 1985 | Civil Transactions Law | 7 |

All four ship with public placeholder excerpts; replace with official PDFs as a
data drop without code changes.

## 5. Copilot registry

`app/copilot_registry.py` is a file-backed JSON store under `data/copilots/`.
Build mode persists `copilot_config` keyed by `copilot_id`; use mode loads it
back so the produced copilot is replayable across sessions. `GET /copilots`
lists what has been built.

## 6. Audit trail

`app/logging_utils.py` defines `AuditTrail`, collecting one entry per agent action
(`agent, action, decision, reason, loop, details`). Entries are streamed to
`logs/run_<run_id>.jsonl` and returned in the API response, then rendered in the
Streamlit sidebar.

## 7. Services & ports

| Service | Entry | Port |
|---|---|---|
| API (FastAPI) | `run.py` → `app.api:app` | 8000 |
| UI (Streamlit) | `run_ui.py` | 8001 |

Both run together via `docker-entrypoint.sh` in the Docker image. Verified clean
build + run from a fresh clone with both ports responding under 2s; full
use-mode arc through the container reproduces the canonical Loop 4/5 evidence —
see [`docs/use-mode-evidence.md`](use-mode-evidence.md).
