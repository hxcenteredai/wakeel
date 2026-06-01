"""Streamlit chat UI (port 8001).

Run:  streamlit run run_ui.py --server.port 8001
  or: python run_ui.py   (delegates to the streamlit CLI)

Layout (PRD section 10):
  - Top: mode toggle (Build / Use)
  - Center: chat interface (st.chat_message / st.chat_input)
  - Right: audit-trail panel (per-step expanders) + config/copilot preview
  - Arabic input is detected and rendered right-to-left.
"""
from __future__ import annotations

import os
import re
import sys

import requests
import streamlit as st

BACKEND_URL = os.environ.get("WAKEEL_BACKEND_URL", "http://localhost:8000")
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _looks_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def _call_backend(payload: dict) -> dict:
    resp = requests.post(f"{BACKEND_URL}/run", json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()


def _get_config() -> dict:
    try:
        return requests.get(f"{BACKEND_URL}/config", timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _render_settings_sidebar() -> None:
    """Left sidebar: change the LLM API key / endpoint / models at runtime."""
    with st.sidebar:
        st.header("API settings")
        cfg = _get_config()
        if "error" in cfg:
            st.error(f"Backend unreachable: {cfg['error']}")
        else:
            mode = "OFFLINE (stub)" if cfg.get("offline_mode") else "LIVE"
            st.caption(f"Mode: **{mode}**  ·  key: `{cfg.get('api_key_masked') or 'none'}`")

        with st.form("llm_config"):
            st.caption("Swap provider without restarting. Leave blank to keep current.")
            api_key = st.text_input("API key", type="password", placeholder="sk-... / leave blank to keep")
            base_url = st.text_input("Base URL", value=cfg.get("base_url") or "", placeholder="https://api.openai.com/v1")
            models = cfg.get("models", {}) if isinstance(cfg, dict) else {}
            default_model = st.text_input("Standard model", value=models.get("standard", ""))
            reasoning_model = st.text_input("Reasoning model", value=models.get("reasoning", ""))
            embedding_model = st.text_input("Embedding model", value=models.get("embedding", ""))
            submitted = st.form_submit_button("Apply")

        if submitted:
            payload = {
                "base_url": base_url or None,
                "default_model": default_model or None,
                "reasoning_model": reasoning_model or None,
                "embedding_model": embedding_model or None,
            }
            if api_key:
                payload["api_key"] = api_key
            try:
                r = requests.post(f"{BACKEND_URL}/config", json=payload, timeout=30)
                r.raise_for_status()
                st.success("Applied. New config active.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to apply: {exc}")


def _render_audit(container, audit_trail: list[dict]) -> None:
    container.subheader("Audit trail")
    if not audit_trail:
        container.caption("No steps yet. Submit a request to see the agent council run.")
        return
    loops_seen = sorted({e["loop"] for e in audit_trail if e.get("loop")})
    if loops_seen:
        container.success("Loops fired: " + ", ".join(loops_seen))
    for i, entry in enumerate(audit_trail, 1):
        label = f"{i}. {entry['agent']} — {entry['action']}"
        if entry.get("loop"):
            label += f"  [{entry['loop']}]"
        with container.expander(label, expanded=False):
            st.write(f"**Decision:** {entry.get('decision') or '—'}")
            st.write(f"**Reason:** {entry.get('reason') or '—'}")
            if entry.get("details"):
                st.json(entry["details"])


def _build_mode(chat_col, side_col) -> None:
    with chat_col:
        st.caption("Describe the regulatory workflow you want a copilot for (English or Arabic).")
        for msg in st.session_state.build_messages:
            with st.chat_message(msg["role"]):
                if msg.get("rtl"):
                    st.markdown(
                        f"<div dir='rtl' style='text-align:right'>{msg['content']}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(msg["content"])

    prompt = st.chat_input("e.g. Review vendor NDAs against our fintech data-handling stance")
    if prompt:
        rtl = _looks_arabic(prompt)
        st.session_state.build_messages.append({"role": "user", "content": prompt, "rtl": rtl})
        with chat_col:
            with st.chat_message("user"):
                if rtl:
                    st.markdown(
                        f"<div dir='rtl' style='text-align:right'>{prompt}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(prompt)

        payload = {
            "mode": "build",
            "intake": {
                "workflow_description": prompt,
                "language": "ar" if rtl else "en",
            },
        }
        with st.spinner("Agent council running…"):
            try:
                result = _call_backend(payload)
            except Exception as exc:  # noqa: BLE001
                with chat_col:
                    st.error(f"Backend error: {exc}")
                return

        st.session_state.build_audit = result.get("audit_trail", [])
        st.session_state.last_copilot_id = result.get("copilot_id")
        st.session_state.last_config = result.get("config", {})

        interviewer_response = result.get("interviewer_response", "")
        summary = (
            f"**Copilot built:** `{result.get('copilot_id')}`\n\n"
            f"**Validation:** {result.get('validation_results', {}).get('score', '—')} "
            f"(passed={result.get('validation_results', {}).get('passed')})"
        )
        if interviewer_response:
            st.session_state.build_messages.append(
                {"role": "assistant", "content": interviewer_response, "rtl": _looks_arabic(interviewer_response)}
            )
        st.session_state.build_messages.append({"role": "assistant", "content": summary})
        st.rerun()

    with side_col:
        _render_audit(st, st.session_state.build_audit)
        if st.session_state.get("last_copilot_id"):
            st.subheader("Copilot config")
            st.code(st.session_state.last_copilot_id)
            st.json(st.session_state.last_config)


def _use_mode(chat_col, side_col) -> None:
    with chat_col:
        st.info(
            "Use mode (document review) lands in Milestone 2: Reviewer + Citation "
            "Verifier (Loop 4). The toggle and layout are wired now."
        )
        copilots = [st.session_state.get("last_copilot_id")] if st.session_state.get("last_copilot_id") else []
        st.selectbox("Select a copilot_id", options=copilots or ["(none built yet)"])
        st.text_area("Paste document text", height=160, disabled=True)
        st.file_uploader("…or upload a document", disabled=True)
    with side_col:
        _render_audit(st, [])


def main() -> None:
    st.set_page_config(page_title="Wakeel", layout="wide")
    st.title("Wakeel — Regulatory Agent Factory")

    _render_settings_sidebar()

    if "build_messages" not in st.session_state:
        st.session_state.build_messages = []
    if "build_audit" not in st.session_state:
        st.session_state.build_audit = []

    mode = st.radio("Mode", ["Build", "Use"], horizontal=True, key="mode_toggle")
    st.divider()

    chat_col, side_col = st.columns([2, 1], gap="large")
    if mode == "Build":
        _build_mode(chat_col, side_col)
    else:
        _use_mode(chat_col, side_col)


def _running_under_streamlit() -> bool:
    """True when this module is executing inside a Streamlit script runtime."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


if _running_under_streamlit():
    # Launched via `streamlit run run_ui.py` (or the Docker entrypoint).
    main()
elif __name__ == "__main__":
    # Launched via `python run_ui.py` — delegate to the streamlit CLI on :8001.
    import subprocess

    sys.exit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                os.path.abspath(__file__),
                "--server.port",
                "8001",
                "--server.address",
                "0.0.0.0",
            ]
        )
    )
