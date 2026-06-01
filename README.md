# Wakeel — Sovereign Regulatory Agent Factory

Wakeel turns an organization's interpretation of UAE regulation into deployable
AI copilots. **Build mode** interviews a user (English or Arabic), debates the
regulatory stance with an agent council, and instantiates a configured copilot.
**Use mode** (later milestone) runs that copilot over documents.

This repository currently delivers **Build mode end-to-end (Milestone 1)**.

---

## Architecture at a glance

```
POST /run (mode=build)  ──►  LangGraph build graph
                               Interviewer (EN/AR)
                                  │
                                  ▼
                               Debate ⇄ Architect      ← Loop 1 (stance debate)
                                  │   ▲                  Loop 3 (clarification)
                                  ▼   │
                               Builder ⇄ Validator      ← Loop 2 (validation reject)
                                  │
                                  ▼
                          copilot_id + config + audit_trail
```

- **10-agent system** (build-mode agents implemented in M1; use-mode agents in M2).
- **All LLM access** goes through one wrapper, `app/llm.py` (SOW §6).
- **Corpus**: UAE statutes ingested into ChromaDB, chunked by article.
- **Audit trail**: every agent action + loop iteration logged to JSONL in `logs/`.

See [`docs/architecture.md`](docs/architecture.md) for the full topology and the
LLM-client design.

---

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
# Fill OPENAI_API_KEY and OPENAI_BASE_URL with your Compass credentials.
# Leave them blank to run fully OFFLINE (deterministic stubs, zero quota).
```

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | Compass endpoint (OpenAI-protocol). |
| `DEFAULT_MODEL` / `REASONING_MODEL` / `EMBEDDING_MODEL` | Model per tier. |
| `INTERVIEWER_MODEL` | Optional Arabic model (e.g. Jais) for the Interviewer. |
| `SAMPLE_MODE` | Caps `max_tokens` for dev quota discipline (default `true`). |
| `OFFLINE_MODE` | Force deterministic stubs (auto-on if no API key). |

### 2. Install & ingest corpus

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.corpus.ingest
```

### 3. Run

```bash
python run.py        # API on http://localhost:8000
python run_ui.py     # Streamlit UI on http://localhost:8001
```

### Docker (both services)

```bash
docker build -t wakeel .
docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel
```

---

## Using the API

```bash
curl -X POST localhost:8000/run -H 'Content-Type: application/json' \
  -d '{"mode":"build","intake":{"workflow_description":"Review vendor NDAs against our conservative PDPL stance","language":"en"}}'
```

Response: `run_id`, `copilot_id`, `config`, `validation_results`, `audit_trail`,
`interviewer_response`. See `output_examples/build_mode/` for full samples.

---

## Arabic usage notes

- The Interviewer accepts **English or Arabic** input and replies in the user's
  language (`interviewer_response`). All downstream structured fields are English.
- Send `intake.language = "ar"`; the UI auto-detects Arabic script and renders the
  input/messages **right-to-left**.
- **Jais**: if exposed on Compass, set `INTERVIEWER_MODEL` to it — no code change.
  Otherwise the Interviewer falls back to `DEFAULT_MODEL` with Arabic-aware
  prompting (SOW §2).
- An Arabic build example lives in `input_examples/build_mode/03_arabic_nda.json`.

---

## Feedback loops (logged)

| Loop | Where | Behaviour |
|---|---|---|
| **Loop 1** — Stance debate | Debater A/B ⇄ Architect | ≥2 rounds; Architect can request more (cap 3). |
| **Loop 2** — Validation reject | Validator → Builder | Reject substandard config; revise (cap 3). |
| **Loop 3** — Clarification | Architect → Interviewer | Escalate ambiguity for follow-up (cap 2). |
| Loop 4 / 5 | Use mode | Delivered in Milestone 2. |

Sample run showing Loops 1–3: `logs/samples/build_mode_run_loops_1_2_3.jsonl`.
Per-call LLM logs: `logs/llm_calls.jsonl`.

---

## End-to-end / acceptance tests

Two complementary tools simulate **customers** (building copilots) and the **PO
acceptance review** (gate-by-gate verdict).

### 1. Acceptance report (human-readable verdict)

```bash
python e2e_acceptance.py --offline                  # deterministic, no creds
python e2e_acceptance.py                            # uses .env (live LLM)
python e2e_acceptance.py --base-url http://localhost:8000   # a running server
```

Prints each customer journey (Sarah/EN, Ahmed/AR, vague request) and a Gate 1–6
verdict. Exit code `0` only if all evaluated gates pass.

> **Verifying Milestone 1 from a fresh clone (incl. Compass):** see
> [`docs/verification.md`](docs/verification.md) for the step-by-step walkthrough.

### 2. Pytest suite

```bash
pytest tests/ -q                 # in-process, OFFLINE by default (fast, deterministic)
WAKEEL_E2E_LIVE=1 pytest tests/  # in-process against the live LLM in .env
WAKEEL_E2E_BASE_URL=http://localhost:8000 pytest tests/   # against a running API
```

- `tests/test_customer_journeys.py` — real user flows (EN/AR/ambiguous, use-mode 501, validation).
- `tests/test_acceptance_gates.py` — one assertion group per acceptance gate.

Tests use an isolated vector store and never touch your dev `data/chroma/`.
Loop-3 and Arabic-reply assertions run in offline mode (deterministic); they are
skipped live since they depend on the configured model's JSON fidelity.

## Adding a statute (no code change)

Drop the text file in `data/corpus/`, add an entry to
`data/corpus/corpus_config.json` (law name, file, article regex), and re-run
`python -m app.corpus.ingest`.

---

## Limitations (Milestone 1)

- **Use mode** (Reviewer, Citation Verifier, Counter-Proposal Drafter, Synthesis;
  Loops 4–5) returns HTTP 501 — scheduled for Milestone 2.
- Corpus seeds (`Labour Law`, `PDPL`) are **public placeholder excerpts** pending
  the founder's official full texts; swap them in as a data drop.
- `OFFLINE_MODE` uses deterministic stubs so the system runs without Compass
  credentials; live behaviour requires real creds.
- Commercial Transactions Law and Civil Transactions Law are configured but their
  texts are added later (data drop).
