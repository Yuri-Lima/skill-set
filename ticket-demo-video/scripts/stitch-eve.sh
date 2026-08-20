#!/usr/bin/env bash
# Concat consecutive Eve talking-head clips (each ≤15s API limit) into one file.
# Normalizes size/fps first so concat is safe. Length is the sum of the clips.
#   bash stitch-eve.sh --out eve.mp4 clip1.mp4 clip2.mp4 [...]
set -euo pipefail

OUT=""
CLIPS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    -*) echo "unknown arg: $1" >&2; exit 2 ;;
    *) CLIPS+=("$1"); shift ;;
  esac
done
if [[ -z "$OUT" || ${#CLIPS[@]} -lt 1 ]]; then
  echo "usage: $0 --out OUT.mp4 CLIP [CLIP...]" >&2
  exit 2
fi

norm() {
  local src="$1" dest="$2"
  ffmpeg -y -i "$src" \
    -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p" \
    -c:v libx264 -c:a aac -ar 48000 -ac 2 -preset fast "$dest"
}

if [[ ${#CLIPS[@]} -eq 1 ]]; then
  norm "${CLIPS[0]}" "$OUT"
  echo "wrote $OUT"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LIST="$TMP/list.txt"
: > "$LIST"
i=0
for clip in "${CLIPS[@]}"; do
  dest="$TMP/n$(printf '%02d' "$i").mp4"
  norm "$clip" "$dest"
  printf "file '%s'\n" "$dest" >> "$LIST"
  i=$((i + 1))
done

ffmpeg -y -f concat -safe 0 -i "$LIST" -c copy -movflags +faststart "$OUT"
echo "wrote $OUT"
