"""Regenerate use-mode input/output examples and the committed sample log.

Deterministic (OFFLINE_MODE=true) so the committed evidence is reproducible
without any LLM credentials. Run from the repo root:

    OFFLINE_MODE=true python3 scripts/generate_use_mode_examples.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# Force offline before importing the LLM-touching modules.
os.environ.setdefault("OFFLINE_MODE", "true")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.config import LOG_DIR
from app.graph.build_graph import run_build
from app.graph.use_graph import run_use

INPUTS = [
    _ROOT / "input_examples" / "use_mode" / "01_aggressive_vendor_nda.json",
    _ROOT / "input_examples" / "use_mode" / "02_balanced_partner_nda.json",
    _ROOT / "input_examples" / "use_mode" / "03_data_broker_nda.json",
]
OUT_DIR = _ROOT / "output_examples" / "use_mode"
SAMPLES_DIR = _ROOT / "logs" / "samples"


def _normalise(payload: dict) -> dict:
    """Strip non-deterministic fields (run_id, timestamps) for diff-friendly output."""
    payload = dict(payload)
    payload["run_id"] = "<deterministic-offline-run>"
    audit = []
    for entry in payload.get("audit_trail", []):
        e = dict(entry)
        e.pop("timestamp", None)
        audit.append(e)
    payload["audit_trail"] = audit
    return payload


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Build a copilot for org fintech_co_001 (Sarah's persona) — feeds all 3.
    intake = {
        "workflow_description": (
            "We are a Dubai fintech. I need a copilot that reviews vendor NDAs "
            "against our conservative data-handling stance under UAE PDPL, "
            "flagging cross-border transfer and consent clauses."
        ),
        "org_id": "fintech_co_001",
        "document_type": "nda",
        "risk_appetite": "conservative",
        "language": "en",
    }
    build_response = run_build(intake)
    copilot_id = build_response["copilot_id"]
    print(f"[gen] built copilot {copilot_id} (steps={len(build_response['audit_trail'])})")

    # 2. Run each use-mode input against the same copilot.
    for input_path in INPUTS:
        case = json.loads(input_path.read_text(encoding="utf-8"))
        document = case["document"]
        response = run_use(copilot_id, document)
        case["copilot_id"] = copilot_id
        input_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        out_path = OUT_DIR / (input_path.stem + ".out.json")
        out_path.write_text(
            json.dumps(_normalise(response), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        loops = sorted({e.get("loop") for e in response["audit_trail"] if e.get("loop")})
        print(
            f"[gen] {input_path.name} → {out_path.name}: "
            f"{len(response['findings'])} findings, loops={loops}, "
            f"rejections={response['summary'].get('citation_rejections', 0)}, "
            f"critiques={response['summary'].get('draft_critiques', 0)}"
        )

    # 3. Canonical sample log for Loops 4 + 5 (committed evidence per PRD §17).
    canonical_log = LOG_DIR / f"run_{build_response['run_id']}.jsonl"  # not used directly
    # The use-mode run for example 01 already wrote a per-run JSONL into LOG_DIR.
    # We replay it cleanly under logs/samples/ with a stable name.
    sample_target = SAMPLES_DIR / "use_mode_run_loops_4_5.jsonl"

    # Collect the last use-mode run by re-running example 01 (idempotent in offline)
    rerun_response = run_use(
        copilot_id,
        json.loads(INPUTS[0].read_text(encoding="utf-8"))["document"],
    )
    src_log = LOG_DIR / f"run_{rerun_response['run_id']}.jsonl"
    if src_log.exists():
        shutil.copyfile(src_log, sample_target)
        print(f"[gen] wrote canonical sample log → {sample_target.relative_to(_ROOT)}")
    else:
        print(f"[gen] WARNING: expected run log at {src_log} but it was not found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
