"""Shared LLM client wrapper — the single gateway for ALL model access.

Implements every property required by SOW v2 section 6:

  1. Single shared OpenAI client, initialized once at module load from env vars.
  2. Model selection by tier ("standard" / "reasoning" / "embedding"), not name.
  3. Retry decorator: exponential backoff (tenacity), 4 attempts, 2s-30s.
  4. Sample mode: caps response length to a small default when SAMPLE_MODE=true,
     using `max_completion_tokens` (the parameter name required by GPT-5/o-series
     reasoning models and supported by GPT-4.x chat completions on both OpenAI
     direct and Compass). Any caller that passes the legacy `max_tokens` kwarg
     is transparently translated to `max_completion_tokens`.
  5. Mandatory chat(agent_name, tier, messages, **kwargs) signature.
  6. Mandatory embed(texts) signature.
  7. Structured JSONL logging on every call (timestamp, agent, model, tier,
     latency, input/output tokens, status, error_message).
  8. Agents only ever call chat()/embed(); they never import OpenAI.
  9. Env vars per .env.example.

OFFLINE behaviour (Wakeel addition): when OFFLINE_MODE is true (or no API key
is configured) the wrapper returns deterministic stub completions/embeddings so
the full graph, loops, UI, and audit logs run without credentials or quota.
The same logging contract is honoured (status="ok", model tagged "offline-stub").
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app import config
from app.logging_utils import log_llm_call

# --- Mutable runtime state -----------------------------------------------------
# Initialized from env at module load (Property 1/2/9), but reconfigurable at
# runtime so the API key / base URL / models can be changed from the front-end
# without restarting the process (provider flexibility requested by the client).
_state: dict[str, Any] = {
    "api_key": config.OPENAI_API_KEY,
    "base_url": config.OPENAI_BASE_URL,
    "offline": config.OFFLINE_MODE,
    "interviewer_model": config.INTERVIEWER_MODEL,
}

# --- Property 2: model selection by tier ---
MODELS: dict[str, str] = dict(config.MODELS)

# --- Property 1: single shared client (only constructed when online) ---
_client = None


def _build_client():
    """Construct the shared OpenAI client from current runtime state."""
    global _client
    if _state["offline"]:
        _client = None
        return None
    from openai import OpenAI

    _client = OpenAI(api_key=_state["api_key"], base_url=_state["base_url"] or None)
    return _client


_build_client()


def reconfigure(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    models: dict[str, str] | None = None,
    interviewer_model: str | None = None,
    offline: bool | None = None,
) -> dict[str, Any]:
    """Update LLM configuration at runtime and rebuild the shared client.

    Called by the ``POST /config`` endpoint so the API key / endpoint / models
    can be switched from the UI. If ``offline`` is not given, it is inferred from
    whether an API key is present (mirrors the module-load behaviour).
    """
    if api_key is not None:
        _state["api_key"] = api_key.strip()
    if base_url is not None:
        _state["base_url"] = base_url.strip()
    if interviewer_model is not None:
        _state["interviewer_model"] = interviewer_model.strip()
    if models:
        for tier, name in models.items():
            if name:
                MODELS[tier] = name
    if offline is None:
        _state["offline"] = not _state["api_key"]
    else:
        _state["offline"] = bool(offline)
    _build_client()
    return current_config()


def current_config() -> dict[str, Any]:
    """Return the current config with the API key masked (safe to surface in UI)."""
    key = _state["api_key"] or ""
    masked = (key[:4] + "..." + key[-4:]) if len(key) > 8 else ("set" if key else "")
    return {
        "offline_mode": _state["offline"],
        "sample_mode": config.SAMPLE_MODE,
        "base_url": _state["base_url"],
        "api_key_masked": masked,
        "models": dict(MODELS),
        "interviewer_model": _state["interviewer_model"],
    }


def resolve_model(tier: str, *, agent_name: str | None = None) -> str:
    """Resolve a tier (and optionally agent) to a concrete model name.

    The Interviewer can use a dedicated Arabic-capable model (e.g. Jais) via
    INTERVIEWER_MODEL; if unset it falls back to the standard tier model. This
    keeps the Jais-vs-fallback decision a pure config change (SOW section 6).
    """
    if agent_name == "Interviewer" and _state["interviewer_model"]:
        return _state["interviewer_model"]
    if tier not in MODELS:
        raise ValueError(f"Unknown tier '{tier}'. Valid tiers: {list(MODELS)}")
    return MODELS[tier]


# --- Minimal response shapes (used in offline mode; mirror the OpenAI SDK) ---
@dataclass
class _Message:
    content: str
    role: str = "assistant"


@dataclass
class _Choice:
    message: _Message
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class _Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class _ChatCompletion:
    choices: list[_Choice]
    usage: _Usage = field(default_factory=_Usage)
    model: str = "offline-stub"


# --- Property 3: retry decorator (4 attempts, exponential 2s-30s) ---
_retry = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)


@_retry
def _online_chat(model: str, messages: list, **kwargs) -> Any:
    return _client.chat.completions.create(model=model, messages=messages, **kwargs)


@_retry
def _online_embed(model: str, texts: list[str]) -> Any:
    return _client.embeddings.create(model=model, input=texts)


def _estimate_tokens(messages: list) -> int:
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return max(1, chars // 4)


# --- Property 5: mandatory chat() ---
def chat(agent_name: str, tier: str, messages: list, **kwargs) -> Any:
    """All chat completions in the codebase go through this function.

    Agents must pass their name (required) for audit-trail attribution and
    request a tier, never a model name.
    """
    if not agent_name:
        raise ValueError("agent_name is required for every chat() call")

    model = resolve_model(tier, agent_name=agent_name)

    # Property 4: sample-mode token cap.
    #
    # GPT-5 / o-series reasoning models on Compass enforce the new OpenAI
    # parameter name `max_completion_tokens` and reject `max_tokens`.
    # GPT-4.x chat completions accept `max_completion_tokens` too, so we
    # use it unconditionally and translate any legacy `max_tokens` the
    # caller might still pass.
    if "max_tokens" in kwargs and "max_completion_tokens" not in kwargs:
        kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
    if config.SAMPLE_MODE and "max_completion_tokens" not in kwargs:
        kwargs["max_completion_tokens"] = config.SAMPLE_MODE_MAX_TOKENS

    offline = _state["offline"]
    start = time.perf_counter()
    status = "ok"
    error_message: str | None = None
    completion: Any = None
    try:
        if offline:
            from app.offline_stubs import stub_chat

            content = stub_chat(agent_name, messages)
            prompt_tokens = _estimate_tokens(messages)
            completion_tokens = max(1, len(content) // 4)
            completion = _ChatCompletion(
                choices=[_Choice(message=_Message(content=content))],
                usage=_Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
                model=f"offline-stub:{model}",
            )
        else:
            completion = _online_chat(model, messages, **kwargs)
        return completion
    except Exception as exc:  # noqa: BLE001 - logged then re-raised
        status = "error"
        error_message = f"{exc.__class__.__name__}: {exc}"
        raise
    finally:
        latency = time.perf_counter() - start
        usage = getattr(completion, "usage", None)
        log_llm_call(
            agent=agent_name,
            model=f"offline-stub:{model}" if offline else model,
            tier=tier,
            latency_seconds=latency,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            status=status,
            error_message=error_message,
        )


# --- Property 6: mandatory embed() ---
def embed(texts: list[str]) -> list[list[float]]:
    """All embedding calls in the codebase go through this function."""
    model = resolve_model("embedding")
    offline = _state["offline"]
    start = time.perf_counter()
    status = "ok"
    error_message: str | None = None
    vectors: list[list[float]] = []
    try:
        if offline:
            from app.offline_stubs import stub_embed

            vectors = [stub_embed(t) for t in texts]
        else:
            resp = _online_embed(model, texts)
            vectors = [d.embedding for d in resp.data]
        return vectors
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error_message = f"{exc.__class__.__name__}: {exc}"
        raise
    finally:
        latency = time.perf_counter() - start
        log_llm_call(
            agent="embed",
            model=f"offline-stub:{model}" if offline else model,
            tier="embedding",
            latency_seconds=latency,
            input_tokens=sum(len(t) // 4 for t in texts) or None,
            output_tokens=None,
            status=status,
            error_message=error_message,
        )


def message_content(completion: Any) -> str:
    """Convenience accessor used by agents to read the assistant text."""
    return completion.choices[0].message.content or ""


def _smoke_test() -> int:
    """Smoke test (Amendment M1 criterion #1): `python -m app.llm`.

    Sends one request through the wrapper against the configured endpoint and
    prints a valid response. Returns 0 on success, 1 on failure.
    """
    cfg = current_config()
    print("Wakeel LLM smoke test")
    print(f"  mode      : {'OFFLINE (stub)' if cfg['offline_mode'] else 'LIVE'}")
    print(f"  base_url  : {cfg['base_url'] or '(default)'}")
    print(f"  api_key   : {cfg['api_key_masked'] or '(none)'}")
    print(f"  models    : {cfg['models']}")
    try:
        completion = chat(
            "Interviewer",
            "standard",
            [{"role": "user", "content": "Reply with a short confirmation that you are reachable."}],
        )
        text = message_content(completion)
        print(f"  response  : {text[:200]!r}")
        usage = getattr(completion, "usage", None)
        print(
            f"  tokens    : in={getattr(usage, 'prompt_tokens', '?')} "
            f"out={getattr(usage, 'completion_tokens', '?')}"
        )
        assert text and text.strip(), "empty response"
        print("RESULT: OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT: FAILED — {exc.__class__.__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(_smoke_test())
