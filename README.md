# Wakeel — Sovereign UAE Regulatory Agent Factory

> Turn your organization's interpretation of UAE regulation into deployable AI copilots.
> Describe the workflow in English or Arabic, debate the requirements with our agent council, and ship a specialized compliance assistant tuned to your org's stance — without writing code.

---

## What this is

Wakeel is a multi-agent system that operates in two modes:

1. **Build mode** — an agent council (Interviewer, two Stance Debaters, Architect, Builder, Validator) interviews a user about their regulatory workflow, debates strict-vs-practical interpretations, and ships a configured copilot.
2. **Use mode** — the minted copilot (Reviewer + Citation Verifier + Counter-Proposal Drafter + Synthesis) reviews documents against the org's tuned interpretation, verifies every citation against the corpus, and drafts compliant counter-proposals.

10 agents. 5 explicit feedback loops. Single API endpoint switched by a `mode` field. Streamlit chat UI on a separate port.

## Why this matters

Public statutes are public. Anyone can read UAE Federal Decree-Law 45 of 2021 (PDPL) or Federal Decree-Law 33 of 2021 (Labour Law). But how a bank reads them is different from how a hospital reads them, and different again from how a fintech reads them. That difference — tacit, undocumented, living in senior counsel's heads — is where the value is.

Wakeel encodes that institutional interpretation layer as deployable agents.

## Architecture at a glance

```
BUILD MODE                              USE MODE (the copilot)
─────────────                           ─────────────────────
                                        
[User intake]                           [Document in]
     ↓                                       ↓
 Interviewer ←──── (Loop 3) ─────       Reviewer ←────── (Loop 4) ────┐
     ↓                                       ↓                        │
 Debater A ↔ Debater B (Loop 1)         Citation Verifier ────────────┘
     ↓                                       ↓ (verified findings)
 Architect                              Counter-Proposal Drafter
     ↓                                       ↓  ↑
 Builder ←──── (Loop 2) ────             ────┘ (Loop 5)
     ↓                                       ↓
 Validator                              Synthesis
     ↓                                       ↓
[copilot_id + config]                   [findings + citations + audit]
```

See `docs/architecture.md` for the full agent topology and feedback-loop semantics.

## Quick start

### Prerequisites
- Python 3.11
- Docker (optional but recommended)
- An OpenAI-protocol compatible API endpoint and key (Compass, OpenAI, or compatible)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and OPENAI_BASE_URL
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Drop statute corpus

Put the four UAE statute texts (PDF or TXT) in `data/corpus/` — see `data/corpus/README.md` for required files.

### 4. Ingest corpus

```bash
python scripts/ingest_corpus.py
```

### 5. Run

API:
```bash
python run.py
# API available at http://localhost:8000
```

UI (separate terminal):
```bash
streamlit run run_ui.py --server.port 8001
# UI available at http://localhost:8001
```

### Or run with Docker

```bash
docker build -t wakeel .
docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel
```

## API

Single endpoint, two modes.

### Build a copilot

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d @input_examples/build_mode_01_en.json
```

### Use a copilot

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d @input_examples/use_mode_01.json
```

See `input_examples/` for full request shapes and `output_examples/` for response shapes.

## Project layout

```
wakeel/
├── app/                     # Core agent logic
│   ├── llm.py              # Shared LLM wrapper (SOW Section 6)
│   ├── state.py            # LangGraph state types
│   ├── graph.py            # Agent topology and routing
│   ├── agents/             # 10 agent implementations
│   ├── corpus/             # Statute ingestion + retrieval
│   ├── copilots/           # Templates (NDA in v1.0)
│   └── org/                # Org adaptation config
├── data/
│   ├── corpus/             # Statute files (gitignored except README)
│   ├── orgs/               # Sample org configs
│   └── copilots/           # Generated copilot configs (gitignored)
├── docs/                   # Architecture, LLM client guide
├── input_examples/         # Sample requests (3 per mode)
├── output_examples/        # Sample responses (3 per mode)
├── logs/                   # Audit trail JSONL files
├── demos/                  # Technical walkthrough videos
├── tests/                  # Unit and smoke tests
├── run.py                  # API entry point (port 8000)
├── run_ui.py               # Streamlit UI entry point (port 8001)
├── requirements.txt
├── Dockerfile
├── .env.example
└── metadata.json
```

## Multi-agent collaboration

This is the heart of the system. Five explicit feedback loops, not a pipeline:

| Loop | Mode | Agents | What happens |
| --- | --- | --- | --- |
| 1. Stance Debate | Build | Debater A ↔ Debater B → Architect | 2–3 rounds of strict-vs-practical argument before synthesis |
| 2. Validation Rejection | Build | Validator ↔ Builder | Validator rejects underperforming copilots; Builder revises |
| 3. Requirements Clarification | Build | Architect → Interviewer | Architect escalates ambiguity rather than guessing |
| 4. Citation Rejection | Use | Reviewer ↔ Citation Verifier | Verifier rejects hallucinated citations; Reviewer must re-cite |
| 5. Counter-Proposal Critique | Use | Drafter ↔ Reviewer | Reviewer rejects drafts that still violate the law |

Every loop iteration is logged to `logs/run_<run_id>.jsonl` with agent name, action, decision, and reasoning. Max 3 iterations per loop (configurable via env vars).

## Arabic support (v1.0)

- **In:** the Interviewer agent accepts Arabic input. The Streamlit UI renders RTL on input fields.
- **Out:** v1.0 ships English-only review output. Arabic document review (use mode in Arabic) is v1.1.

## Limitations (v1.0)

- One copilot template family: document review (NDA in v1.0; employment and services agreements deferred)
- UAE Federal law only — DIFC and ADGM in v1.1+
- Single-tenant; no authentication
- Override logging is file-based; continuous learning from overrides is v1.1+
- English-only output

## License

TBD — to be set by founder before public release.

## Acknowledgements

Built for the Agentathon, June 2026.
