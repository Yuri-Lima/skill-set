#!/usr/bin/env bash
# Put a recorded studio board (left) behind Eve (right). Audio = Eve.
#   bash compose-studio.sh --eve eve.mp4 --studio studio.webm --out presenter.mp4
set -euo pipefail

EVE=""
STUDIO=""
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --eve) EVE="$2"; shift 2 ;;
    --studio) STUDIO="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$EVE" || -z "$STUDIO" || -z "$OUT" ]]; then
  echo "usage: $0 --eve EVE.mp4 --studio STUDIO.webm --out OUT.mp4" >&2
  exit 2
fi

probe() {
  ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"
}

EVE_DUR="$(probe "$EVE")"
STU_DUR="$(probe "$STUDIO")"
TARGET="$(python3 -c "print(max(float('${EVE_DUR}'), float('${STU_DUR}')))")"
PAD_EVE="$(python3 -c "print(max(0.0, ${TARGET} - float('${EVE_DUR}') + 0.2))")"
PAD_STU="$(python3 -c "print(max(0.0, ${TARGET} - float('${STU_DUR}') + 0.2))")"

# Eve is a chroma-green cutout on the right; studio cards stay left.
ffmpeg -y -i "$STUDIO" -i "$EVE" -filter_complex "\
[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p,tpad=stop_mode=clone:stop_duration=${PAD_STU}[bg];\
[1:v]fps=24,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,crop=820:720:360:0,chromakey=0x00FF00:0.20:0.08,despill=green,format=yuva420p,colorchannelmixer=aa=0.72,tpad=stop_mode=clone:stop_duration=${PAD_EVE}[ev];\
[bg][ev]overlay=720:40:eof_action=repeat,format=yuv420p[v]" \
  -map "[v]" -map 1:a:0? -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 \
  -t "$TARGET" -movflags +faststart "$OUT"

echo "wrote $OUT (${TARGET}s)"
