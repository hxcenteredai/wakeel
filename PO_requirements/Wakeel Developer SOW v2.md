# Wakeel — Developer Statement of Work

**SOW v2.0** *(supersedes v1.0)*
**Engagement window:** May 22 – May 30, 2026
**Hard delivery deadline:** May 30, 2026, 23:59 UAE time
**Effective build days:** ~5 working days
**Reference document:** `Wakeel_PRD_v3.md`

**Changes from v1.0:**

- Arabic input support added to scope (Interviewer agent)
- Streamlit chat UI on port 8001 added to scope
- Explicit LLM client implementation requirements (new Section 6)
- Updated daily milestones to reflect added scope
- Corpus expanded from 2 to 4 UAE Federal statutes (Labour, PDPL, Commercial Transactions, Civil Transactions)
- 3 technical walkthrough videos added to scope (raw recordings; polished judge-facing video remains with founder + Claude)

-----

## 1. Engagement summary

You are building the v1.0 of Wakeel — a multi-agent system that operates in two modes:

1. **Build mode**: an agent council interviews a user about a regulatory workflow, debates the stance, and instantiates a configured copilot. **The interviewer accepts Arabic and English input.**
1. **Use mode**: the instantiated copilot reviews documents against the org’s tuned interpretation, verifies citations, and drafts counter-proposals.

10 agents, 5 feedback loops, single API endpoint, Streamlit chat UI. Python, LangGraph, FastAPI, ChromaDB, Docker.

**Read before quoting:** `Wakeel_PRD_v3.md` sections 5–10 and 17. That is the full functional spec. This SOW is the contract scope and delivery terms.

-----

## 2. Scope of work — what you are building

By 23:59 UAE on May 30, you must deliver the following in the GitHub repo:

### Core system

- All 10 agents implemented and orchestrated via LangGraph (PRD section 7)
- All 5 feedback loops working and logged (PRD section 7)
- `POST /run` endpoint on port 8000 supporting both `mode: "build"` and `mode: "use"`
- Shared LLM client wrapper per Section 6 of this SOW
- Vector store (ChromaDB) with corpus ingestion script
- Audit trail logging to JSONL files in `logs/`

### Arabic intake support

- Interviewer agent accepts input in English or Arabic
- Interviewer responds in the language the user wrote in
- Downstream agents (Debaters, Architect, Builder, Validator) operate in English using the Interviewer’s translated structured output
- At least 3 Arabic test inputs in `input_examples/build_mode/` with corresponding outputs
- **Jais availability:** test Day 1. If exposed via the configured LLM endpoint, use it for the Interviewer. If not, fall back to the standard reasoning model with Arabic-aware prompting. Notify founder + Claude same day; do not delay the build over this.

### Chat UI (port 8001)

- Streamlit single-page app, runnable via `python run_ui.py` or `streamlit run run_ui.py`
- Mode toggle at top (Build / Use)
- Chat interface using `st.chat_message` and `st.chat_input` primitives
- Build mode: user types description (Arabic or English) → UI calls `/run` → streams audit trail to right sidebar → displays final `copilot_id` and config summary
- Use mode: dropdown to select an existing `copilot_id` → text paste or file upload for document → calls `/run` → streams findings into chat
- Right sidebar displays audit trail entries as they arrive
- Right-to-left rendering supported on input field when Arabic detected
- No authentication
- Configurable backend URL via env var (default `http://localhost:8000`)

### Corpus

- Ingestion of four UAE Federal statutes (provided by founder as PDF or text):
  - Federal Decree-Law 33 of 2021 (Labour Law) — full text
  - Federal Decree-Law 45 of 2021 (Personal Data Protection Law) — full text
  - Federal Law 18 of 1993 (Commercial Transactions Law) — key chapters on contract formation, commercial obligations, and confidentiality
  - Federal Law 5 of 1985 (Civil Transactions Law) — contract formation and general obligations articles only
- Chunking by article with metadata (law name, article number, exact text)
- Embeddings via the configured embedding model
- Ingestion pipeline must be generic — adding a fifth statute later must be a config + data drop, not a code change

### Copilot template

- One working template end-to-end: **NDA review copilot**
- Template includes: system prompts, output schema, retrieval rules, configurable risk thresholds
- Configurable via the org-adaptation JSON (PRD section 8)

### Infrastructure

- `Dockerfile` that builds cleanly and runs both API (port 8000) and UI (port 8001)
- `requirements.txt` with pinned versions
- `.env.example` with all required environment variables, no real secrets
- GitLab repo as source of truth; GitLab → GitHub auto-mirror live from Day 1

### Documentation

- `README.md`: setup, run, architecture, examples, limitations, Arabic usage notes
- `docs/architecture.md`: agent topology diagram + loop documentation + LLM client architecture
- Inline code comments on non-obvious logic
- 3+ input examples per mode (6 total) in `input_examples/`, including ≥1 Arabic build-mode example
- 3+ output examples per mode (6 total) in `output_examples/`
- Sample run logs in `logs/` demonstrating all 5 feedback loops

### Technical walkthrough videos

- 3 short screen-recorded videos demonstrating system functionality, delivered in `demos/`:
1. **Build mode walkthrough** (60–90s): full factory run from intake to copilot delivery, with visible loop firings in the audit trail sidebar
1. **Use mode walkthrough** (60–90s): document submission through to findings — **must capture the Citation Verifier rejection moment**
1. **Arabic intake walkthrough** (60–90s): Interviewer agent processing an Arabic input end-to-end
- Format: raw screen recording, MP4, 1080p
- Voiceover optional — silent recordings with on-screen text or subtitles are acceptable
- No editing or post-production required
- Referenced from `README.md`
- **Note:** these are technical evidence of system functionality. The polished 2–3 minute judge-facing demo video is produced separately by founder + Claude using these as source material.

-----

## 3. Out of scope — what you are NOT building

1. Arabic *output* — counter-proposals, findings, summaries remain English in v1
1. Bilingual document review in use mode (Arabic NDAs)
1. Authentication, user accounts, multi-tenancy
1. Free-zone law coverage (DIFC, ADGM)
1. Document types other than NDA in v1 (employment and services agreements deferred)
1. Continuous learning from user overrides (logged in v1, not fed back)
1. Real-time collaboration features
1. CI/CD pipelines beyond the GitLab→GitHub mirror
1. Production-grade observability (Prometheus, Grafana, etc.)
1. Hosting, deployment, DNS — local Docker only
1. The polished 2–3 minute judge-facing demo video — founder + Claude own this Jun 3–4 (developer produces raw technical walkthroughs per Section 2)
1. The `metadata.json` and submission portal artifacts — handled by founder + Claude Jun 5
1. UI polish beyond the spec in Section 2 — no custom CSS, no animations, no dark mode

If a feature request lands during the build that isn’t in Section 2, it’s out of scope unless explicitly added in writing with a corresponding deadline impact assessment.

-----

## 4. Deliverables and milestones

|Date             |Day|Deliverable                                                                                                                                                        |
|-----------------|---|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|Thu May 22       |1  |Repo scaffolded; LLM client wrapper working; GitLab→GitHub mirror live; LangGraph hello-world; Streamlit UI shell renders with mode toggle                         |
|Fri May 23       |2  |Corpus ingested and embedded; Interviewer agent working (English + Arabic); Debaters A & B; Loop 1 firing                                                          |
|Sat May 24       |3  |Build-mode complete: Architect + Builder + Validator; Loops 2 & 3; full build mode runnable via API and visible in UI                                              |
|Sun May 25       |4  |Use mode agents: Reviewer + Citation Verifier; Loop 4 firing on test NDA                                                                                           |
|Mon–Thu May 26–29|Eid|No work expected. Light cleanup acceptable.                                                                                                                        |
|Fri May 30       |5  |**DELIVERY:** Counter-Proposal Drafter + Synthesis; Loop 5; full UI polished for both modes; all documentation; all examples; clean Docker build of both API and UI|

### Daily check-ins

End-of-day on May 22, 23, 24, 25 — 5-minute Loom video or written summary of milestone status and any blockers.

### Risk-trigger reviews

- **May 24 EOD:** if Days 1–3 are not delivered, founder + Claude meet with you to assess scope cuts.
- **May 28 (mid-Eid):** optional 30-min call to confirm May 30 is on track.

-----

## 5. Acceptance criteria for May 30 delivery

All of the following must be true at 23:59 UAE on May 30:

- [ ] GitHub repo (mirror of GitLab `main`) is current and publicly viewable on request
- [ ] `docker build -t wakeel .` succeeds from a clean clone
- [ ] `docker run -p 8000:8000 -p 8001:8001 wakeel` starts both API and UI with no errors
- [ ] `POST /run` with `mode: "build"` returns valid response (including for an Arabic input)
- [ ] `POST /run` with `mode: "use"` returns valid response with findings, citations, audit trail
- [ ] Streamlit UI at `http://localhost:8001` loads, supports mode toggle, accepts input, renders audit trail
- [ ] Streamlit UI accepts Arabic input in build mode and the Interviewer responds appropriately
- [ ] `logs/` contains at least 2 sample runs (one per mode) showing all 5 feedback loops triggered
- [ ] 6 input examples and 6 output examples present and internally consistent (including ≥1 Arabic build example)
- [ ] `README.md` covers setup, run, architecture, examples, Arabic usage, limitations
- [ ] `docs/architecture.md` includes agent topology diagram and LLM client architecture diagram
- [ ] No real API keys or secrets committed anywhere in the repo or its history
- [ ] `requirements.txt` has pinned versions
- [ ] 3 technical walkthrough videos delivered in `demos/` per Section 2 (build mode, use mode with citation rejection, Arabic intake)

Acceptance review by founder + Claude on May 31. Any failures are bug fixes under this engagement, not new work.

-----

## 6. LLM client implementation requirements (explicit)

All LLM access in the codebase MUST go through a single shared client wrapper. This is non-negotiable. Reasons: (1) provider-agnostic so we can swap endpoints via env vars, (2) one place for logging, retries, sample-mode handling, (3) consistent attribution of calls to agents in the audit trail.

### Required structure: `app/llm.py`

The developer must implement a wrapper with these exact responsibilities:

**1. Single shared client.** One `OpenAI` client instance initialized at module load from environment variables. No per-agent instantiation.

```python
from openai import OpenAI
import os

_client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
)
```

**2. Model selection by tier, not by name.** Agents request a tier — `"standard"` or `"reasoning"`. The wrapper resolves to a model name via env vars.

```python
MODELS = {
    "standard": os.environ.get("DEFAULT_MODEL", "gpt-4.1"),
    "reasoning": os.environ.get("REASONING_MODEL", "gpt-5.1"),
    "embedding": os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large"),
}
```

This means we can swap underlying models (including testing Jais for the Interviewer) by changing env vars only, without touching agent code.

**3. Retry decorator.** All chat completions wrapped in exponential backoff retries on rate limit and transient API errors. Recommended: `tenacity` library, 4 attempts max, exponential 2s–30s.

**4. Sample mode handling.** When `SAMPLE_MODE=true` in env, cap `max_tokens` to a small value (e.g., 300) by default if not specified by the caller. This is for development quota discipline.

**5. Mandatory `chat()` function signature:**

```python
def chat(agent_name: str, tier: str, messages: list, **kwargs) -> ChatCompletion:
    """
    All chat completions in the codebase go through this function.
    Agents must pass their name for audit trail attribution.
    """
```

**6. Mandatory `embed()` function signature:**

```python
def embed(texts: list[str]) -> list[list[float]]:
    """All embedding calls in the codebase go through this function."""
```

**7. Logging on every call.** Every call must emit a structured log record (JSONL) with:

- `timestamp`
- `agent` (the `agent_name` parameter)
- `model` (resolved model name)
- `tier`
- `latency_seconds`
- `input_tokens` (from `usage.prompt_tokens`)
- `output_tokens` (from `usage.completion_tokens`)
- `status` (`ok` or `error`)
- `error_message` if status is error

These logs are part of the audit trail that judges and reviewers use to verify multi-agent collaboration.

**8. Rules for agent code:**

- Agents NEVER import `OpenAI` directly or instantiate a client
- Agents ALWAYS call `chat(agent_name, tier, messages)` or `embed(texts)`
- Agents request tier, never model name
- `agent_name` parameter is required, not optional

**9. Environment variables (must be documented in `.env.example`):**

```
OPENAI_API_KEY=
OPENAI_BASE_URL=
DEFAULT_MODEL=gpt-4.1
REASONING_MODEL=gpt-5.1
EMBEDDING_MODEL=text-embedding-3-large
SAMPLE_MODE=true
```

A reference implementation is acceptable as long as all 9 properties above are met.

-----

## 7. Other technical requirements

|Layer              |Required                                        |
|-------------------|------------------------------------------------|
|Language           |Python 3.11                                     |
|Agent orchestration|LangGraph                                       |
|API framework      |FastAPI                                         |
|UI framework       |Streamlit ≥ 1.30                                |
|Vector store       |ChromaDB (file-backed, local)                   |
|LLM client         |OpenAI Python SDK via the wrapper in Section 6  |
|Embeddings         |text-embedding-3-large (configurable via env)   |
|Container          |Docker                                          |
|Logging            |Python `logging` module, JSONL output to `logs/`|
|Ports              |8000 (API), 8001 (UI). No hardcoded other ports.|

-----

## 8. Working norms

- **Communication:** Founder + Claude available daily via Slack/WhatsApp during UAE working hours
- **Daily updates:** End-of-day on May 22, 23, 24, 25 — short Loom or written summary of milestone status + blockers
- **Blocker SLA:** If stuck more than 4 hours on a single issue, surface it. We pay for build velocity, not debugging patience.
- **Code review:** Founder + Claude review GitLab repo daily. PRs not required; direct commits to `main` fine. Atomic commits, message-prefixed (`feat:`, `fix:`, `docs:`)
- **Questions:** No question too small. Ambiguity not surfaced becomes your problem.
- **Eid:** no work expected May 26–29. Founder won’t message during that window.

-----

## 9. What the founder provides

- LLM API credentials (test creds Day 1)
- GitLab and GitHub repo access provisioned before Day 1
- Source PDFs/text for the UAE Federal statutes
- Sample NDAs for development (3–5 redacted realistic examples)
- Sample Arabic intake descriptions for testing the Interviewer
- Customer validation feedback (compliance/legal experts review WIP Jun 1–4)
- Daily availability for questions and scope decisions
- PRD v3 as the functional spec
- Claude as a technical sounding board

-----

## 10. Commercial structure

Total engagement value: **TBD (your quote).**

Suggested milestone-based payment structure:

|Milestone                                 |Payment|
|------------------------------------------|-------|
|Signature of SOW                          |30%    |
|Day 4 (May 25) milestone hit per Section 4|30%    |
|May 30 acceptance per Section 5           |40%    |

Currency: AED. Payment via bank transfer or other mutually agreed method within 7 days of milestone.

**Intellectual property:** all code, documentation, and artifacts produced under this engagement are property of the founder/Wakeel entity. Developer retains right to mention engagement in portfolio and reference the public GitHub repo.

**NDA:** a one-page mutual NDA can be signed if requested before code access.

-----

## 11. Questions for the developer (please answer when quoting)

1. **Stack comfort:** confirm comfort with LangGraph, FastAPI, ChromaDB, Streamlit chat primitives, Docker, OpenAI-SDK-style LLM clients. Flag weak points.
1. **Arabic comfort:** confirm you can implement RTL rendering in Streamlit input and prompt-engineer for Arabic intake. Native Arabic is not required but familiarity with Arabic text handling helps.
1. **Availability:** confirm substantial full-time commitment May 22–25 and May 30. Light or zero work during Eid is fine.
1. **Timeline feasibility:** confirm the May 30 deadline is feasible, or propose adjustments now (not on May 28).
1. **Your quote:** fixed-price preferred. Hourly with not-to-exceed cap acceptable.
1. **Pushback:** flag any section you’d renegotiate. Better now than later.

-----

## 12. Sign-off

Once both parties sign this SOW and founder confirms 30% milestone payment, the engagement begins.

**Founder:** ___________________ Date: ___________

**Developer:** ___________________ Date: ___________

-----

*End of SOW v2.0.*