"""Auto-record the three M2 walkthrough videos using Playwright.

Produces the deliverables required by Milestone Amendment §3 criterion 6
and PRD §17 by driving the running Streamlit UI on ``http://127.0.0.1:8001``
through three scripted scenarios. Each browser context records to a
.webm; ``ffmpeg`` stream-copies / re-encodes them to the canonical MP4
filenames under ``demos/``.

Outputs:
  demos/01_build_mode_walkthrough.mp4   (build mode → Loops 1+2+3 audit)
  demos/02_use_mode_walkthrough.mp4     (use mode → Loop 4 rejection moment)
  demos/03_arabic_intake_walkthrough.mp4 (Arabic intake → RTL + Arabic reply)

Pre-flight:
  1. API on http://127.0.0.1:8000 with OFFLINE_MODE=true.
  2. Streamlit on http://127.0.0.1:8001 (run_ui.py).
  3. Playwright + chromium installed.

Run:
  python scripts/demos/record_walkthroughs.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DEMOS = ROOT / "demos"
RECORDINGS = DEMOS / "recordings"
RECORDINGS.mkdir(parents=True, exist_ok=True)

URL = "http://127.0.0.1:8001"
VIEW = {"width": 1920, "height": 1080}

# Build-mode English prompt (from input_examples/build_mode/01_english_nda_fintech.json)
BUILD_EN_PROMPT = (
    "Build a copilot to review vendor NDAs against our PDPL stance, "
    "flagging cross-border transfer and consent clauses."
)
# Arabic hospital intake (from input_examples/build_02_hospital_nda_ar.json)
ARABIC_PROMPT = (
    "نحن مستشفى خاص في أبوظبي ونحتاج إلى مساعد لمراجعة اتفاقيات عدم "
    "الإفصاح مع موردي الأجهزة الطبية ومقدمي الخدمات السحابية، مع التشدد "
    "في حماية البيانات الصحية للمرضى وفق قانون حماية البيانات الشخصية "
    "الإماراتي والتزامات السرية المهنية. يجب أن يرفض المساعد أي بنود "
    "تسمح بنقل بيانات المرضى خارج الدولة دون موافقة صريحة."
)


# ----- helpers ---------------------------------------------------------------


_ANNO_Z = 2147483647  # max int32 — beat Streamlit's chrome (z-index ~999990)

# CSS rules. All positional/layout properties are !important so Streamlit's
# global styles (which match `body > div` selectors) cannot override us, and
# we declare `width: 100vw` + attach to documentElement to escape any
# transform-containing-block established by Streamlit's `[data-testid="stApp"]`.
ANNOTATION_CSS = f"""
#wakeel-anno-style {{ display: none; }}

/* Hide Streamlit's deploy header + toolbar so our title bar isn't covered. */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {{
    display: none !important;
    visibility: hidden !important;
}}

.wakeel-anno-box {{
    position: fixed !important;
    border: 5px solid #dc2626 !important;
    border-radius: 4px !important;
    box-shadow: 0 0 24px rgba(220, 38, 38, 0.55), inset 0 0 12px rgba(220, 38, 38, 0.18);
    z-index: {_ANNO_Z} !important;
    pointer-events: none !important;
    animation: wakeelPulse 1.6s ease-in-out infinite;
    background: transparent !important;
}}
.wakeel-anno-caption {{
    position: fixed !important;
    background: #dc2626 !important;
    color: #fff !important;
    font: 700 17px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif !important;
    padding: 10px 16px !important;
    border-radius: 6px !important;
    box-shadow: 0 6px 18px rgba(0,0,0,0.25);
    z-index: {_ANNO_Z} !important;
    pointer-events: none !important;
    max-width: 540px !important;
    white-space: normal !important;
    direction: ltr !important;
    text-align: left !important;
}}
.wakeel-anno-title-bar {{
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: auto !important;
    bottom: auto !important;
    width: 100vw !important;
    max-width: 100vw !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    background: linear-gradient(180deg, #0f172a, #1e293b) !important;
    color: #fff !important;
    font: 700 22px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif !important;
    padding: 14px 48px !important;
    z-index: {_ANNO_Z} !important;
    border-bottom: 4px solid #dc2626 !important;
    pointer-events: none !important;
    letter-spacing: 0.2px !important;
    direction: ltr !important;
    text-align: left !important;
    text-indent: 0 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    display: block !important;
}}
.wakeel-anno-explain-bar {{
    position: fixed !important;
    top: auto !important;
    left: 0 !important;
    right: auto !important;
    bottom: 0 !important;
    width: 100vw !important;
    max-width: 100vw !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    background: rgba(15, 23, 42, 0.96) !important;
    color: #fff !important;
    font: 500 19px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif !important;
    padding: 18px 64px !important;
    z-index: {_ANNO_Z} !important;
    border-top: 3px solid #dc2626 !important;
    pointer-events: none !important;
    min-height: 32px !important;
    direction: ltr !important;
    text-align: left !important;
    text-indent: 0 !important;
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: anywhere !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
}}
@keyframes wakeelPulse {{
    0%, 100% {{ box-shadow: 0 0 24px rgba(220, 38, 38, 0.55), inset 0 0 12px rgba(220, 38, 38, 0.18); }}
    50%      {{ box-shadow: 0 0 36px rgba(220, 38, 38, 0.85), inset 0 0 18px rgba(220, 38, 38, 0.28); }}
}}
"""


def _settle(page: Page, ms: int = 900) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def _hold(page: Page, seconds: float, msg: str | None = None) -> None:
    """Deliberate pause for the camera — explicit so the runbook timings map cleanly."""
    if msg:
        print(f"    hold {seconds:.1f}s — {msg}")
    page.wait_for_timeout(int(seconds * 1000))


def _inject_styles(page: Page) -> None:
    """Inject the annotation CSS + a persistence layer that re-creates the
    bars whenever Streamlit's reruns wipe them out of the DOM.

    The CSS is appended to ``document.head``; the title/explain bars are
    appended directly to ``document.documentElement`` (the <html> element).
    This bypasses the transform-containing-block established by Streamlit's
    ``[data-testid="stApp"]`` wrapper that was previously turning
    ``position: fixed; left: 0`` into an offset position, clipping the left
    side of every caption.
    """
    page.evaluate(
        """css => {
            // Idempotent style injection
            let s = document.getElementById('wakeel-anno-style');
            if (!s) {
                s = document.createElement('style');
                s.id = 'wakeel-anno-style';
                document.head.appendChild(s);
            }
            s.textContent = css;

            // Anchor div holds the bars + caches their text across Streamlit reruns.
            // Attached to documentElement (the <html> element) so it lives OUTSIDE
            // Streamlit's `<body><div data-testid="stApp">…</div></body>` subtree
            // and survives whole-app reruns + escapes any transform-containing-block.
            if (window.__wakeelAnno) return;
            const anchor = {
                title: '',
                explain: '',
                _ensureBar: function (id, cls) {
                    let bar = document.getElementById(id);
                    if (!bar) {
                        bar = document.createElement('div');
                        bar.id = id;
                        bar.className = cls;
                        document.documentElement.appendChild(bar);
                    } else if (bar.parentNode !== document.documentElement) {
                        // Streamlit moved it — yank back to documentElement.
                        document.documentElement.appendChild(bar);
                    }
                    return bar;
                },
                refresh: function () {
                    if (this.title) {
                        const b = this._ensureBar('wakeel-title-bar', 'wakeel-anno-title-bar');
                        if (b.textContent !== this.title) b.textContent = this.title;
                    } else {
                        document.getElementById('wakeel-title-bar')?.remove();
                    }
                    if (this.explain) {
                        const b = this._ensureBar('wakeel-explain-bar', 'wakeel-anno-explain-bar');
                        if (b.textContent !== this.explain) b.textContent = this.explain;
                    } else {
                        document.getElementById('wakeel-explain-bar')?.remove();
                    }
                },
                setTitle: function (t) { this.title = t || ''; this.refresh(); },
                setExplain: function (t) { this.explain = t || ''; this.refresh(); },
                clearAll: function () {
                    this.title = '';
                    this.explain = '';
                    document.getElementById('wakeel-title-bar')?.remove();
                    document.getElementById('wakeel-explain-bar')?.remove();
                },
            };
            window.__wakeelAnno = anchor;

            // Watch for Streamlit reruns wiping our nodes; restore immediately.
            const obs = new MutationObserver(() => anchor.refresh());
            obs.observe(document.documentElement, { childList: true, subtree: true });

            // Belt-and-braces: every 250ms also force a refresh (covers cases
            // where MutationObserver fires before Streamlit's removal completes).
            setInterval(() => anchor.refresh(), 250);
        }""",
        ANNOTATION_CSS,
    )


def _set_title_bar(page: Page, title: str) -> None:
    """Show or replace the persistent dark title bar at the top of the video."""
    page.evaluate(
        """text => {
            if (!window.__wakeelAnno) return;
            window.__wakeelAnno.setTitle(text);
        }""",
        title,
    )


def _set_explain(page: Page, text: str) -> None:
    """Show or replace the persistent dark explanation bar at the bottom."""
    page.evaluate(
        """text => {
            if (!window.__wakeelAnno) return;
            window.__wakeelAnno.setExplain(text);
        }""",
        text,
    )


def _box(
    page: Page,
    locator: Locator,
    caption: str,
    anchor: str = "tr",
    box_id: str = "primary",
) -> None:
    """Draw a red callout box around the locator's current bounding rect + caption.

    Subsequent calls with the same ``box_id`` replace the previous one,
    so the highlight follows the action without piling up overlays.
    """
    bb = None
    try:
        bb = locator.first.bounding_box(timeout=2000)
    except Exception:
        pass
    if not bb:
        return
    page.evaluate(
        """args => {
            const id = 'wakeel-box-' + args.id;
            const capId = id + '-cap';
            ['', '-cap'].forEach(suffix => {
                const e = document.getElementById(id + suffix); if (e) e.remove();
            });
            const box = document.createElement('div');
            box.id = id;
            box.className = 'wakeel-anno-box';
            box.style.left = args.x + 'px';
            box.style.top = args.y + 'px';
            box.style.width = args.w + 'px';
            box.style.height = args.h + 'px';
            document.body.appendChild(box);

            const cap = document.createElement('div');
            cap.id = capId;
            cap.className = 'wakeel-anno-caption';
            cap.textContent = args.caption;
            document.body.appendChild(cap);
            // Measure caption after insertion
            const cw = cap.getBoundingClientRect().width;
            const ch = cap.getBoundingClientRect().height;
            let cx, cy;
            if (args.anchor === 'tr') { cx = Math.max(8, args.x + args.w - cw); cy = Math.max(8, args.y - ch - 8); }
            else if (args.anchor === 'tl') { cx = args.x; cy = Math.max(8, args.y - ch - 8); }
            else if (args.anchor === 'bl') { cx = args.x; cy = args.y + args.h + 8; }
            else if (args.anchor === 'br') { cx = Math.max(8, args.x + args.w - cw); cy = args.y + args.h + 8; }
            else if (args.anchor === 'rt') { cx = args.x + args.w + 12; cy = args.y; }
            else if (args.anchor === 'lt') { cx = Math.max(8, args.x - cw - 12); cy = args.y; }
            else { cx = args.x; cy = args.y + args.h + 8; }
            // Keep within viewport
            cx = Math.min(cx, window.innerWidth - cw - 8);
            cy = Math.min(cy, window.innerHeight - ch - 8);
            cap.style.left = cx + 'px';
            cap.style.top  = cy + 'px';
        }""",
        {
            "id": box_id,
            "x": int(bb["x"]),
            "y": int(bb["y"]),
            "w": int(bb["width"]),
            "h": int(bb["height"]),
            "caption": caption,
            "anchor": anchor,
        },
    )


def _clear_boxes(page: Page) -> None:
    """Remove all red callout boxes (keeps title + explain bars)."""
    page.evaluate(
        """() => {
            document.querySelectorAll('.wakeel-anno-box, .wakeel-anno-caption').forEach(e => e.remove());
        }"""
    )


def _clear_all(page: Page) -> None:
    """Remove every annotation (used between videos / on shutdown)."""
    page.evaluate(
        """() => {
            document.querySelectorAll('.wakeel-anno-box, .wakeel-anno-caption').forEach(e => e.remove());
            if (window.__wakeelAnno) {
                window.__wakeelAnno.clearAll();
            } else {
                document.getElementById('wakeel-title-bar')?.remove();
                document.getElementById('wakeel-explain-bar')?.remove();
            }
        }"""
    )


def _expand_audit_entries(page: Page, labels: list[str]) -> int:
    """Click each named audit expander once, left-to-right, with a beat between."""
    audit_details = page.locator("[data-testid='stExpander']")
    n = audit_details.count()
    used: set[int] = set()
    expanded = 0
    for target in labels:
        for i in range(n):
            if i in used:
                continue
            summary = audit_details.nth(i).locator("summary").first
            try:
                txt = summary.inner_text(timeout=400).strip().replace("\n", " ")
            except Exception:
                continue
            if target in txt:
                try:
                    summary.click(timeout=1200)
                    used.add(i)
                    expanded += 1
                    page.wait_for_timeout(700)
                    break
                except Exception:
                    pass
    return expanded


def _switch_mode(page: Page, mode: str) -> None:
    page.get_by_text(mode, exact=True).first.click()
    _settle(page, 800)


def _make_context(p, video_dir: Path) -> BrowserContext:
    return p.chromium.launch(headless=True).new_context(
        viewport=VIEW,
        device_scale_factor=1,  # 1x for video to keep file size reasonable
        record_video_dir=str(video_dir),
        record_video_size=VIEW,
    )


def _convert_webm(webm: Path, target_mp4: Path) -> None:
    """Transcode WebM (VP8/9) to MP4 (H.264) preserving wallclock duration.

    Playwright records variable-frame-rate WebM — during static page periods
    chromium emits very few frames. ffprobe the source's wallclock duration
    and pass it via ``-r`` matched to the wallclock so the constant-fps MP4
    output keeps the same play-time as the recording session.
    """
    # Get source wallclock duration (the WebM's container duration is correct
    # even when frame-rate is variable).
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(webm)],
        capture_output=True, text=True,
    )
    src_dur = float(probe.stdout.strip() or "0")
    # If duration is missing or zero, fall back to 30 fps passthrough.
    fps_arg = ["-fps_mode", "cfr", "-r", "30"]
    cmd = [
        "ffmpeg", "-y",
        # Reading the input twice so we can target a duration:
        "-i", str(webm),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        *fps_arg,
        # Stretch / duplicate frames to match the source wallclock duration
        # if ffmpeg's natural CFR conversion would otherwise truncate.
        *(["-t", f"{src_dur:.3f}"] if src_dur > 0 else []),
        "-an",
        str(target_mp4),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-500:]}")


# ----- video #1 — Build mode walkthrough ------------------------------------


def record_build_mode(p) -> str:
    """Returns the freshly minted copilot_id. Targets ~75s with annotations."""
    print("[video 1/3] Build mode walkthrough — minting a copilot")
    ctx = _make_context(p, RECORDINGS / "01_build")
    page = ctx.new_page()
    page.goto(URL)
    _settle(page, 2200)

    _inject_styles(page)
    _set_title_bar(page, "WAKEEL — BUILD MODE: a copilot forged by an agent council")
    _set_explain(page, "One-sentence intake → agent factory. Watch the audit panel: agents debate, retry, and rebuild — Loops 1, 2, 3 visible live.")

    # 0:00–0:06 — Build mode landing
    _switch_mode(page, "Build")
    _hold(page, 5.0, "title + intro")

    # 0:06–0:20 — paste prompt + highlight it
    chat_input = page.get_by_placeholder(
        "e.g. Review vendor NDAs against our fintech data-handling stance"
    )
    chat_input.click()
    chat_input.fill(BUILD_EN_PROMPT)
    _box(page, chat_input, "User intake — fintech NDA review against PDPL stance", anchor="tl")
    _set_explain(page, "Plain-language intake. No SQL, no JSON — just an NDA-review brief. The Interviewer parses it into structured requirements.")
    _hold(page, 7.0, "user prompt highlighted")
    _clear_boxes(page)
    chat_input.press("Enter")

    # 0:20–0:30 — wait for completion
    _set_explain(page, "Six agents fire: Interviewer → Debater A vs B (Loop 1) → Architect → Builder → Validator (Loop 2) → reject + rebuild if needed.")
    page.wait_for_selector("text=Loops fired", timeout=60_000)
    _hold(page, 4.0, "audit panel populated")

    # 0:30–0:40 — Loops fired pill
    loops_pill = page.get_by_text("Loops fired:").first.locator("..")
    _box(page, loops_pill, "Loops fired: Loop 1, Loop 2 (and 3) — proof of multi-round collaboration", anchor="tl")
    _set_explain(page, "Green pill = the council didn't just run sequentially. A feedback loop fired — agents disagreed and re-collaborated.")
    _hold(page, 7.0, "Loops fired pill highlighted")
    _clear_boxes(page)

    # 0:40–1:05 — expand Loop 1 + Loop 2 evidence entries
    print("  expanding audit entries…")
    audit_details = page.locator("[data-testid='stExpander']")
    used: set[int] = set()

    loop1_captions = [
        ("Architect — synthesize_or_escalate [Loop 1]",
         "Loop 1: Architect — Decision: request_more_debate",
         "Loop 1 (Stance Debate): debaters hadn't resolved the cross-border consent split — Architect requested another round."),
        ("Validator — validate_copilot [Loop 2]",
         "Loop 2: Validator — Decision: rejected (first attempt)",
         "Loop 2 (Validation Rejection): the first build failed the Validator's sample-NDA tests — Builder must rebuild."),
        ("Validator — validate_copilot [Loop 2]",
         "Loop 2: Validator — Decision: passed (second attempt, score 0.91)",
         "Second attempt passes (iteration 2, score 0.91). Validator accepts the copilot — Loop 2 closes successfully."),
    ]
    for target, caption, explain in loop1_captions:
        for i in range(audit_details.count()):
            if i in used:
                continue
            summary = audit_details.nth(i).locator("summary").first
            try:
                txt = summary.inner_text(timeout=400).strip().replace("\n", " ")
            except Exception:
                continue
            if target in txt:
                try:
                    summary.click(timeout=1200)
                    used.add(i)
                    page.wait_for_timeout(400)
                    _box(page, audit_details.nth(i), caption, anchor="tl")
                    _set_explain(page, explain)
                    _hold(page, 6.0, target)
                    _clear_boxes(page)
                    break
                except Exception:
                    pass

    # 1:05–end — show copilot_id
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    _set_explain(page, "Final output: a brand-new copilot_id is minted with the full audit trail. Persisted and addressable from Use mode.")
    cp_block = page.locator("text=Copilot config").first.locator("..")
    _box(page, cp_block, "Copilot built — minted copilot_id ready for Use mode", anchor="tl")
    _hold(page, 8.0, "copilot_id callout")
    _clear_all(page)

    # Closing frame: clean view
    page.evaluate("window.scrollTo(0, 0)")
    _inject_styles(page)
    _set_title_bar(page, "WAKEEL — BUILD MODE: copilot minted, Loops 1+2 fired")
    _set_explain(page, "One sentence in → a fully-tuned, audit-trailed copilot out. Feedback loops 1-3 demonstrably triggering.")
    _hold(page, 6.0, "closing frame")
    _clear_all(page)

    # Capture the minted copilot_id from /copilots (use the newest entry)
    import json as _json
    import urllib.request as _ur
    copilot_ids_before = set()
    copilots_url = "http://127.0.0.1:8000/copilots"
    # We don't have a clean "newest" timestamp via /copilots; for simplicity,
    # parse the final assistant message in the chat for `cp_xxxxxxxx`.
    bubble_text = page.locator(
        "[data-testid='stChatMessage'][data-testid-role='assistant'], [data-testid='stChatMessage']"
    ).last.inner_text(timeout=2000)
    import re
    m = re.search(r"cp_[0-9a-f]{8}", bubble_text)
    minted = m.group(0) if m else ""

    video_obj = page.video
    ctx.close()
    webm_path = Path(video_obj.path()) if video_obj else None
    if webm_path and webm_path.exists():
        target = DEMOS / "01_build_mode_walkthrough.mp4"
        _convert_webm(webm_path, target)
        print(f"  → {target.relative_to(ROOT)}  ({target.stat().st_size//1024} KB)")
    else:
        raise RuntimeError("video #1 not produced")
    print(f"  copilot minted: {minted or '(not detected — will use latest from /copilots)'}")
    return minted


# ----- video #2 — Use mode killer demo --------------------------------------


def record_use_mode(p, copilot_id: str) -> None:
    """Targets ~95s — heaviest on the Loop-4 rejection moment per PRD §16."""
    print(f"[video 2/3] Use mode walkthrough — the killer demo (copilot {copilot_id})")
    ctx = _make_context(p, RECORDINGS / "02_use")
    page = ctx.new_page()
    page.goto(URL)
    _settle(page, 2200)

    _inject_styles(page)
    _set_title_bar(page, "WAKEEL — THE KILLER DEMO: Citation Verifier catches a hallucinated cite")
    _set_explain(page, "Feed the just-built copilot an aggressive vendor NDA. The Reviewer hallucinates a citation — the Citation Verifier catches it.")

    # 0:00–0:05 — switch to Use mode
    _switch_mode(page, "Use")
    _hold(page, 4.0, "Use mode landing")

    # 0:05–0:13 — select the freshly minted copilot
    if copilot_id:
        cp_picker = page.locator(
            "div:has(> div > label:has-text('Select a copilot_id'))"
        ).get_by_role("combobox")
        cp_picker.click()
        _hold(page, 0.6)
        page.keyboard.type(copilot_id, delay=40)
        _hold(page, 0.8)
        page.get_by_role("option", name=copilot_id).first.click()
        cp_picker_field = page.locator(
            "div:has(> div > label:has-text('Select a copilot_id'))"
        )
        _box(page, cp_picker_field, f"Selected: {copilot_id} (the copilot we just built)", anchor="br")
        _set_explain(page, "The copilot built in video 1, now addressable. Same copilot, replayed against any document — the factory promise.")
        _hold(page, 4.5, "copilot selected")
        _clear_boxes(page)

    # 0:13–0:25 — load the aggressive NDA example
    page.locator(
        "div:has(> div > label:has-text('Load a committed example'))"
    ).get_by_role("combobox").click()
    _hold(page, 0.7)
    page.get_by_role("option", name="Aggressive vendor NDA (triggers Loops 4 + 5)").click()
    _hold(page, 0.7)
    page.get_by_role("button", name="Load example").click()
    _settle(page, 600)
    doc_text = page.locator("div:has(> div > label:has-text('Document text'))").locator("textarea")
    _box(page, doc_text, "Aggressive vendor NDA — clause 2 transfers data across borders", anchor="tr")
    _set_explain(page, "Clause 2 (cross-border transfer) violates UAE PDPL. The Reviewer catches it — but cites the WRONG article. That's Loop 4.")
    _hold(page, 7.0, "NDA loaded with highlight")
    _clear_boxes(page)

    # 0:25–0:32 — submit
    submit_btn = page.get_by_role("button", name="Review document")
    _box(page, submit_btn, "Submit — 5 agents will run, including the Citation Verifier", anchor="rt")
    _set_explain(page, "Pipeline: Reviewer → Verifier → (Loop 4 if mismatch) → Drafter → Reviewer-as-critic → (Loop 5 if vague) → Synthesis.")
    _hold(page, 3.5)
    _clear_boxes(page)
    submit_btn.click()
    page.wait_for_selector("text=Recommendation:", timeout=60_000)
    _hold(page, 3.0, "audit populates")

    # 0:32–0:42 — Loops fired pill
    loops_pill = page.get_by_text("Loops fired:").first.locator("..")
    _box(page, loops_pill, "Both feedback loops fired: Loop 4 + Loop 5", anchor="tl")
    _set_explain(page, "Green pill = audit caught a citation mismatch (Loop 4) AND critiqued a counter-proposal draft (Loop 5). Checks and balances.")
    _hold(page, 7.0, "loops fired pill")
    _clear_boxes(page)

    # 0:42–1:05 — Loop 4 rejection — THE moment per PRD §16
    print("  expanding Loop 4 rejection + recovery…")
    audit_details = page.locator("[data-testid='stExpander']")
    used: set[int] = set()
    targets = [
        (
            "Citation Verifier — verify_citation [Loop 4]",
            "THE KILLER MOMENT — Loop 4 rejection: article 99 was not in the corpus",
            "Loop 4 fires: Reviewer cited 'Federal Decree-Law 45/2021 Art 99' — Verifier ran exact retrieval, no match. Hallucination caught.",
            14.0,
        ),
        (
            "Reviewer — re_cite [Loop 4]",
            "Loop 4 recovery: Reviewer re-cites Article 7 (the real PDPL consent article)",
            "Reviewer re-runs with Verifier's candidates and proposes Article 7 — the real PDPL consent provision. Self-correction, no human.",
            8.0,
        ),
        (
            "Reviewer — critique_draft [Loop 5]",
            "Loop 5: Reviewer-as-critic rejects the first counter-proposal draft",
            "Loop 5 (Counter-Proposal Critique): first draft was too vague — 'tighten with explicit obligations + the cited article'. Draft revises.",
            7.0,
        ),
    ]
    expanded = 0
    for target, caption, explain, hold_s in targets:
        for i in range(audit_details.count()):
            if i in used:
                continue
            summary = audit_details.nth(i).locator("summary").first
            try:
                txt = summary.inner_text(timeout=400).strip().replace("\n", " ")
            except Exception:
                continue
            if target in txt:
                try:
                    summary.click(timeout=1200)
                    used.add(i)
                    expanded += 1
                    page.wait_for_timeout(400)
                    _box(page, audit_details.nth(i), caption, anchor="tl")
                    _set_explain(page, explain)
                    _hold(page, hold_s, target)
                    _clear_boxes(page)
                    break
                except Exception:
                    pass
    print(f"    expanded {expanded} entries")

    # 1:05–1:25 — show Finding 1 + counter-proposal
    page.evaluate("window.scrollBy(0, 700)")
    _settle(page, 400)
    finding_1_cite = page.get_by_text("verified on attempt 2", exact=False).first.locator("..")
    _box(page, finding_1_cite, "Finding 1: PDPL Art 7 VERIFIED (verified on attempt 2)", anchor="tr")
    _set_explain(page, "Finding 1's citation now shows VERIFIED with '(verified on attempt 2)' — Verifier ran the loop, Reviewer recovered.")
    _hold(page, 6.5, "Finding 1 with attempt-2 callout")
    _clear_boxes(page)

    counter_prop = page.get_by_text("refined over 2 Loop-5 critique cycles", exact=False).first
    _box(page, counter_prop, "Counter-proposal refined over 2 Loop-5 critique cycles", anchor="bl")
    _set_explain(page, "Counter-proposal is the THIRD version — first rejected, second critiqued, third accepted. Anchored on the verified statute.")
    _hold(page, 6.0, "counter-proposal Loop 5 callout")
    _clear_boxes(page)

    # 1:25–1:35 — scroll back up to DO NOT SIGN banner
    page.evaluate("window.scrollTo(0, 0)")
    _settle(page, 400)
    rec_banner = page.locator(
        "[data-testid='stMarkdownContainer']:has-text('Recommendation: DO NOT SIGN')"
    ).first
    _box(page, rec_banner, "Final verdict: DO NOT SIGN — material PDPL risk on cross-border transfer", anchor="tr")
    _set_explain(page, "M2 in 90s: POST /run mode=use returns verified citations · Loops 4+5 fire · NDA copilot end-to-end. Reviewable, auditable, replayable.")
    _hold(page, 8.0, "DO NOT SIGN closing frame")
    _clear_all(page)

    video_obj = page.video
    ctx.close()
    webm_path = Path(video_obj.path()) if video_obj else None
    if webm_path and webm_path.exists():
        target = DEMOS / "02_use_mode_walkthrough.mp4"
        _convert_webm(webm_path, target)
        print(f"  → {target.relative_to(ROOT)}  ({target.stat().st_size//1024} KB)")
    else:
        raise RuntimeError("video #2 not produced")


# ----- video #3 — Arabic intake ---------------------------------------------


def record_arabic_intake(p) -> None:
    """Targets ~75s with annotations — heavy on RTL rendering + Arabic reply."""
    print("[video 3/3] Arabic intake walkthrough")
    ctx = _make_context(p, RECORDINGS / "03_arabic")
    page = ctx.new_page()
    page.goto(URL)
    _settle(page, 2200)

    _inject_styles(page)
    _set_title_bar(page, "WAKEEL — ARABIC INTAKE: UAE hospital workflow, right-to-left, agents reply in Arabic")
    _set_explain(page, "Same factory, different language. An Abu Dhabi hospital describes its NDA workflow in Arabic — Interviewer detects, chat renders RTL.")

    # 0:00–0:05 — Build mode
    _switch_mode(page, "Build")
    _hold(page, 4.0, "title + intro")

    # 0:05–0:22 — paste Arabic
    chat_input = page.get_by_placeholder(
        "e.g. Review vendor NDAs against our fintech data-handling stance"
    )
    chat_input.click()
    chat_input.fill(ARABIC_PROMPT)
    _box(page, chat_input, "Arabic intake — text rendered right-to-left (RTL)", anchor="tl")
    _set_explain(page, "Cursor sits on the RIGHT — Streamlit detected Arabic Unicode (U+0600–U+06FF) and switched rendering to RTL automatically.")
    _hold(page, 12.0, "Arabic in input with highlight")
    _clear_boxes(page)
    chat_input.press("Enter")

    # 0:22–0:35 — wait for completion
    _set_explain(page, "Same six agents as the English build — but every prompt flows with language='ar' and the Interviewer's user-facing reply is Arabic.")
    page.wait_for_selector("text=Loops fired", timeout=60_000)
    _hold(page, 6.0, "Arabic chat bubble + Arabic Interviewer reply rendering")

    # 0:35–0:45 — highlight the Arabic user bubble
    user_bubble = page.locator("[data-testid='stChatMessage']").first
    _box(page, user_bubble, "User message — Arabic, rendered RTL", anchor="br")
    _set_explain(page, "The Arabic intake renders inside the chat bubble with proper RTL alignment — text flows right-to-left, punctuation mirrored.")
    _hold(page, 7.0, "user bubble highlighted")
    _clear_boxes(page)

    # 0:45–0:55 — highlight the assistant Arabic reply
    bubbles = page.locator("[data-testid='stChatMessage']")
    if bubbles.count() >= 2:
        assistant_bubble = bubbles.nth(1)
        _box(page, assistant_bubble, "Interviewer reply — in Arabic", anchor="tl")
        _set_explain(page, "Interviewer's response_to_user comes back in Arabic. No translation API — the agent is language-aware via language='ar'.")
        _hold(page, 7.0, "assistant Arabic reply")
        _clear_boxes(page)

    # 0:55–1:10 — expand the Interviewer audit entry to show language: "ar"
    print("  expanding Interviewer audit entry…")
    audit_details = page.locator("[data-testid='stExpander']")
    for i in range(audit_details.count()):
        summary = audit_details.nth(i).locator("summary").first
        try:
            txt = summary.inner_text(timeout=400).strip().replace("\n", " ")
        except Exception:
            continue
        if "Interviewer — extract_requirements" in txt:
            try:
                summary.click(timeout=1200)
                page.wait_for_timeout(400)
                _box(page, audit_details.nth(i), "Audit: Interviewer extract_requirements — language: 'ar'", anchor="tl")
                _set_explain(page, "Audit JSON proves language='ar' was carried through the pipeline — every downstream agent received it and respected it.")
                _hold(page, 10.0, "Interviewer entry highlighted")
                _clear_boxes(page)
                break
            except Exception:
                pass

    # 1:10–end — closing frame
    page.evaluate("window.scrollTo(0, 0)")
    _set_title_bar(page, "WAKEEL — ARABIC INTAKE: bilingual agent factory, audit-trailed end-to-end")
    _set_explain(page, "M2 Criterion 4 satisfied: Arabic input on the Interviewer, verified on input_examples/build_02_hospital_nda_ar.json.")
    _hold(page, 11.0, "closing frame")
    _clear_all(page)

    video_obj = page.video
    ctx.close()
    webm_path = Path(video_obj.path()) if video_obj else None
    if webm_path and webm_path.exists():
        target = DEMOS / "03_arabic_intake_walkthrough.mp4"
        _convert_webm(webm_path, target)
        print(f"  → {target.relative_to(ROOT)}  ({target.stat().st_size//1024} KB)")
    else:
        raise RuntimeError("video #3 not produced")


# ----- main ------------------------------------------------------------------


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH — install via `brew install ffmpeg`", file=sys.stderr)
        return 1

    print(f"recording to {RECORDINGS.relative_to(ROOT)}/ then writing MP4s to demos/")

    t0 = time.time()
    with sync_playwright() as p:
        copilot = record_build_mode(p)
        record_use_mode(p, copilot)
        record_arabic_intake(p)
    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s")

    # Optionally keep webms for debugging (set WAKEEL_KEEP_WEBM=1)
    import os
    if not os.environ.get("WAKEEL_KEEP_WEBM"):
        shutil.rmtree(RECORDINGS, ignore_errors=True)
        print(f"cleaned up {RECORDINGS.name}/")
    else:
        print(f"kept intermediate webms under {RECORDINGS.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
