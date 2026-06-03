#!/usr/bin/env bash
# Generate 3 placeholder MP4 stubs for demos/ so the PR is shape-complete.
# Each is a 5-second 1280x720 H.264 MP4 with on-screen text pointing to the
# runbook. Real recordings replace these per demos/RUNBOOK.md.

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)/demos"
mkdir -p "$DEMO_DIR"

make_stub () {
    local file="$1"
    local title="$2"
    local subtitle="$3"
    ffmpeg -y -loglevel error \
        -f lavfi -i "color=c=black:s=1280x720:d=5" \
        -vf "
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:text='$title':\
fontcolor=white:fontsize=42:x=(w-text_w)/2:y=(h-text_h)/2 - 80,\
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:text='$subtitle':\
fontcolor=#9ca3af:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2,\
            drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:text='PLACEHOLDER — see demos/RUNBOOK.md':\
fontcolor=#f59e0b:fontsize=24:x=(w-text_w)/2:y=(h-text_h)/2 + 80
        " \
        -c:v libx264 -pix_fmt yuv420p -preset veryfast -t 5 \
        "$DEMO_DIR/$file"
    echo "  wrote $file"
}

make_stub "01_build_mode_walkthrough.mp4"      "Build mode walkthrough"                 "Sarah → factory mints a copilot (60-90s)"
make_stub "02_use_mode_walkthrough.mp4"        "Use mode walkthrough"                   "Citation Verifier rejection moment (60-90s)"
make_stub "03_arabic_intake_walkthrough.mp4"   "Arabic intake walkthrough"              "Interviewer accepts Arabic, replies Arabic (60-90s)"

echo
echo "Done. Real recordings go in $DEMO_DIR per RUNBOOK.md."
