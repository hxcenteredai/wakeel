"""Shared agent helpers.

Agents NEVER import OpenAI or instantiate a client. They call ``call_llm`` which
delegates to the shared wrapper (app.llm.chat) and parses structured output.
A compact JSON ``context`` block is appended to the prompt behind the ``@@CTX@@``
marker so the offline stub engine can produce schema-valid responses; live models
simply receive it as additional structured context.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.llm import chat, message_content
from app.offline_stubs import CTX_MARKER


def _coerce_json(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON OBJECT from a model response.

    ALWAYS returns a dict. Real models sometimes emit a bare/quoted JSON value
    (e.g. ``"ok"`` parses to a str) or prose; in those cases we wrap the content
    as ``{"_raw": ...}`` so downstream agent code can always call ``.get()``
    without crashing.
    """
    text = (text or "").strip()
    # Strip code fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"_raw": text}


def _looks_incomplete(parsed: dict[str, Any], expect_keys: list[str] | None) -> bool:
    """True if the parsed object is unusable (bare _raw or missing all keys)."""
    if "_raw" in parsed and len(parsed) == 1:
        return True
    if expect_keys and not any(k in parsed for k in expect_keys):
        return True
    return False


def call_llm(
    *,
    agent_name: str,
    tier: str,
    system: str,
    user: str,
    ctx: dict[str, Any] | None = None,
    parse_json: bool = True,
    expect_keys: list[str] | None = None,
    **kwargs,
) -> tuple[Any, str]:
    """Call the shared LLM wrapper and parse structured output.

    When ``parse_json`` is set, the result is ALWAYS a dict. If the model returns
    unusable output (non-JSON, or missing all ``expect_keys``), we retry once with
    a stricter instruction before giving up — defends the graph against ragged
    output from weaker models without changing agent code.

    Returns (parsed_or_raw, raw_text).
    """
    user_content = user
    if ctx is not None:
        user_content = f"{user}\n\n{CTX_MARKER} {json.dumps(ctx, ensure_ascii=False)}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    completion = chat(agent_name, tier, messages, **kwargs)
    raw = message_content(completion)
    if not parse_json:
        return raw, raw

    parsed = _coerce_json(raw)
    if _looks_incomplete(parsed, expect_keys):
        # One corrective retry: re-ask for a single strict JSON object.
        nudge = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Your previous reply was not a single valid JSON object. "
                    "Respond again with ONLY a JSON object"
                    + (f" containing keys {expect_keys}" if expect_keys else "")
                    + ". No prose, no code fences."
                ),
            },
        ]
        retry = chat(agent_name, tier, nudge, **kwargs)
        retry_raw = message_content(retry)
        retry_parsed = _coerce_json(retry_raw)
        if not _looks_incomplete(retry_parsed, expect_keys):
            return retry_parsed, retry_raw
    return parsed, raw
