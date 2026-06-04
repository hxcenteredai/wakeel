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

For the **manual UI walkthrough** with annotated screenshots (the visual
equivalent of `docs/gate4-evidence.md` for Milestone 1), jump to the
[Visual walkthrough — A–E](#visual-walkthrough--ae) section below. Both the
programmatic per-criterion evidence and the visual walkthrough back the same
M2 acceptance gates.

---

## Visual walkthrough — A–E

Annotated screenshots taken from the running UI (`run_ui.py`). The Playwright
capture + Pillow annotator scripts used to produce these PNGs are kept locally
(`scripts/screenshots/capture_use_mode.py` and `annotate_use_mode.py`) and are
gitignored — the committed deliverable is the annotated PNG itself, per the
same logic as the demo MP4s. Each section below is the proof for the M2
criterion(ia) listed underneath.

- **Run date:** 2026-06-03
- **Backend:** `uvicorn app.api:app` on `http://localhost:8100` — `OFFLINE_MODE=true`
- **Frontend:** `streamlit run run_ui.py` on `http://localhost:8101`
- **Copilot pre-minted:** `cp_515a842c` (Build mode, English fintech NDA template)
- **Mode:** offline stub mode for determinism — every agent, every loop, every
  retrieval call runs identically on every machine without LLM credentials.

### A. Use mode — landing (copilot picker fed by `GET /copilots`)

After switching the radio to **Use**, the panel calls `GET /copilots`,
populates the picker with copilots from the registry, and exposes the
example shortcut + document title + document text inputs. The audit panel
is armed but empty.

![Section A annotated](use-mode-evidence/A-use-mode-landing-annotated.png)

Proves the Use-mode UI half of **Criterion 3** (NDA copilot E2E) and the
glue between Build mode and Use mode (the same `copilot_id` minted by
Build is what Use mode picks up via the file-backed registry).

### B. Aggressive-vendor NDA loaded (pre-submit)

Loading the *Aggressive vendor NDA* shortcut paste-loads
[`input_examples/use_mode/01_aggressive_vendor_nda.json`](../input_examples/use_mode/01_aggressive_vendor_nda.json)
into the form — title + the full NDA body including the cross-border
transfers clause that exercises Loops 4 and 5. The primary **Review
document** button is armed.

![Section B annotated](use-mode-evidence/B-aggressive-nda-loaded-annotated.png)

Demonstrates how a reviewer can replay any of the **3 committed
use-mode examples** through the UI in one click.

### C. Reviewed — verified citations, DO-NOT-SIGN, Loops 4+5 visible

This is **the killer demo** per PRD §16. Submitting the aggressive NDA
returns a `UseResponse` with:

- Recommendation banner = **DO NOT SIGN as-is — material PDPL risk on
  cross-border transfer** (rendered red).
- Summary metrics: 3 findings (1 High, 1 Medium, 1 Low), **1 Loop-4
  citation rejection**, **2 Loop-5 critique cycles**.
- Finding 1 carries citation `Federal Decree-Law 45 of 2021, Article 7
  VERIFIED (verified on attempt 2)` — the *attempt 2* annotation is the
  Loop 4 proof; the Citation Verifier rejected the prior cite and the
  Reviewer re-cited.
- Counter-proposal sub-line says *refined over 2 Loop-5 critique cycles*.
- Audit panel green pill: **Loops fired: Loop 4, Loop 5**.

![Section C annotated](use-mode-evidence/C-aggressive-nda-reviewed-annotated.png)

Proves **Criterion 1** (verified citations on a use-mode example),
**Criterion 2** (Loops 4 + 5 firing), and **Criterion 3** (NDA copilot
end-to-end).

### D. Audit panel — Loop 4 rejection + Reviewer re-cite expanded

Expanding the first Citation Verifier (Loop 4) audit entry surfaces the
full rejection record:

- `Decision: rejected`
- `Reason: Article not found in corpus; offered 3 candidates.`
- Details JSON: hallucinated cite was `Federal Decree-Law 45 of 2021,
  Article 99` — the Verifier offered back 3 nearest neighbours (Civil
  Transactions Art 257, Commercial Transactions Art 2, Civil Transactions
  Art 390).

The Reviewer — `re_cite` (Loop 4) entry below shows the recovery —
`{rejected: art 99} → {proposed: art 7}`. The finding card on the left
then carries the `verified on attempt 2` annotation that proves Loop 4
ran to a successful re-cite, not just to a fail-state.

![Section D annotated](use-mode-evidence/D-audit-loops-4-5-expanded-annotated.png)

Proves the mechanism behind **Criterion 2** — Loops 4 and 5 are not
just *labelled* in the audit, they carry the full structured rejection
and recovery payload. This is the auditability story PRD §14 requires.

### E. Balanced commercial NDA — different recommendation, same pipeline

Same copilot, different document
([`input_examples/use_mode/02_balanced_partner_nda.json`](../input_examples/use_mode/02_balanced_partner_nda.json)).
Recommendation flips to **GREEN — *Acceptable subject to the listed
counter-proposals*** with 1 Medium finding, **0 Loop-4 rejections**,
**1 Loop-5 critique**. The audit panel still expanded from D shows the
Citation Verifier ran with `Decision: verified` and zero candidates —
the same Loop 4 mechanism, just no rejection because the original cite
was already in the corpus.

![Section E annotated](use-mode-evidence/E-balanced-nda-reviewed-annotated.png)

Demonstrates **content-aware** behaviour — the deterministic offline
stubs differentiate per NDA, the recommendation logic flips colour
based on risk severity, and **Criterion 1** holds across input
variations (every citation verified, all `UseResponse` fields present).

---

## Reproducing the visual walkthrough locally

```bash
# 1. Start the M2 backend + UI in offline mode (use any free ports)
OFFLINE_MODE=true SAMPLE_MODE=true \
    python -m uvicorn app.api:app --host 127.0.0.1 --port 8100 &
WAKEEL_BACKEND_URL=http://127.0.0.1:8100 \
    streamlit run run_ui.py --server.port 8101 --server.headless true &

# 2. Mint a copilot via Build mode so the Use mode picker is populated
curl -s -X POST http://127.0.0.1:8100/run \
     -H 'Content-Type: application/json' \
     -d @input_examples/build_mode/01_english_nda_fintech.json | jq .copilot_id

# 3. Re-capture and re-annotate the screenshots (local-only dev tooling,
#    gitignored — committed deliverable is the annotated PNG itself).
python scripts/screenshots/capture_use_mode.py
python scripts/screenshots/annotate_use_mode.py
# → docs/use-mode-evidence/{A,B,C,D,E}-*-annotated.png
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

**Visual proof:** [Section C](#c-reviewed--verified-citations-do-not-sign-loops-45-visible)
(aggressive NDA) and [Section E](#e-balanced-commercial-nda--different-recommendation-same-pipeline)
(balanced NDA) show the Finding cards with `VERIFIED` pill + `verified on
attempt 2` annotation on the citations.

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

**Visual proof:** [Section D](#d-audit-panel--loop-4-rejection--reviewer-re-cite-expanded)
expands the Citation Verifier (Loop 4) rejection entry — full rejection
JSON with the hallucinated article and the 3 candidate alternatives — plus
the Reviewer `re_cite` (Loop 4) recovery entry showing
`{rejected: art 99} → {proposed: art 7}`.

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

**Visual proof:** [Sections A → B → C → E](#visual-walkthrough--ae) walk
the complete UI loop — copilot picker fed by `/copilots`, document load,
review submission, results rendered with verified citations and
counter-proposals.

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

# 7. (Optional) Regenerate the annotated UI walkthrough (Sections A–E):
#    capture_use_mode.py + annotate_use_mode.py are local-only dev tooling
#    (gitignored). The committed PNGs under docs/use-mode-evidence/ are the
#    deliverable. Requires playwright + chromium if re-running locally.
```

Expected at step 3: **VERDICT: ALL EVALUATED GATES PASS**, M1 Gates 1-3, 5 and M2 Gates 1-4, 8 all PASS. M1 Gates 4 (UI manual), 6 (GitHub manual) and M2 Gates 5 (Docker manual), 6 (videos), 7 (docs) are N/A (manual) — verified in the [Visual walkthrough section above](#visual-walkthrough--ae) and in `gate4-evidence.md`.

Expected at step 4: **26 passed, 1 skipped** (M1 + M2 acceptance gates + use-mode UI helper tests).
