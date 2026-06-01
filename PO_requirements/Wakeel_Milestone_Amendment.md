# Milestone & Acceptance Amendment

**Project:** Wakeel — UAE Regulatory Multi-Agent System
**Date:** _________________
**Parties:** [Founder Name] ("Client") and [Developer Name] ("Developer")

This amendment defines payment milestones, acceptance criteria, and the acceptance process for the engagement. It supplements any prior agreement between the Parties and controls in case of conflict on these specific terms.

---

## 1. Engagement total

Total fixed-price fee: **AED / USD __________** (the "Fee")

Payment structure: **50% on acceptance of Milestone 1; 50% on acceptance of Milestone 2.** No upfront payment.

---

## 2. Milestone 1 — Build Mode Foundation

**Delivery deadline:** Tuesday, May 26, 2026, 23:59 UAE time
**Payment on acceptance:** 50% of Fee

**Acceptance criteria (all must pass):**

1. LLM smoke test (`python -m app.llm`) returns a valid response from the configured Compass endpoint
2. Corpus ingested for at least UAE Federal Decree-Law 33 of 2021 (Labour Law) and Federal Decree-Law 45 of 2021 (PDPL); semantic retrieval returns sensible results
3. `POST /run` with `mode: "build"` returns a valid, complete response (including `copilot_id`, `config`, `validation_results`, `audit_trail`) on at least one English input from `input_examples/`
4. Streamlit UI loads on port 8001 with mode toggle, chat interface, and live audit trail sidebar
5. Feedback Loops 1, 2, and 3 demonstrably firing and visible in `logs/run_*.jsonl`
6. GitLab repository is current and the GitLab → GitHub mirror is live, syncing automatically

---

## 3. Milestone 2 — Use Mode, Arabic, Docker, Delivery

**Delivery deadline:** Friday, May 30, 2026, 23:59 UAE time
**Payment on acceptance:** 50% of Fee

**Acceptance criteria (all must pass):**

1. `POST /run` with `mode: "use"` returns a valid, complete response with verified citations on all 3 use-mode examples in `input_examples/`
2. Feedback Loops 4 (citation rejection) and 5 (counter-proposal critique) **demonstrably triggering** in `logs/run_*.jsonl` on test inputs — not merely present in code
3. NDA review copilot template working end-to-end against all 3 use-mode example inputs
4. Arabic input support working on the Interviewer agent, verified with `input_examples/build_02_hospital_nda_ar.json`
5. `docker build -t wakeel .` succeeds and `docker run -p 8000:8000 -p 8001:8001 --env-file .env wakeel` starts both API and UI cleanly from a fresh clone
6. Three (3) technical walkthrough videos delivered in `demos/`, each 60–90 seconds, covering: (a) build mode end-to-end, (b) use mode with a visible Loop 4 citation-rejection moment, (c) Arabic intake
7. `README.md` and `docs/architecture.md` reflect the final state of the system
8. No real API keys, secrets, or credentials present in the repository or its git history

---

## 4. Acceptance process

For each Milestone:

1. Developer notifies Client in writing when the Milestone is ready for review.
2. Client has up to **48 hours** from notification to complete the acceptance review and respond with one of: (a) **Accepted** — payment released within 7 days; (b) **Conditionally Accepted with Fix List** — specific, listed defects to be corrected within 48 hours, then re-review; (c) **Not Accepted** — material failure of acceptance criteria, with written explanation.
3. If the Client does not respond within 48 hours, the Milestone is deemed **Accepted**.
4. Defects discovered in Milestone 1 deliverables during Milestone 2 work that should reasonably have been caught at Milestone 1 acceptance are corrected by the Developer at no additional cost as part of the Milestone 2 scope.

---

## 5. Working norms

- **Daily check-ins** end of working day on May 22, 23, 24, 25, and 30 — short Loom or written summary of status and blockers.
- **Blocker SLA:** if blocked on a single issue for more than 4 hours, surface it.
- **No work expected during Eid Al Adha break (May 26–29).** Daily check-ins suspended during this window.
- **Code commits** atomic and message-prefixed (`feat:`, `fix:`, `docs:`).
- **Communication channel:** ___________________

---

## 6. Payment terms

- Payment within **7 days** of written Acceptance.
- Currency: ___________________
- Method: ___________________

---

## 7. Intellectual property

All code, documentation, configurations, prompts, and other artifacts produced under this engagement are the exclusive property of the Client upon payment of the respective Milestone. The Developer retains the right to reference this engagement in their professional portfolio and to link to the public GitHub repository.

---

## 8. Signatures

**Client:**

Signature: _________________________________________

Name: _____________________________________________

Date: _____________________________________________

**Developer:**

Signature: _________________________________________

Name: _____________________________________________

Date: _____________________________________________

---

*One page. Both signatures required before work begins.*
