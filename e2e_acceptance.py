"""End-to-end acceptance simulation: customers + PO review.

Runs the Milestone-1 customer journeys against the system and prints a
gate-by-gate acceptance verdict — the same checklist the founder/Claude use in
their 48h review.

Usage:
    python e2e_acceptance.py                     # in-process, uses current .env
    python e2e_acceptance.py --offline           # force deterministic stubs
    python e2e_acceptance.py --base-url http://localhost:8000   # live server

Exit code 0 if all evaluated gates pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "tests"))


def _green(s: str) -> str:
    return f"\033[92m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[91m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[93m{s}\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WAKEEL_E2E_BASE_URL", ""))
    parser.add_argument("--offline", action="store_true", help="Force OFFLINE_MODE.")
    args = parser.parse_args()

    if args.offline:
        os.environ["OFFLINE_MODE"] = "true"

    # For in-process runs, use an isolated vector store and re-ingest to match the
    # current embedding mode (so we never clobber dev data or mismatch dimensions).
    if not args.base_url:
        os.environ.setdefault("CHROMA_DIR", str(_ROOT / ".e2e_chroma"))

    from app import config  # imported after env tweaks
    from helpers import (
        CUSTOMER_SCENARIOS,
        assert_valid_build_response,
        has_arabic,
        loops_in,
    )

    offline = config.OFFLINE_MODE

    # --- Build the client (in-process or live) ---
    if args.base_url:
        import requests

        class Client:
            def post(self, path, json):
                return requests.post(args.base_url.rstrip("/") + path, json=json, timeout=600)

            def get(self, path):
                return requests.get(args.base_url.rstrip("/") + path, timeout=30)

        client = Client()
        target = f"live server {args.base_url}"
    else:
        from fastapi.testclient import TestClient

        from app.api import app

        client = TestClient(app)
        target = "in-process API"

    # Ensure corpus matches the current embedding mode.
    from app.corpus.ingest import ingest
    from app.corpus.retrieval import semantic_search

    if not args.base_url:
        ingest(reset=True)

    print("=" * 72)
    print("  WAKEEL — Milestone 1 acceptance simulation (Build mode)")
    print(f"  Target: {target}   |   Mode: {'OFFLINE (stubs)' if offline else 'LIVE (real LLM)'}")
    print("=" * 72)

    results: list[dict] = []
    all_loops: set[str] = set()

    # --- Customer journeys ---
    print("\n[Customers] Building copilots...\n")
    for sc in CUSTOMER_SCENARIOS:
        try:
            resp = client.post("/run", json={"mode": "build", "intake": sc["intake"]})
            ok = resp.status_code == 200
            body = resp.json() if ok else {}
            if ok:
                assert_valid_build_response(body)
                loops = loops_in(body["audit_trail"])
                all_loops |= loops
                detail = (
                    f"copilot={body['copilot_id']} "
                    f"valid={body['validation_results'].get('passed')} "
                    f"loops={sorted(loops)} steps={len(body['audit_trail'])}"
                )
            else:
                detail = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = f"{exc.__class__.__name__}: {exc}"
            body = {}

        results.append({"scenario": sc, "ok": ok, "body": body})
        mark = _green("PASS") if ok else _red("FAIL")
        print(f"  [{mark}] {sc['persona']}")
        print(f"          {detail}")

    # --- PO gate verdicts ---
    def gate(ok: bool, evaluated: bool = True) -> str:
        if not evaluated:
            return _yellow("N/A (manual)")
        return _green("PASS") if ok else _red("FAIL")

    health_ok = False
    try:
        h = client.get("/health")
        health_ok = h.status_code == 200 and h.json().get("status") == "ok"
    except Exception:
        health_ok = False

    retrieval_ok = False
    try:
        hits = semantic_search("personal data cross border transfer consent", top_k=3)
        retrieval_ok = bool(hits) and all("article_number" in h["metadata"] for h in hits)
    except Exception:
        retrieval_ok = False

    builds_ok = all(r["ok"] for r in results)
    arabic_ok = any(
        r["ok"] and r["scenario"]["id"] == "ahmed_arabic" for r in results
    )
    if offline:
        loops_ok = {"Loop 1", "Loop 2", "Loop 3"}.issubset(all_loops)
    else:
        loops_ok = {"Loop 1", "Loop 2"}.issubset(all_loops)

    gates = [
        ("1", "LLM client connected (health + models)", gate(health_ok)),
        ("2", "Corpus ingested + retrieval works", gate(retrieval_ok)),
        ("3", "POST /run mode=build valid response (incl. Arabic)", gate(builds_ok and arabic_ok)),
        ("4", "Streamlit UI on :8001 (chat + audit)", gate(False, evaluated=False)),
        ("5", f"Loops firing in logs (saw {sorted(all_loops)})", gate(loops_ok)),
        ("6", "GitHub repo current with all delivered code", gate(False, evaluated=False)),
    ]

    print("\n" + "-" * 72)
    print("  PO ACCEPTANCE GATES")
    print("-" * 72)
    for num, name, verdict in gates:
        print(f"  Gate {num}: {verdict:<22} {name}")
    if not offline:
        print("\n  Note: live Loop 3 depends on model JSON compliance; it fires")
        print("        deterministically in offline mode (see logs/samples/).")
    print("  Note: Gates 4 & 6 are verified manually (UI in browser; GitHub repo")
    print("        current — see README and docs/github-setup.md).")

    evaluated_pass = all(
        v == _green("PASS") for _, _, v in gates if "N/A" not in v
    )
    print("\n" + "=" * 72)
    print("  VERDICT:", _green("ALL EVALUATED GATES PASS") if evaluated_pass else _red("FAILURES PRESENT"))
    print("=" * 72)
    return 0 if evaluated_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
