# Milestone 2 — Use mode + delivery evidence

Maps every acceptance criterion in **Milestone Amendment §3** to the artefact
that proves it, plus the exact command(s) to reproduce. All evidence is
reproducible offline (no LLM creds required) per the explicit decision recorded
during M2 kickoff (deterministic stub mode for committed evidence).

Run the full report end-to-end:

```bash
OFFLINE_MODE=true python3 e2e_acceptance.py --offline
# expected: VERDICT: ALL EVALUATED GATES PASS
```

---

## Criterion 1 — `POST /run mode=use` returns verified citations on 3 examples

**Inputs (committed):**

- `input_examples/use_mode/01_aggressive_vendor_nda.json`
- `input_examples/use_mode/02_balanced_partner_nda.json`
- `input_examples/use_mode/03_data_broker_nda.json`

**Outputs (committed, deterministic):**

- `output_examples/use_mode/01_aggressive_vendor_nda.out.json`
- `output_examples/use_mode/02_balanced_partner_nda.out.json`
- `output_examples/use_mode/03_data_broker_nda.out.json`

Each output is structurally valid (PRD §9 schema: `run_id, mode, copilot_id,
findings, summary, audit_trail`) and **every finding has
`citation.verified=true`**. Differentiation across the three inputs:

| Input | Findings | High | Med | Low | L4 rejections | L5 critiques | Recommendation |
|---|---|---|---|---|---|---|---|
| Aggressive vendor | 3 | 1 | 1 | 1 | 1 | 2 | DO NOT SIGN |
| Balanced commercial | 1 | 0 | 1 | 0 | 0 | 1 | Acceptable subject to revisions |
| Data-broker | 5 | 2 | 2 | 1 | 1 | 4 | DO NOT SIGN |

**Reproduce:**

```bash
OFFLINE_MODE=true python3 scripts/generate_use_mode_examples.py
# Regenerates the 3 input + 3 output examples + canonical sample log.
```

**Tests:** `tests/test_acceptance_gates.py::test_gate7_use_mode_returns_verified_citations_on_three_examples`

---

## Criterion 2 — Loops 4 & 5 demonstrably triggering in `logs/run_*.jsonl`

**Canonical evidence (committed):**

- `logs/samples/use_mode_run_loops_4_5.jsonl` — full per-event log of a use-mode
  run against the aggressive-vendor NDA. The audit trail contains:
  - `agent=Citation Verifier  loop=Loop 4  decision=rejected` (the hallucinated PDPL Art 99 cite)
  - `agent=Reviewer  action=re_cite  loop=Loop 4  decision=recited` (re-cites Art 7)
  - `agent=Citation Verifier  loop=Loop 4  decision=verified` (real article, exact text returned)
  - `agent=Reviewer  action=critique_draft  loop=Loop 5  decision=rejected` (twice — vague initial drafts)
  - `agent=Counter-Proposal Drafter  loop=Loop 5  decision=drafted` (revised)
  - `agent=Reviewer  action=critique_draft  loop=Loop 5  decision=accepted` (final)

**Loops fired across all 3 use-mode examples (offline e2e):**

```
Loop 4 — total citation rejections:  2
Loop 5 — total draft critiques:      7
```

**Reproduce:**

```bash
OFFLINE_MODE=true python3 e2e_acceptance.py --offline | grep "L4\|L5"
```

**Tests:**

- `tests/test_acceptance_gates.py::test_gate8_loops_4_and_5_demonstrably_fire`
- `tests/test_acceptance_gates.py::test_gate8_canonical_sample_log_committed`

---

## Criterion 3 — NDA copilot template working end-to-end against 3 use-mode inputs

The NDA-review template is the single template family in v1 (PRD §5).
Build mode mints a `copilot_id`; use mode replays it against any document.
Criterion 1 already runs all three NDAs through the same `copilot_id` — every
run completes successfully and returns a structured `UseResponse` with findings
+ counter-proposals + verified citations.

**Reproduce (single-input flow):**

```bash
# 1. Mint a copilot via build mode
curl -s -X POST localhost:8000/run -H 'Content-Type: application/json' -d @input_examples/build_mode/01_english_nda_fintech.json | jq .copilot_id
# returns: "cp_xxxxxxx"

# 2. Run any use-mode input against it
curl -s -X POST localhost:8000/run -H 'Content-Type: application/json' -d "$(python3 -c "
import json
c=json.load(open('input_examples/use_mode/01_aggressive_vendor_nda.json'))
print(json.dumps({'mode':'use','copilot_id':'cp_xxxxxxx','document':c['document']}))")" | jq '.summary'
```

---

## Criterion 4 — Arabic input on Interviewer, verified on `input_examples/build_02_hospital_nda_ar.json`

**Input (committed):** `input_examples/build_02_hospital_nda_ar.json` —
hospital-themed Arabic NDA workflow description (PDPL + professional
confidentiality stance).

**Behaviour:** the Interviewer accepts Arabic (`language: "ar"`), emits the
structured English fields downstream, and the `response_to_user` field comes
back **in Arabic**.

**Reproduce:**

```bash
curl -s -X POST localhost:8000/run -H 'Content-Type: application/json' \
  -d @input_examples/build_02_hospital_nda_ar.json | jq '{copilot_id, interviewer_response, valid: .validation_results.passed}'
```

Expected: `valid: true`, `interviewer_response` contains Arabic characters
(`\u0600-\u06FF`).

**Test:** `tests/test_acceptance_gates.py::test_arabic_interviewer_handles_hospital_input`

---

## Criterion 5 — `docker build` succeeds; `docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel` runs clean

**Verified on:** macOS arm64, Docker Desktop 4.73.0.

```
$ docker build -t wakeel .
... DONE in ~7s on cached layers, full build under 3 min from scratch

$ docker run -d --name wakeel-test -p 8000:8000 -p 8001:8001 --env-file .env wakeel
$ curl localhost:8000/health
{"status":"ok", "models":{"standard":"gpt-4.1", "reasoning":"gpt-5.1", "embedding":"text-embedding-3-large"}, ...}

$ curl -s -I localhost:8001/
HTTP/1.1 200 OK
Server: TornadoServer/6.5.6
```

Both ports respond within ~2s of container start. Memory at idle: ~137 MiB.
Full use-mode arc through the container produces the canonical Loop 4 + Loop 5
evidence identical to in-process runs.

The image excludes `.venv/`, `.pytest_cache/`, `.cursor/`, `data/chroma/`,
`data/copilots/`, `logs/`, and `PO_requirements/` via `.dockerignore`, keeping
the build context small and the image at ~1.2 GiB.

---

## Criterion 6 — 3 walkthrough videos in `demos/`

Per Q4 decision at M2 kickoff: PR ships with **placeholder MP4 stubs** + a
shot-by-shot recording runbook. Each placeholder is a valid H.264 1280×720 MP4
labelled with the scenario it represents; replace with the real 60–90s 1080p
recording per `demos/RUNBOOK.md`.

| File | Scenario | Status |
|---|---|---|
| `demos/01_build_mode_walkthrough.mp4` | Build mode end-to-end (Loops 1-3 visible) | **PLACEHOLDER** — record per runbook |
| `demos/02_use_mode_walkthrough.mp4` | Use mode with Citation Verifier rejection moment (Loop 4) | **PLACEHOLDER** — record per runbook |
| `demos/03_arabic_intake_walkthrough.mp4` | Arabic intake (RTL rendering, Arabic reply) | **PLACEHOLDER** — record per runbook |

---

## Criterion 7 — `README.md` and `docs/architecture.md` reflect final state

- `README.md` — full quick start, build-mode + use-mode API usage examples, Arabic notes incl. hospital file, Loops 1–5 table, M2 limitations section.
- `docs/architecture.md` — full 10-agent topology (build + use), use-mode graph diagram, all 5 loops with caps, Loop 4 deep-dive, corpus pipeline with 4 statutes, copilot registry, services/ports.

---

## Criterion 8 — No real API keys, secrets, or credentials in the repo or git history

**Working-tree scan** (run by `e2e_acceptance.py`):

```bash
$ OFFLINE_MODE=true python3 e2e_acceptance.py --offline | grep "M2.8"
  Gate M2.8: PASS          No secrets in repo or git history
```

**Full-history scan** (manual, before push):

```bash
git log --all -p --pickaxe-regex -S'sk-[A-Za-z0-9_]{20,}' --format='%h %s' | head -20
# expected: empty output
git log --all -p --pickaxe-regex -S'OPENAI_API_KEY *= *sk-' --format='%h %s'
# expected: empty output
git log --all --name-only --pretty=format: | sort -u | grep -E '\.env|secret|credentials|api_key' | grep -v '\.example'
# expected: empty output
git ls-files | grep -E '^\.env$'
# expected: empty output (.env is gitignored)
```

All four checks pass clean on `feat/m2-use-mode-delivery`.

`.gitignore` patterns covering secrets:

- `.env` (exact)
- `.env.*` (any per-environment override)

`.dockerignore` excludes `.env` and `.env.*` from the build context so secrets
also never enter the image.

---

## Reproducibility summary

```bash
# 1. From a fresh clone:
git clone <repo> && cd wakeel
git checkout feat/m2-use-mode-delivery
cp .env.example .env       # then either set creds or leave OFFLINE_MODE=true

# 2. Set up Python:
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.corpus.ingest

# 3. Run the full M1 + M2 acceptance report:
OFFLINE_MODE=true python3 e2e_acceptance.py --offline

# 4. Run pytest:
OFFLINE_MODE=true python3 -m pytest tests/ -q

# 5. (Optional) Regenerate committed examples + canonical log:
OFFLINE_MODE=true python3 scripts/generate_use_mode_examples.py

# 6. (Optional) Docker:
docker build -t wakeel .
docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel
```

Expected at step 3: **VERDICT: ALL EVALUATED GATES PASS**, M1 Gates 1-3, 5 and M2 Gates 1-4, 8 all PASS. M1 Gates 4 (UI manual), 6 (GitHub manual) and M2 Gates 5 (Docker manual), 6 (videos), 7 (docs) are N/A (manual) — verified above and in `gate4-evidence.md`.

Expected at step 4: **18 passed, 1 skipped**.
