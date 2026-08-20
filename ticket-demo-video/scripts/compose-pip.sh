#!/usr/bin/env bash
# Overlay chromakeyed Eve on a live UI recording. Audio = presenter only.
# On ui-clock beats with "point": true, swap in the pointing clip (arm raise).
#   bash compose-pip.sh --ui ui.webm --presenter eve.mp4 --out ticket.mp4
#   bash compose-pip.sh --ui ui.webm --presenter eve.mp4 \
#     --point assets/eve-point.mp4 --clock ui-clock.json --slug eve-cutout-point --out ticket.mp4
set -euo pipefail

UI=""
PRESENTER=""
OUT=""
TARGET_ARG=""
PIP_W="520"
UI_TRIM=""
POINT=""
CLOCK=""
SLUG=""
KEY="0x00FF00"
SIM="0.20"
BLEND="0.08"
POINT_HOLD="2.0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ui) UI="$2"; shift 2 ;;
    --presenter) PRESENTER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --target) TARGET_ARG="$2"; shift 2 ;;
    --pip-width) PIP_W="$2"; shift 2 ;;
    --ui-trim) UI_TRIM="$2"; shift 2 ;;
    --point) POINT="$2"; shift 2 ;;
    --clock) CLOCK="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --similarity) SIM="$2"; shift 2 ;;
    --blend) BLEND="$2"; shift 2 ;;
    --point-hold) POINT_HOLD="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$UI" || -z "$PRESENTER" || -z "$OUT" ]]; then
  echo "usage: $0 --ui UI --presenter EVE.mp4 [--point POINT.mp4] [--clock ui-clock.json] --out OUT.mp4" >&2
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

KEY_VF="chromakey=${KEY}:${SIM}:${BLEND},despill=green,format=yuva420p"

# Idle Eve is on the right of a 16:9 plate — crop the empty left before scale.
TALK_CROP="640:720:540:0"
# Pointing plate keeps the left so the finger stays in frame.
POINT_CROP="1220:720:8:0"
POINT_W="$(python3 -c "print(int(${PIP_W}) + 120)")"

python3 - "$TMP" "$CLOCK" "$POINT_HOLD" "$PIP_W" "$POINT_W" "$KEY_VF" "$TALK_CROP" "$POINT_CROP" "$POINT" <<'PY' > "$TMP/filter.txt"
import json, sys
from pathlib import Path

tmp, clock_path, hold_s, pip_w, point_w, key_vf, talk_crop, point_crop, point = sys.argv[1:]
hold = float(hold_s)
windows = []
if clock_path and Path(clock_path).is_file():
    data = json.loads(Path(clock_path).read_text())
    for beat in data.get("beats") or []:
        if not beat.get("point"):
            continue
        start = float(beat["at"])
        end = start + float(beat.get("hold") or hold)
        windows.append((start, end))

talk = (
    f"[1:v]crop={talk_crop},{key_vf},scale={pip_w}:-1[talk]"
)
hide = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows)
talk_en = f"not({hide})" if hide else "1"
lines = [talk]
inputs_after = 0
if point and Path(point).is_file() and windows:
    n = len(windows)
    splits = "".join(f"[s{i}]" for i in range(n))
    lines.append(
        f"[2:v]fps=24,crop={point_crop},{key_vf},scale={point_w}:-1,split={n}{splits}"
    )
    last = "base"
    lines.append(
        f"[0:v][talk]overlay=W-w-10:H-h+6:enable='{talk_en}':eof_action=repeat[{last}]"
    )
    for i, (a, b) in enumerate(windows):
        dur = b - a
        p = f"p{i}"
        nxt = f"o{i}"
        lines.append(
            f"[s{i}]trim=0:{dur:.3f},setpts=PTS-STARTPTS+{a:.3f}/TB[{p}]"
        )
        lines.append(
            f"[{last}][{p}]overlay=W-w-90:H-h+8:enable='between(t,{a:.3f},{b:.3f})'[{nxt}]"
        )
        last = nxt
    lines.append(f"[{last}]format=yuv420p[v]")
    inputs_after = 1
else:
    lines.append(
        "[0:v][talk]overlay=W-w-10:H-h+6:eof_action=repeat,format=yuv420p[v]"
    )

Path(tmp, "has_point").write_text("1" if inputs_after else "0")
print(";".join(lines))
PY

HAS_POINT="$(cat "$TMP/has_point")"
FILTER="$(cat "$TMP/filter.txt")"

if [[ "$HAS_POINT" == "1" ]]; then
  ffmpeg -y -i "$TMP/ui.mp4" -i "$TMP/pres.mp4" -i "$POINT" \
    -filter_complex "$FILTER" \
    -map "[v]" -map 1:a:0 -c:v libx264 -pix_fmt yuv420p -c:a aac \
    -t "$TARGET" -movflags +faststart "$OUT"
else
  ffmpeg -y -i "$TMP/ui.mp4" -i "$TMP/pres.mp4" \
    -filter_complex "$FILTER" \
    -map "[v]" -map 1:a:0 -c:v libx264 -pix_fmt yuv420p -c:a aac \
    -t "$TARGET" -movflags +faststart "$OUT"
fi

echo "wrote $OUT (${TARGET}s)"

if [[ -n "$SLUG" ]]; then
  ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
  PUB="${ROOT}/docs/ticket-demos/${SLUG}.mp4"
  mkdir -p "$(dirname "$PUB")"
  cp -f "$OUT" "$PUB"
  echo "published $PUB"
fi
