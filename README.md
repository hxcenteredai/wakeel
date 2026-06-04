# Wakeel — Sovereign Regulatory Agent Factory

Wakeel turns an organization's interpretation of UAE regulation into deployable
AI copilots. **Build mode** interviews a user (English or Arabic), debates the
regulatory stance with an agent council, and instantiates a configured copilot.
**Use mode** runs that copilot over documents — verifying every citation
against the statute corpus and drafting counter-proposals for flagged clauses.

This repository delivers **Milestone 1 (Build mode end-to-end)** plus
**Milestone 2 (Use mode + delivery)** — see the [M2 evidence doc](docs/use-mode-evidence.md)
for the gate-by-gate audit. The technical walkthrough videos referenced by
Amendment §3 criterion 6 live in [`demos/`](demos/RUNBOOK.md).

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
                                  │
                                  ▼  (config persisted to data/copilots/)
POST /run (mode=use)    ──►  LangGraph use graph
                               Reviewer (emits findings)
                                  │
                                  ▼
                               Citation Verifier         ← Loop 4 (per finding)
                                  │   ▲                    exact-text corpus lookup;
                                  ▼   │                    hallucinated cites rejected,
                               Reviewer re-cite           Reviewer re-cites from candidates
                                  │
                                  ▼
                               Counter-Proposal Drafter
                                  │   ▲
                                  ▼   │                  ← Loop 5 (per finding)
                               Reviewer-as-critic
                                  │
                                  ▼
                               Synthesis
                                  │
                                  ▼
                          findings (verified) + summary + audit_trail
```

- **10-agent system** — 6 build-mode + 4 use-mode (Reviewer, Citation Verifier, Counter-Proposal Drafter, Synthesis).
- **All LLM access** goes through one wrapper, `app/llm.py` (SOW §6).
- **Corpus**: 4 UAE Federal statutes (Labour Law, PDPL, Commercial Transactions, Civil Transactions) ingested into ChromaDB, chunked by article. **Citation Verifier uses exact-text retrieval** so hallucinated cites are rejected with the real article text returned.
- **Audit trail**: every agent action + loop iteration logged to JSONL in `logs/`. Canonical evidence in `logs/samples/`.

See [`docs/architecture.md`](docs/architecture.md) for the full topology and the
LLM-client design.

---

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — see profiles below. Leave OPENAI_API_KEY empty for fully OFFLINE mode.
```

**Developer (OpenAI direct)** — day-to-day builds:

```env
OPENAI_API_KEY=<your OpenAI direct key>
OPENAI_BASE_URL=https://api.openai.com/v1
```

**Compass verification (UAE)** — M1/M2 acceptance; client runs locally:

```env
OPENAI_BASE_URL=https://api.core42.ai/v1
OPENAI_API_KEY=<kept on the client side only>
```

**Model tiers** (confirmed on Compass; defaults in `.env.example`):

| Tier | Env var | Model |
|---|---|---|
| Standard | `DEFAULT_MODEL` | `gpt-4.1` |
| Reasoning | `REASONING_MODEL` | `gpt-5.1` |
| Embedding | `EMBEDDING_MODEL` | `text-embedding-3-large` |

Same code, different endpoint — SOW §6 wrapper only. Optional sovereign-AI demo:
set `INTERVIEWER_MODEL=G42-INCEPTION-GPT41-MSA` on Compass (per-agent env override;
no code change).

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | Provider endpoint (OpenAI direct or Compass). |
| `DEFAULT_MODEL` / `REASONING_MODEL` / `EMBEDDING_MODEL` | Model per tier (see table). |
| `INTERVIEWER_MODEL` | Optional dedicated Interviewer model (e.g. Inception MSA on Compass). |
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

### Build mode — mint a copilot

```bash
curl -X POST localhost:8000/run -H 'Content-Type: application/json' \
  -d '{"mode":"build","intake":{"workflow_description":"Review vendor NDAs against our conservative PDPL stance","language":"en"}}'
```

Response: `run_id`, `copilot_id`, `config`, `validation_results`, `audit_trail`,
`interviewer_response`. See `output_examples/build_mode/` for full samples.

### Use mode — review a document

The `copilot_id` from a build run is persisted to `data/copilots/` and can be
replayed against any document:

```bash
curl -X POST localhost:8000/run -H 'Content-Type: application/json' \
  -d '{
    "mode":"use",
    "copilot_id":"cp_<from build>",
    "document":{"type":"text","content":"<NDA body text>"}
  }'
```

Response: `run_id`, `findings` (each with verified `citation`), `summary`
(counts, risk buckets, recommendation), `audit_trail`. See
`output_examples/use_mode/` for three full samples (aggressive vendor NDA,
balanced commercial NDA, data-broker NDA).

```bash
# List built copilots
curl localhost:8000/copilots
```

---

## Arabic usage notes

- The Interviewer accepts **English or Arabic** input and replies in the user's
  language (`interviewer_response`). All downstream structured fields are English.
- Send `intake.language = "ar"`; the UI auto-detects Arabic script and renders the
  input/messages **right-to-left**.
- **Dedicated Arabic model**: set `INTERVIEWER_MODEL` (e.g.
  `G42-INCEPTION-GPT41-MSA` on Compass) — per-agent env override, no code change.
  Otherwise the Interviewer uses `DEFAULT_MODEL` with Arabic-aware prompting.
- Arabic build examples:
  - `input_examples/build_mode/03_arabic_nda.json` (vendor NDAs, fintech)
  - `input_examples/build_02_hospital_nda_ar.json` (hospital — M2 Amendment §3 criterion 4)

---

## Feedback loops (logged)

| Loop | Where | Behaviour |
|---|---|---|
| **Loop 1** — Stance debate | Debater A/B ⇄ Architect | ≥2 rounds; Architect can request more (cap 3). |
| **Loop 2** — Validation reject | Validator → Builder | Reject substandard config; revise (cap 3). |
| **Loop 3** — Clarification | Architect → Interviewer | Escalate ambiguity for follow-up (cap 2). |
| **Loop 4** — Citation rejection | Reviewer ⇄ Citation Verifier | Hallucinated cite → exact-text lookup fails → Reviewer re-cites from candidates (cap 3 per finding). |
| **Loop 5** — Counter-proposal critique | Drafter ⇄ Reviewer-as-critic | Vague/off-statute draft → Reviewer rejects → Drafter revises (cap 3 per finding). |

Sample runs (deterministic, committed evidence):

- `logs/samples/build_mode_run_loops_1_2_3.jsonl`
- `logs/samples/use_mode_run_loops_4_5.jsonl`

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

Runs the M1 customer journeys (Sarah/EN, Ahmed/AR, vague request) and the M2
use-mode journeys (aggressive vendor / balanced commercial / data-broker NDAs),
then prints **Gate-by-gate verdicts for both M1 (Gates 1–6) and M2 (Gates 1–8)**.
Exit code `0` only if all evaluated gates pass.

> **Verifying Milestone 1 from a fresh clone (incl. Compass):** see
> [`docs/verification.md`](docs/verification.md).
> **Verifying Milestone 2 (use mode + Loops 4-5):** see
> [`docs/use-mode-evidence.md`](docs/use-mode-evidence.md).

### 2. Pytest suite

```bash
pytest tests/ -q                 # in-process, OFFLINE by default (fast, deterministic)
WAKEEL_E2E_LIVE=1 pytest tests/  # in-process against the live LLM in .env
WAKEEL_E2E_BASE_URL=http://localhost:8000 pytest tests/   # against a running API
```

- `tests/test_customer_journeys.py` — real user flows (EN/AR/ambiguous, use-mode input contract, validation).
- `tests/test_acceptance_gates.py` — one assertion group per acceptance gate (M1 + M2).

Tests use an isolated vector store and never touch your dev `data/chroma/`.
Loop-3/4/5 firing and Arabic-reply assertions run in offline mode (deterministic);
they are skipped live since they depend on the configured model's JSON fidelity.

## Adding a statute (no code change)

Drop the text file in `data/corpus/`, add an entry to
`data/corpus/corpus_config.json` (law name, file, article regex), and re-run
`python -m app.corpus.ingest`.

---

## Limitations (Milestone 2)

- **All four corpus statutes** ship with **public placeholder excerpts** (clearly marked as such at the top of each text file). Replace with the founder's official full UAE PDFs as a data drop — no code change required.
- `OFFLINE_MODE` uses deterministic stubs so the system runs without Compass
  credentials; live behaviour requires real creds.
- Use-mode **offline stubs are content-aware** (different findings per document) but use hash-based pseudo-embeddings for semantic search — live LLM mode produces semantically richer findings.
- **Arabic output** (counter-proposals, findings, summaries in Arabic) is **out of scope per PRD §5 and SOW §3**; Arabic *intake* is in-scope and works.
- **Walkthrough videos in `demos/`** are placeholder MP4 stubs at commit time; replace with the real 60–90s recordings per [`demos/RUNBOOK.md`](demos/RUNBOOK.md).
