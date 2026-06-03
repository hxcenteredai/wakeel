"""Annotate the raw use-mode screenshots with Gate-4-style red callouts.

Reads bounding boxes from ``docs/use-mode-evidence/raw/_bboxes.json``
(produced by ``capture_use_mode.py``) so coordinates stay in sync with the
live DOM rather than drifting against magic numbers.

Output: ``docs/use-mode-evidence/<basename>-annotated.png``

Style mirrors ``docs/gate4-evidence/*-annotated.png``:
  - Dark top banner with white section title.
  - Red 8px-stroke rectangles around the proof element.
  - White-on-red inline labels attached to each rectangle.
  - Light-grey bottom banner with a one-line caption.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "docs" / "use-mode-evidence" / "raw"
OUT = ROOT / "docs" / "use-mode-evidence"

TOP_BANNER_H = 110
BOTTOM_BANNER_MIN_H = 100
RED = (220, 38, 38)
DARK_BG = (15, 23, 42)
LIGHT_BG = (243, 244, 246)
WHITE = (255, 255, 255)
DARK_TEXT = (17, 24, 39)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
) -> tuple[int, int]:
    pad_x, pad_y = 14, 8
    tw = draw.textlength(text, font=font)
    ascent, descent = font.getmetrics()
    th = ascent + descent
    x, y = xy
    rect = (x, y, x + int(tw) + 2 * pad_x, y + th + 2 * pad_y)
    draw.rectangle(rect, fill=RED)
    draw.text((x + pad_x, y + pad_y - descent // 2), text, fill=WHITE, font=font)
    return rect[2] - rect[0], rect[3] - rect[1]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def annotate(
    src_name: str,
    title: str,
    caption: str,
    callouts: list[tuple[str, str, str]],
    bboxes: dict[str, list[int]],
) -> Path:
    """callouts entries: (bbox_key, label, anchor) where anchor ∈ tr|tl|bl|br."""
    src = RAW / src_name
    img = Image.open(src).convert("RGB")
    iw, ih = img.size

    title_font = _font(54, bold=True)
    caption_font = _font(38)
    label_font = _font(34, bold=True)

    margin_x = 60
    draw_probe = ImageDraw.Draw(img)
    caption_lines = _wrap(draw_probe, caption, caption_font, iw - 2 * margin_x)
    line_h = caption_font.getmetrics()[0] + caption_font.getmetrics()[1]
    bottom_h = max(BOTTOM_BANNER_MIN_H, 40 + line_h * len(caption_lines) + 20)

    out_h = TOP_BANNER_H + ih + bottom_h
    canvas = Image.new("RGB", (iw, out_h), WHITE)
    canvas.paste(img, (0, TOP_BANNER_H))
    d = ImageDraw.Draw(canvas)

    d.rectangle((0, 0, iw, TOP_BANNER_H), fill=DARK_BG)
    title_ascent = title_font.getmetrics()[0]
    d.text(
        (margin_x, (TOP_BANNER_H - title_ascent) // 2 - 4),
        title,
        fill=WHITE,
        font=title_font,
    )

    by0 = TOP_BANNER_H + ih
    d.rectangle((0, by0, iw, out_h), fill=LIGHT_BG)
    y = by0 + 20
    for line in caption_lines:
        d.text((margin_x, y), line, fill=DARK_TEXT, font=caption_font)
        y += line_h

    for bbox_key, label, anchor in callouts:
        if bbox_key not in bboxes:
            print(f"  [warn] missing bbox {bbox_key!r} in {src_name}", file=sys.stderr)
            continue
        x1, y1, x2, y2 = bboxes[bbox_key]
        y1 += TOP_BANNER_H
        y2 += TOP_BANNER_H
        d.rectangle((x1, y1, x2, y2), outline=RED, width=8)

        pad_x, pad_y = 14, 8
        tw = d.textlength(label, font=label_font)
        ascent, descent = label_font.getmetrics()
        th = ascent + descent
        lw = int(tw) + 2 * pad_x
        lh = th + 2 * pad_y

        if anchor == "tr":
            lx, ly = min(x2 - lw, iw - lw - 4), max(0, y1 - lh - 6)
        elif anchor == "tl":
            lx, ly = x1, max(0, y1 - lh - 6)
        elif anchor == "bl":
            lx, ly = x1, y2 + 6
        elif anchor == "br":
            lx, ly = min(x2 - lw, iw - lw - 4), y2 + 6
        elif anchor == "rt":
            lx, ly = min(x2 + 12, iw - lw - 4), y1
        else:
            lx, ly = x1, max(0, y1 - lh - 6)

        d.rectangle((lx, ly, lx + lw, ly + lh), fill=RED)
        d.text(
            (lx + pad_x, ly + pad_y - descent // 2),
            label,
            fill=WHITE,
            font=label_font,
        )

    out_path = OUT / src_name.replace(".png", "-annotated.png")
    canvas.save(out_path, optimize=True)
    print(f"[annotate] {out_path.relative_to(ROOT)}  "
          f"({out_path.stat().st_size // 1024} KB, {canvas.size})")
    return out_path


def main() -> None:
    bboxes_path = RAW / "_bboxes.json"
    if not bboxes_path.exists():
        print("Run capture_use_mode.py first.", file=sys.stderr)
        sys.exit(1)
    with open(bboxes_path, "r", encoding="utf-8") as fh:
        all_bboxes = json.load(fh)

    annotate(
        "A-use-mode-landing.png",
        title="A. Use mode — landing (copilot dropdown populated from /copilots)",
        caption=(
            "After switching to Use mode, the Streamlit panel loads the copilot list "
            "from GET /copilots, populates the picker with cp_515a842c (minted earlier "
            "via Build mode), and exposes the document inputs alongside the committed-"
            "example shortcut menu."
        ),
        callouts=[
            ("use_radio", "Use mode selected", "rt"),
            ("copilot_picker", "Copilot picker fed by GET /copilots", "tr"),
            ("example_picker", "Load any of the 3 committed examples", "br"),
            ("audit_panel", "Audit panel armed (empty)", "tr"),
        ],
        bboxes=all_bboxes["A-use-mode-landing.png"],
    )

    annotate(
        "B-aggressive-nda-loaded.png",
        title="B. Aggressive-vendor NDA loaded (pre-submit)",
        caption=(
            "Loading the 'Aggressive vendor NDA' shortcut paste-loaded "
            "input_examples/use_mode/01_aggressive_vendor_nda.json into the form: "
            "title + full NDA body including the cross-border transfers clause that "
            "will exercise Loops 4 and 5. Submit is armed in primary red."
        ),
        callouts=[
            ("example_picker", "Aggressive vendor NDA chosen", "br"),
            ("doc_title", "Document title pre-filled", "tr"),
            ("doc_text", "Full NDA body pasted (5 clauses)", "tr"),
            ("submit_btn", "Primary submit armed", "br"),
        ],
        bboxes=all_bboxes["B-aggressive-nda-loaded.png"],
    )

    annotate(
        "C-aggressive-nda-reviewed.png",
        title="C. Reviewed — verified citations, DO-NOT-SIGN, Loops 4+5 visible",
        caption=(
            "Recommendation = DO NOT SIGN (PDPL cross-border risk). Summary metrics: "
            "3 findings (1 High, 1 Medium, 1 Low), 1 Loop-4 citation rejection, 2 "
            "Loop-5 critique cycles. Finding 1 cites PDPL Article 7 VERIFIED on "
            "attempt 2 — the Citation Verifier rejected the prior (hallucinated) cite "
            "and forced a re-cite (Loop 4). Counter-proposal was refined over 2 "
            "critique cycles (Loop 5)."
        ),
        callouts=[
            ("loops_pill", "Loops fired: Loop 4, Loop 5", "tl"),
            ("recommendation", "Recommendation: DO NOT SIGN", "tr"),
            ("metrics_row", "Findings 3, L4 rejections 1, L5 critiques 2", "br"),
            ("finding_1_citation", "PDPL Art 7 VERIFIED (attempt 2 = Loop 4 proof)", "tr"),
            ("counter_prop_loop5", "Counter-proposal refined over 2 Loop-5 cycles", "br"),
        ],
        bboxes=all_bboxes["C-aggressive-nda-reviewed.png"],
    )

    annotate(
        "D-audit-loops-4-5-expanded.png",
        title="D. Audit panel — Loop 4 rejection + Reviewer re-cite expanded",
        caption=(
            "Expanded Citation Verifier (Loop 4) entry shows Decision=rejected with "
            "Reason='Article not found in corpus; offered 3 candidates' against the "
            "hallucinated Federal Decree-Law 45/2021 Article 99, plus the 3 candidate "
            "articles the Verifier offered back. The Reviewer — re_cite (Loop 4) "
            "entry below shows the recovery: rejected art 99 → proposed art 7. The "
            "finding card on the left then carries 'verified on attempt 2'."
        ),
        callouts=[
            ("rejection_entry", "Loop 4 — rejected (Art 99 hallucinated)", "tl"),
            ("recite_entry", "Loop 4 — Reviewer re-cites Art 7", "tl"),
            ("finding_1_verified", "Citation marked VERIFIED on attempt 2", "tr"),
        ],
        bboxes=all_bboxes["D-audit-loops-4-5-expanded.png"],
    )

    annotate(
        "E-balanced-nda-reviewed.png",
        title="E. Balanced commercial NDA — different recommendation, contrasting metrics",
        caption=(
            "Same copilot, different document: "
            "input_examples/use_mode/02_balanced_partner_nda.json produces a GREEN "
            "recommendation 'Acceptable subject to the listed counter-proposals' "
            "— only 1 Medium finding, 0 Loop-4 rejections, 1 Loop-5 critique. Same "
            "pipeline, deterministic content-aware outcome."
        ),
        callouts=[
            ("recommendation", "Acceptable (GREEN recommendation)", "tr"),
            ("metrics_row", "1 finding, 0 L4 rejections, 1 L5 critique", "br"),
            ("finding_1", "Single Medium finding only", "tr"),
        ],
        bboxes=all_bboxes["E-balanced-nda-reviewed.png"],
    )


if __name__ == "__main__":
    main()
