#!/usr/bin/env bash
# Concat Act 1 studio + Act 2 screencap into one 1280x720@24 picture track.
#   build-two-act-picture.sh --studio studio.webm --studio-end 85.292 \
#     --screencap ~/Desktop/aaaa.mov --out picture.mp4
set -euo pipefail

STUDIO=""
STUDIO_END=""
SCREENCAP=""
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --studio) STUDIO="$2"; shift 2 ;;
    --studio-end) STUDIO_END="$2"; shift 2 ;;
    --screencap) SCREENCAP="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$STUDIO" || -z "$STUDIO_END" || -z "$SCREENCAP" || -z "$OUT" ]]; then
  echo "usage: $0 --studio STUDIO --studio-end SECONDS --screencap MOV --out PICTURE.mp4" >&2
  exit 2
fi
if [[ ! -f "$STUDIO" || ! -f "$SCREENCAP" ]]; then
  echo "missing studio or screencap" >&2
  exit 1
fi

VF="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ffmpeg -y -i "$STUDIO" -t "$STUDIO_END" -vf "$VF" -an -c:v libx264 -preset fast "$TMP/a.mp4"
ffmpeg -y -i "$SCREENCAP" -vf "$VF" -an -c:v libx264 -preset fast "$TMP/b.mp4"
printf "file '%s'\nfile '%s'\n" "$TMP/a.mp4" "$TMP/b.mp4" > "$TMP/list.txt"
ffmpeg -y -f concat -safe 0 -i "$TMP/list.txt" -c copy "$OUT"
echo "wrote $OUT"
