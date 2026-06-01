# Wakeel — LLM Client Architecture

This document explains the LLM wrapper pattern implemented in `app/llm.py`.
Read this before writing any agent code.

## The rule

**Every LLM call in Wakeel goes through one of two functions:**

```python
from app.llm import chat, embed

# Chat completions
result = chat(agent_name="reviewer", tier="reasoning", messages=[...])

# Embeddings
vectors = embed(["text1", "text2"], agent_name="corpus_ingest")
```

**Do not:**
- Import `openai` directly in any agent file
- Instantiate `OpenAI()` anywhere outside `app/llm.py`
- Pass a model name (e.g. `"gpt-4.1"`) directly — always use `tier`
- Call `chat()` without `agent_name`

This is a hard architectural rule, not a guideline. It exists for four reasons:

## Why the wrapper exists

### 1. Provider-agnosticism

Agents request a tier (`"standard"` or `"reasoning"`). The wrapper resolves
tier to model name via env vars (`DEFAULT_MODEL`, `REASONING_MODEL`). To swap
providers — including testing Jais for the Interviewer agent — we change env
vars only. Zero code changes.

```bash
# Test Jais on the Interviewer agent without touching code:
AGENT_MODEL_OVERRIDE_INTERVIEWER=jais-30b-chat python run.py
```

### 2. Audit trail attribution

Every LLM call must be attributable to the agent that made it. The
`agent_name` parameter is required for this. Audit logs include:

```json
{
  "timestamp": 1716300000.123,
  "agent": "debater_strict",
  "model": "gpt-5.1",
  "tier": "reasoning",
  "latency_seconds": 2.341,
  "input_tokens": 847,
  "output_tokens": 312,
  "status": "ok"
}
```

These logs are the evidence of multi-agent collaboration that reviewers and
judges look for. They live in `logs/audit.jsonl`.

### 3. Centralized retry and rate-limit handling

The wrapper uses `tenacity` to retry transient errors (rate limits, timeouts,
connection errors) with exponential backoff. Tunable via env vars:

- `LLM_RETRY_ATTEMPTS` (default 4)
- `LLM_RETRY_MIN_WAIT_SECONDS` (default 2)
- `LLM_RETRY_MAX_WAIT_SECONDS` (default 30)

If we discover an agent that hits rate limits more aggressively, we add retry
nuance in one place. No agent file changes.

### 4. Sample mode for development quota discipline

When `SAMPLE_MODE=true`, the wrapper caps `max_tokens` at 300 by default. This
prevents accidental quota burn during development. To opt out for a specific
call, pass `max_tokens` explicitly.

## Tier → model mapping

| Tier | Default model | Used by |
| --- | --- | --- |
| `standard` | `gpt-4.1` | Interviewer, Builder, Validator, Citation Verifier, Counter-Proposal Drafter, Synthesis |
| `reasoning` | `gpt-5.1` | Stance Debater A, Stance Debater B, Architect, Reviewer |
| `embedding` | `text-embedding-3-large` | Corpus ingestion, retrieval |

Use `reasoning` when the agent must:
- Synthesize across multiple inputs
- Weigh tradeoffs
- Produce structured judgments under uncertainty

Use `standard` when the agent is doing:
- Structured extraction
- Pattern matching
- Drafting from templates
- Deterministic verification

Don't use `reasoning` by default — it costs more and is slower.

## Per-agent model overrides

If we need to test a different model for one agent (e.g. Jais for Arabic
intake), set an env var:

```
AGENT_MODEL_OVERRIDE_INTERVIEWER=jais-30b-chat
```

The variable name is `AGENT_MODEL_OVERRIDE_{AGENT_NAME_UPPER}`. The wrapper
checks for an override before resolving the tier.

This is the mechanism to test Jais on the Interviewer agent Day 1 without
restructuring code.

## Smoke test

Run `app/llm.py` directly to verify your LLM connection works:

```bash
python -m app.llm
```

Expected output:
```
Configured base URL: https://compass.core42.ai/v1
Configured models: {'standard': 'gpt-4.1', 'reasoning': 'gpt-5.1', 'embedding': 'text-embedding-3-large'}
Sample mode: True

Response: OK
Model: gpt-4.1, Tokens in/out: 14/1
Latency: 0.42s

Smoke test PASSED
```

Do this on Day 1 before writing any agent code. If this fails, no agent will
work.

## Reference implementation

See `app/llm.py` for the full source. The interface contract:

```python
def chat(
    agent_name: str,        # required, for audit trail
    tier: str,              # "standard" | "reasoning"
    messages: list[dict],   # OpenAI chat format
    **kwargs                # passed through (temperature, max_tokens, etc.)
) -> ChatResult: ...

def embed(
    texts: list[str],
    agent_name: str = "system"
) -> list[list[float]]: ...
```
