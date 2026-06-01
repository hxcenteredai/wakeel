"""
Wakeel — Shared LLM Client Wrapper

Per SOW v2.0 Section 6, this is the SINGLE entry point for all LLM access in the
codebase. Agents request a tier ("standard" or "reasoning"), never a model name.
Every call is logged to the audit trail for multi-agent collaboration evidence.

Rules for agent code:
    - Agents NEVER import `openai` directly or instantiate a client
    - Agents ALWAYS call `chat(agent_name, tier, messages)` or `embed(texts)`
    - Agents request tier, never model name
    - `agent_name` is required, not optional
"""

import os
import time
import json
import logging
from typing import Any
from dataclasses import dataclass

from openai import OpenAI, RateLimitError, APIError, APIConnectionError, APITimeoutError
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep_log,
)

# -----------------------------------------------------------------------------
# Configuration (from environment)
# -----------------------------------------------------------------------------

_API_KEY = os.environ.get("OPENAI_API_KEY")
_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

if not _API_KEY:
    # Don't crash at import time; let the first call fail with a clear message.
    # This makes `pytest --collect-only` and similar workflows work without credentials.
    logging.getLogger("wakeel.llm").warning(
        "OPENAI_API_KEY not set. LLM calls will fail until it is configured."
    )

# Single shared client (SOW Section 6, rule 1)
_client = OpenAI(api_key=_API_KEY or "missing", base_url=_BASE_URL)

# Model selection by tier (SOW Section 6, rule 2)
MODELS = {
    "standard": os.environ.get("DEFAULT_MODEL", "gpt-4.1"),
    "reasoning": os.environ.get("REASONING_MODEL", "gpt-5.1"),
    "embedding": os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large"),
}

# Operational config
SAMPLE_MODE = os.environ.get("SAMPLE_MODE", "false").lower() == "true"
SAMPLE_MODE_MAX_TOKENS = int(os.environ.get("SAMPLE_MODE_MAX_TOKENS", "300"))

_RETRY_ATTEMPTS = int(os.environ.get("LLM_RETRY_ATTEMPTS", "4"))
_RETRY_MIN_WAIT = float(os.environ.get("LLM_RETRY_MIN_WAIT_SECONDS", "2"))
_RETRY_MAX_WAIT = float(os.environ.get("LLM_RETRY_MAX_WAIT_SECONDS", "30"))

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("wakeel.llm")

# Dedicated audit logger writes structured JSONL to logs/
_audit_logger = logging.getLogger("wakeel.llm.audit")


def _emit_audit(record: dict[str, Any]) -> None:
    """Emit one structured audit record (one line of JSONL)."""
    _audit_logger.info(json.dumps(record, default=str))


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

@dataclass
class ChatResult:
    """Wrapper around the raw API response with the bits agents typically want."""
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    raw: Any  # the original ChatCompletion object


def _resolve_model(agent_name: str, tier: str) -> str:
    """Pick the model for an agent. Allows per-agent override via env var."""
    override_key = f"AGENT_MODEL_OVERRIDE_{agent_name.upper()}"
    if override := os.environ.get(override_key):
        return override
    if tier not in MODELS:
        raise ValueError(
            f"Invalid tier '{tier}' for agent '{agent_name}'. "
            f"Must be one of: {list(MODELS.keys())}"
        )
    return MODELS[tier]


@retry(
    wait=wait_exponential(multiplier=1, min=_RETRY_MIN_WAIT, max=_RETRY_MAX_WAIT),
    stop=stop_after_attempt(_RETRY_ATTEMPTS),
    retry=retry_if_exception_type(
        (RateLimitError, APIError, APIConnectionError, APITimeoutError)
    ),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def chat(
    agent_name: str,
    tier: str,
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> ChatResult:
    """
    Single entry point for all chat completions in Wakeel.

    Args:
        agent_name: The agent invoking this call (for audit trail attribution).
                    Required, not optional.
        tier: "standard" or "reasoning" (or "embedding" — handled separately).
        messages: Chat-format messages [{"role": ..., "content": ...}].
        **kwargs: Passed through to the OpenAI client (temperature, max_tokens, etc.).

    Returns:
        ChatResult with parsed fields and original response.

    Raises:
        ValueError if tier is invalid.
        openai.* exceptions after exhausting retries.
    """
    if not agent_name:
        raise ValueError("agent_name is required (SOW Section 6, rule 8)")

    model = _resolve_model(agent_name, tier)

    # Sample-mode token cap (SOW Section 6, rule 4)
    if SAMPLE_MODE and "max_tokens" not in kwargs:
        kwargs["max_tokens"] = SAMPLE_MODE_MAX_TOKENS

    start = time.perf_counter()
    status = "ok"
    error_message = None

    try:
        resp = _client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        latency = time.perf_counter() - start
        result = ChatResult(
            text=resp.choices[0].message.content or "",
            model=model,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            latency_s=latency,
            raw=resp,
        )
    except Exception as e:
        latency = time.perf_counter() - start
        status = "error"
        error_message = f"{type(e).__name__}: {e}"
        # Log the failure then re-raise (tenacity will retry transient errors)
        _emit_audit({
            "timestamp": time.time(),
            "agent": agent_name,
            "model": model,
            "tier": tier,
            "latency_seconds": round(latency, 3),
            "input_tokens": 0,
            "output_tokens": 0,
            "status": status,
            "error_message": error_message,
        })
        raise

    # Log the success (SOW Section 6, rule 7)
    _emit_audit({
        "timestamp": time.time(),
        "agent": agent_name,
        "model": result.model,
        "tier": tier,
        "latency_seconds": round(result.latency_s, 3),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "status": status,
    })

    return result


def embed(texts: list[str], agent_name: str = "system") -> list[list[float]]:
    """
    Single entry point for all embedding calls in Wakeel.

    Args:
        texts: List of strings to embed.
        agent_name: For audit attribution (default "system" for ingestion).

    Returns:
        List of embedding vectors, in input order.
    """
    if not texts:
        return []

    model = MODELS["embedding"]
    start = time.perf_counter()

    try:
        resp = _client.embeddings.create(model=model, input=texts)
        latency = time.perf_counter() - start
        vectors = [d.embedding for d in resp.data]
    except Exception as e:
        latency = time.perf_counter() - start
        _emit_audit({
            "timestamp": time.time(),
            "agent": agent_name,
            "model": model,
            "tier": "embedding",
            "latency_seconds": round(latency, 3),
            "input_count": len(texts),
            "status": "error",
            "error_message": f"{type(e).__name__}: {e}",
        })
        raise

    _emit_audit({
        "timestamp": time.time(),
        "agent": agent_name,
        "model": model,
        "tier": "embedding",
        "latency_seconds": round(latency, 3),
        "input_count": len(texts),
        "status": "ok",
    })

    return vectors


# -----------------------------------------------------------------------------
# Smoke test (run this file directly to verify connection)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Configured base URL: {_BASE_URL}")
    print(f"Configured models: {MODELS}")
    print(f"Sample mode: {SAMPLE_MODE}")

    try:
        result = chat(
            agent_name="smoketest",
            tier="standard",
            messages=[
                {"role": "user", "content": "Reply with exactly: OK"}
            ],
        )
        print(f"\nResponse: {result.text}")
        print(f"Model: {result.model}, Tokens in/out: {result.input_tokens}/{result.output_tokens}")
        print(f"Latency: {result.latency_s:.2f}s")
        print("\nSmoke test PASSED")
    except Exception as e:
        print(f"\nSmoke test FAILED: {e}")
        raise
