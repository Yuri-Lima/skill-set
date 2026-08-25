#!/usr/bin/env bash
# Overlay chromakeyed Eve on a live UI recording. Audio = presenter only.
# Talking pose only (no pointing). Wider crop keeps both arms. Slight translucency.
#   bash compose-pip.sh --ui ui.webm --presenter eve.mp4 --slug <slug> --out ticket.mp4
set -euo pipefail

UI=""
PRESENTER=""
OUT=""
TARGET_ARG=""
PIP_W="580"
UI_TRIM=""
SLUG=""
KEY="0x00FF00"
SIM="0.20"
BLEND="0.08"
ALPHA="0.72"
# Wider than a head-only crop so her right arm (viewer-left) stays in frame.
TALK_CROP="820:720:360:0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ui) UI="$2"; shift 2 ;;
    --presenter) PRESENTER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --target) TARGET_ARG="$2"; shift 2 ;;
    --pip-width) PIP_W="$2"; shift 2 ;;
    --ui-trim) UI_TRIM="$2"; shift 2 ;;
    --alpha) ALPHA="$2"; shift 2 ;;
    --crop) TALK_CROP="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --similarity) SIM="$2"; shift 2 ;;
    --blend) BLEND="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --clock|--point|--point-hold) shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$UI" || -z "$PRESENTER" || -z "$OUT" ]]; then
  echo "usage: $0 --ui UI --presenter EVE.mp4 [--alpha 0.72] [--slug SLUG] --out OUT.mp4" >&2
  exit 2
fi

probe() {
  ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"
}

if [[ -z "$UI_TRIM" && -f "${UI}.sync.json" ]]; then
  UI_TRIM="$(python3 -c "import json; print(json.load(open('${UI}.sync.json'))['runMs']/1000)")"
fi
UI_TRIM="${UI_TRIM:-0}"

UI_DUR="$(python3 -c "print(max(0.1, float('$(probe "$UI")') - float('${UI_TRIM}')))")"
PRES_DUR="$(probe "$PRESENTER")"
if [[ -n "$TARGET_ARG" ]]; then
  TARGET="$(python3 -c "print(max(float('${TARGET_ARG}'), float('${UI_DUR}'), float('${PRES_DUR}')))")"
else
  TARGET="$(python3 -c "print(max(float('${UI_DUR}'), float('${PRES_DUR}')))")"
fi
PAD_UI="$(python3 -c "print(max(0.0, ${TARGET} - float('${UI_DUR}') + 0.25))")"
PAD_PRES="$(python3 -c "print(max(0.0, ${TARGET} - float('${PRES_DUR}') + 0.25))")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ffmpeg -y -ss "$UI_TRIM" -i "$UI" \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,tpad=stop_mode=clone:stop_duration=${PAD_UI}" \
  -t "$TARGET" -an -c:v libx264 -pix_fmt yuv420p -preset fast "$TMP/ui.mp4"

ffmpeg -y -i "$PRESENTER" \
  -vf "fps=24,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,tpad=stop_mode=clone:stop_duration=${PAD_PRES}" \
  -af "apad=pad_dur=${PAD_PRES}" \
  -t "$TARGET" -c:v libx264 -c:a aac -ar 48000 -ac 2 -preset fast "$TMP/pres.mp4"

FILTER="[1:v]crop=${TALK_CROP},chromakey=${KEY}:${SIM}:${BLEND},despill=green,format=yuva420p,colorchannelmixer=aa=${ALPHA},scale=${PIP_W}:-1[talk];[0:v][talk]overlay=W-w-8:H-h+4:eof_action=repeat,format=yuv420p[v]"

ffmpeg -y -i "$TMP/ui.mp4" -i "$TMP/pres.mp4" \
  -filter_complex "$FILTER" \
  -map "[v]" -map 1:a:0 -c:v libx264 -pix_fmt yuv420p -c:a aac \
  -t "$TARGET" -movflags +faststart "$OUT"

echo "wrote $OUT (${TARGET}s)"

if [[ -n "$SLUG" ]]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  PUB="${ROOT}/docs/ticket-demos/${SLUG}.mp4"
  mkdir -p "$(dirname "$PUB")"
  cp -f "$OUT" "$PUB"
  echo "published $PUB"
fi
