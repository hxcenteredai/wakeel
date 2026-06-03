"""Use-mode agents (PRD section 7).

Reviewer (reasoning) -> Citation Verifier (standard, Loop 4) ->
Counter-Proposal Drafter (standard) <-> Reviewer-as-critic (Loop 5) ->
Synthesis (standard).

Each function calls the shared LLM wrapper via app.agents.base.call_llm and
records its action on the run's AuditTrail. Loop control (4, 5) lives in
app.graph.use_graph; these functions are the per-agent units of work.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import call_llm
from app.corpus import retrieval
from app.logging_utils import AuditTrail


# --- System prompts -----------------------------------------------------------

REVIEWER_SYS = (
    "You are the Reviewer agent of an NDA-review copilot configured for the "
    "client's organisation. Apply the configured interpretation overrides and "
    "risk thresholds to each clause. For each finding, return a SINGLE citation "
    "object {law, article} pointing to the SPECIFIC UAE statute article that "
    "supports the finding. Cite ONLY articles you are confident exist in the "
    "configured corpus. Return STRICT JSON: "
    "{findings: [{clause, risk, confidence, citation:{law, article}, rationale}]}."
)

REVIEWER_RECITE_SYS = (
    "You are the Reviewer. The Citation Verifier rejected your prior citation "
    "as not present in the corpus. Re-cite the same finding using ONE of the "
    "candidate articles supplied. Return STRICT JSON: "
    "{clause, risk, confidence, citation:{law, article}, rationale}."
)

VERIFIER_SYS = (
    "You are the Citation Verifier. Given a (law, article) reference, you do "
    "NOT generate text — you only confirm whether the article exists in the "
    "ingested corpus. The orchestrator performs the corpus lookup; you record "
    "the decision."
)

DRAFTER_SYS = (
    "You are the Counter-Proposal Drafter. Given a flagged NDA clause and the "
    "Reviewer's rationale, draft a replacement clause that resolves the risk "
    "while remaining commercially acceptable. Return STRICT JSON: "
    "{draft_clause, rationale}."
)

CRITIC_SYS = (
    "You are the Reviewer acting as critic. Evaluate the Drafter's replacement "
    "clause against the same statute that triggered the original flag. Return "
    "STRICT JSON: {accepted: bool, critique: str}. Reject if the draft does "
    "not actually resolve the cited risk or is too vague."
)

SYNTHESIS_SYS = (
    "You are the Synthesis agent. Assemble the verified findings, counter-"
    "proposals, and audit trail into the final response summary. Return STRICT "
    "JSON: {summary: {total_findings, high_risk, medium_risk, low_risk, "
    "verified_citations, citation_rejections, draft_critiques, recommendation}}."
)


# --- Agent functions ----------------------------------------------------------

def reviewer(
    audit: AuditTrail,
    copilot_config: dict[str, Any],
    document: dict[str, Any],
    attempt: int = 1,
) -> dict[str, Any]:
    """Initial pass: produce findings with citations."""
    ctx = {
        "copilot_id": copilot_config.get("copilot_id"),
        "interpretation_overrides": copilot_config.get("interpretation_overrides", []),
        "risk_thresholds": copilot_config.get("risk_thresholds", {}),
        "retrieval_rules": copilot_config.get("retrieval_rules", {}),
        "document_text": (document.get("content") or "")[:4000],
        "attempt": attempt,
    }
    result, _ = call_llm(
        agent_name="Reviewer",
        tier="reasoning",
        system=REVIEWER_SYS,
        user=(
            "Review the NDA document below and emit findings with citations to "
            "the configured UAE statutes."
        ),
        ctx=ctx,
        expect_keys=["findings"],
    )
    findings = result.get("findings", [])
    audit.add(
        agent="Reviewer",
        action="review_document",
        decision=f"{len(findings)} findings",
        reason="Initial pass over the NDA.",
        details={"attempt": attempt, "findings_count": len(findings)},
    )
    return result


def reviewer_recite(
    audit: AuditTrail,
    finding: dict[str, Any],
    verifier_feedback: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    """Loop 4 retry: re-cite a single finding after a verifier rejection."""
    ctx = {
        "finding": finding,
        "rejected_citation": finding.get("citation", {}),
        "candidate_articles": verifier_feedback.get("candidates", []),
        "attempt": attempt,
    }
    result, _ = call_llm(
        agent_name="Reviewer",
        tier="reasoning",
        system=REVIEWER_RECITE_SYS,
        user="Re-cite the finding using one of the candidate articles.",
        ctx=ctx,
        expect_keys=["citation"],
    )
    audit.add(
        agent="Reviewer",
        action="re_cite",
        decision="recited",
        reason="Citation Verifier rejected the prior cite.",
        loop="Loop 4",
        details={
            "attempt": attempt,
            "rejected": finding.get("citation", {}),
            "proposed": result.get("citation", {}),
        },
    )
    # Merge the new citation back onto the finding.
    out = dict(finding)
    out["citation"] = result.get("citation", finding.get("citation", {}))
    out.setdefault("rationale", finding.get("rationale", ""))
    return out


def citation_verifier(
    audit: AuditTrail, finding: dict[str, Any], attempt: int
) -> dict[str, Any]:
    """Look up the cited article in the corpus. Returns verifier verdict."""
    citation = finding.get("citation", {}) or {}
    law = citation.get("law", "")
    article = str(citation.get("article", "")).strip()
    short_name = _resolve_short_name(law)

    hit = retrieval.get_article(short_name, _strip_article_prefix(article)) if short_name else None
    candidates: list[dict[str, Any]] = []
    if hit is None:
        # Provide alternatives via semantic search to enable Loop 4 re-cite.
        try:
            results = retrieval.semantic_search(
                finding.get("clause", "") + " " + finding.get("rationale", ""),
                top_k=3,
            )
        except Exception:
            results = []
        for r in results:
            meta = r.get("metadata", {})
            candidates.append(
                {
                    "law": meta.get("law_name"),
                    "article": meta.get("article_number"),
                    "short_name": meta.get("short_name"),
                }
            )

    verdict = {
        "verified": hit is not None,
        "exact_text": hit.get("text") if hit else None,
        "candidates": candidates,
        "attempt": attempt,
    }
    audit.add(
        agent="Citation Verifier",
        action="verify_citation",
        decision="verified" if verdict["verified"] else "rejected",
        reason=("Exact-text retrieval succeeded." if verdict["verified"]
                else f"Article not found in corpus; offered {len(candidates)} candidates."),
        loop="Loop 4",
        details={
            "law": law,
            "article": article,
            "attempt": attempt,
            "candidates": [f"{c.get('short_name')} Art {c.get('article')}" for c in candidates],
        },
    )
    return verdict


def counter_proposal_drafter(
    audit: AuditTrail,
    finding: dict[str, Any],
    attempt: int = 1,
    critique: str | None = None,
) -> dict[str, Any]:
    """Draft a replacement clause for a flagged finding."""
    ctx = {
        "finding": finding,
        "attempt": attempt,
        "critique": critique or "",
    }
    result, _ = call_llm(
        agent_name="Counter-Proposal Drafter",
        tier="standard",
        system=DRAFTER_SYS,
        user="Draft a replacement clause that resolves the cited risk.",
        ctx=ctx,
        expect_keys=["draft_clause"],
    )
    audit.add(
        agent="Counter-Proposal Drafter",
        action="draft_counter_proposal",
        decision="drafted",
        reason=("Initial draft." if attempt == 1
                else f"Revised after critique (attempt {attempt})."),
        loop="Loop 5" if attempt > 1 else None,
        details={"attempt": attempt, "clause": finding.get("clause", "")[:80]},
    )
    return result


def reviewer_critic(
    audit: AuditTrail,
    finding: dict[str, Any],
    draft: dict[str, Any],
    attempt: int,
) -> dict[str, Any]:
    """Loop 5: critique a drafter proposal against the original cited statute."""
    ctx = {"finding": finding, "draft": draft, "attempt": attempt}
    result, _ = call_llm(
        agent_name="Reviewer",
        tier="reasoning",
        system=CRITIC_SYS,
        user="Critique the draft against the cited statute.",
        ctx=ctx,
        expect_keys=["accepted"],
    )
    accepted = bool(result.get("accepted"))
    audit.add(
        agent="Reviewer",
        action="critique_draft",
        decision="accepted" if accepted else "rejected",
        reason=result.get("critique", ""),
        loop="Loop 5",
        details={"attempt": attempt, "accepted": accepted},
    )
    return result


def synthesis(
    audit: AuditTrail, findings: list[dict[str, Any]], rejections: int, critiques: int
) -> dict[str, Any]:
    """Final summary assembly."""
    ctx = {
        "findings_count": len(findings),
        "rejections": rejections,
        "critiques": critiques,
        "risk_buckets": {
            "high": sum(1 for f in findings if f.get("risk") == "high"),
            "medium": sum(1 for f in findings if f.get("risk") == "medium"),
            "low": sum(1 for f in findings if f.get("risk") == "low"),
        },
    }
    result, _ = call_llm(
        agent_name="Synthesis",
        tier="standard",
        system=SYNTHESIS_SYS,
        user="Produce the final summary block for the use-mode response.",
        ctx=ctx,
        expect_keys=["summary"],
    )
    summary = result.get("summary", {})
    audit.add(
        agent="Synthesis",
        action="assemble_response",
        decision="synthesised",
        reason="Final response assembled.",
        details={
            "total_findings": summary.get("total_findings", len(findings)),
            "citation_rejections": rejections,
            "draft_critiques": critiques,
        },
    )
    return summary


# --- Helpers ------------------------------------------------------------------

_LAW_SHORT_NAMES = {
    "Federal Decree-Law 33 of 2021": "Labour Law",
    "Federal Decree-Law 45 of 2021": "PDPL",
    "Federal Law 18 of 1993": "Commercial Transactions Law",
    "Federal Law 5 of 1985": "Civil Transactions Law",
}


def _resolve_short_name(law: str) -> str:
    """Map a full or short law name to the corpus short_name used in IDs."""
    if not law:
        return ""
    law = law.strip()
    if law in _LAW_SHORT_NAMES:
        return _LAW_SHORT_NAMES[law]
    if law in _LAW_SHORT_NAMES.values():
        return law
    # Heuristic: accept "Labour Law", "PDPL", or any string containing them.
    for full, short in _LAW_SHORT_NAMES.items():
        if short.lower() in law.lower() or full.lower() in law.lower():
            return short
    return law


def _strip_article_prefix(article: str) -> str:
    """Accept '43', 'Article 43', '(43)', 'Art. 43' → '43'."""
    if not article:
        return ""
    s = str(article).strip()
    for prefix in ("article", "art.", "art", "("):
        if s.lower().startswith(prefix):
            s = s[len(prefix):].lstrip(" .").rstrip(")")
    s = s.strip("() ").strip()
    return s
