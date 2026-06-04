"""Playwright capture for the M2 use-mode evidence screenshots.

Drives the running Streamlit UI through the full use-mode flow and writes
raw PNGs to ``docs/use-mode-evidence/raw/`` for downstream annotation.

The target URL is read from ``WAKEEL_UI_URL`` (default
``http://127.0.0.1:8001`` — the spec port). Set ``WAKEEL_UI_URL=http://127.0.0.1:8101``
when running an alternate-port Streamlit alongside the canonical one.

Sections captured (mirrors gate4-evidence A-E):

  A. Use mode landing — copilot dropdown populated, doc inputs visible.
  B. Aggressive vendor NDA loaded (pre-submit) — copilot picked, doc pasted.
  C. After review — recommendation banner, summary metrics, finding 1
     citation **VERIFIED on attempt 2** (the Loop-4 moment).
  D. Audit panel expanded — Citation Verifier "rejected" entry visible
     (Loop 4) + critique_draft entries (Loop 5).
  E. Balanced commercial NDA — second example, contrasting low/medium risk
     and "Acceptable subject to revisions" recommendation.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "use-mode-evidence" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

URL = os.environ.get("WAKEEL_UI_URL", "http://127.0.0.1:8001")
SCALE = 2  # device_scale_factor: CSS px → image px

# Bounding boxes captured per shot, indexed by shot filename.
# Each entry is {label: [x1, y1, x2, y2]} in raw-image pixels.
BBOXES: dict[str, dict[str, list[int]]] = {}


def _settle(page: Page, ms: int = 1200) -> None:
    """Streamlit reruns on every interaction; give the DOM time to repaint."""
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def _shot(page: Page, name: str) -> None:
    path = OUT / name
    page.screenshot(path=str(path), full_page=True)
    print(f"[shot] {path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")


def _bbox(page: Page, locator: Locator) -> list[int] | None:
    """Return the locator's bounding box in raw-image px (CSS px * SCALE)."""
    try:
        bx = locator.first.bounding_box(timeout=2000)
    except Exception:
        return None
    if not bx:
        return None
    return [
        int(bx["x"] * SCALE),
        int(bx["y"] * SCALE),
        int((bx["x"] + bx["width"]) * SCALE),
        int((bx["y"] + bx["height"]) * SCALE),
    ]


def _capture_bboxes(page: Page, shot: str, items: dict[str, Locator]) -> None:
    """Capture bounding boxes for each named locator and stash under ``shot``."""
    for name, loc in items.items():
        bb = _bbox(page, loc)
        if bb is not None:
            BBOXES.setdefault(shot, {})[name] = bb


def _expand_audit_entries(page: Page, labels: list[str]) -> int:
    """Click the first audit expander whose label matches each entry in ``labels``.

    Matching is left-to-right by ``labels`` order; each label is consumed once so
    duplicate labels (e.g. multiple Citation Verifier entries) get distinct clicks.
    """
    audit_details = page.locator("[data-testid='stExpander']")
    remaining = list(labels)
    expanded = 0
    n = audit_details.count()
    used: set[int] = set()
    for target in remaining:
        for i in range(n):
            if i in used:
                continue
            summary = audit_details.nth(i).locator("summary").first
            try:
                txt = summary.inner_text(timeout=500).strip().replace("\n", " ")
            except Exception:
                continue
            if target in txt:
                try:
                    summary.click(timeout=1500)
                    expanded += 1
                    used.add(i)
                    break
                except Exception:
                    pass
    return expanded


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Tall viewport so the post-review findings fit on screen without scrolling.
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 2200},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(URL)
        _settle(page, 2500)

        # Switch to Use mode radio
        page.get_by_text("Use", exact=True).click()
        _settle(page)

        # --- A. Use mode landing
        _capture_bboxes(page, "A-use-mode-landing.png", {
            "use_radio": page.locator("label", has_text="Use").first,
            "copilot_picker": page.locator(
                "div:has(> div > label:has-text('Select a copilot_id'))"
            ),
            "example_picker": page.locator(
                "div:has(> div > label:has-text('Load a committed example'))"
            ),
            "audit_panel": page.locator("h3", has_text="Audit trail").locator(".."),
        })
        _shot(page, "A-use-mode-landing.png")

        # --- B. Load the aggressive-vendor NDA example
        page.locator(
            "div:has(> div > label:has-text('Load a committed example'))"
        ).get_by_role("combobox").click()
        _settle(page, 600)
        page.get_by_role("option", name="Aggressive vendor NDA (triggers Loops 4 + 5)").click()
        _settle(page, 600)
        page.get_by_role("button", name="Load example").click()
        _settle(page, 1500)
        _capture_bboxes(page, "B-aggressive-nda-loaded.png", {
            "example_picker": page.locator(
                "div:has(> div > label:has-text('Load a committed example'))"
            ),
            "doc_title": page.locator(
                "div:has(> div > label:has-text('Document title'))"
            ).locator("input"),
            "doc_text": page.locator(
                "div:has(> div > label:has-text('Document text'))"
            ).locator("textarea"),
            "submit_btn": page.get_by_role("button", name="Review document"),
        })
        _shot(page, "B-aggressive-nda-loaded.png")

        # --- C. Submit the review and capture full findings + audit
        page.get_by_role("button", name="Review document").click()
        page.wait_for_selector("text=Recommendation:", timeout=60_000)
        _settle(page, 2500)
        # Make sure we're at the top so the recommendation banner is visible
        page.evaluate("window.scrollTo(0, 0)")
        _settle(page, 600)
        # Build a synthetic bbox spanning all 5 metric tiles (Findings → L5 critiques)
        metrics_locators = page.locator("[data-testid='stMetric']")
        m_first = metrics_locators.first.bounding_box()
        m_last = metrics_locators.last.bounding_box()
        metrics_bb_raw = None
        if m_first and m_last:
            metrics_bb_raw = [
                int(m_first["x"] * SCALE),
                int(m_first["y"] * SCALE),
                int((m_last["x"] + m_last["width"]) * SCALE),
                int((m_first["y"] + m_first["height"]) * SCALE),
            ]

        _capture_bboxes(page, "C-aggressive-nda-reviewed.png", {
            "loops_pill": page.get_by_text("Loops fired:").first.locator(".."),
            "recommendation": page.locator(
                "[data-testid='stMarkdownContainer']:has-text('Recommendation: DO NOT SIGN')"
            ).first,
            "finding_1_citation": page.get_by_text(
                "verified on attempt 2", exact=False
            ).first.locator(".."),
            "counter_prop_loop5": page.get_by_text(
                "refined over 2 Loop-5 critique cycles", exact=False
            ).first,
            "finding_1_card": page.locator("text=Finding 1").first.locator("../.."),
        })
        if metrics_bb_raw:
            BBOXES["C-aggressive-nda-reviewed.png"]["metrics_row"] = metrics_bb_raw
        _shot(page, "C-aggressive-nda-reviewed.png")

        # --- D. Expand the specific Loop 4 rejection + Loop 5 critique entries
        # The first "Citation Verifier — verify_citation [Loop 4]" is the
        # rejection of the hallucinated Federal Decree-Law 45/2021 Art 99
        # cite. The first "Reviewer — re_cite [Loop 4]" shows the recovery.
        # The first "Reviewer — critique_draft [Loop 5]" shows the Drafter
        # critique that triggered the counter-proposal revision.
        n_expanded = _expand_audit_entries(
            page,
            [
                "Citation Verifier — verify_citation [Loop 4]",  # rejected (Art 99)
                "Reviewer — re_cite [Loop 4]",                   # Reviewer re-cites
                "Reviewer — critique_draft [Loop 5]",            # Drafter critique
            ],
        )
        print(f"[info] expanded {n_expanded}/3 targeted audit entries")
        _settle(page, 1000)
        # Capture bboxes of expanded audit entries (use the parent details element)
        audit_details = page.locator("[data-testid='stExpander']")
        rejection_expander = None
        recite_expander = None
        for i in range(audit_details.count()):
            summary = audit_details.nth(i).locator("summary").first
            try:
                txt = summary.inner_text(timeout=500).strip()
            except Exception:
                continue
            if rejection_expander is None and "Citation Verifier" in txt and "Loop 4" in txt:
                rejection_expander = audit_details.nth(i)
            elif recite_expander is None and "re_cite" in txt and "Loop 4" in txt:
                recite_expander = audit_details.nth(i)
        _capture_bboxes(page, "D-audit-loops-4-5-expanded.png", {
            "rejection_entry": rejection_expander,
            "recite_entry": recite_expander,
            "finding_1_verified": page.get_by_text(
                "verified on attempt 2", exact=False
            ).first.locator(".."),
        })
        _shot(page, "D-audit-loops-4-5-expanded.png")

        # --- E. Balanced commercial NDA (Acceptable subject to revisions)
        page.evaluate("window.scrollTo(0, 0)")
        _settle(page, 300)
        page.locator(
            "div:has(> div > label:has-text('Load a committed example'))"
        ).get_by_role("combobox").click()
        _settle(page, 600)
        page.get_by_role("option", name="Balanced commercial partner NDA").click()
        _settle(page, 600)
        page.get_by_role("button", name="Load example").click()
        _settle(page, 1500)
        page.get_by_role("button", name="Review document").click()
        page.wait_for_selector("text=Recommendation:", timeout=60_000)
        _settle(page, 2500)
        page.evaluate("window.scrollTo(0, 0)")
        _settle(page, 500)
        metrics_locators_e = page.locator("[data-testid='stMetric']")
        me_first = metrics_locators_e.first.bounding_box()
        me_last = metrics_locators_e.last.bounding_box()
        metrics_bb_raw_e = None
        if me_first and me_last:
            metrics_bb_raw_e = [
                int(me_first["x"] * SCALE),
                int(me_first["y"] * SCALE),
                int((me_last["x"] + me_last["width"]) * SCALE),
                int((me_first["y"] + me_first["height"]) * SCALE),
            ]
        _capture_bboxes(page, "E-balanced-nda-reviewed.png", {
            "recommendation": page.locator(
                "[data-testid='stMarkdownContainer']:has-text('Recommendation: Acceptable')"
            ).first,
            "finding_1": page.locator("text=Finding 1").first.locator("../.."),
        })
        if metrics_bb_raw_e:
            BBOXES["E-balanced-nda-reviewed.png"]["metrics_row"] = metrics_bb_raw_e
        _shot(page, "E-balanced-nda-reviewed.png")

        browser.close()

    # Persist bounding boxes for the annotator
    bboxes_path = OUT / "_bboxes.json"
    with open(bboxes_path, "w", encoding="utf-8") as fh:
        json.dump(BBOXES, fh, indent=2)
    print(f"[bboxes] wrote {bboxes_path.relative_to(ROOT)} "
          f"({sum(len(v) for v in BBOXES.values())} elements across "
          f"{len(BBOXES)} shots)")


if __name__ == "__main__":
    sys.exit(main() or 0)
