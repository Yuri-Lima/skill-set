#!/usr/bin/env bash
# Copy the finished ticket demo into repo docs (not the gitignored scratch dir).
#   bash publish-demo.sh --in ticket-148.mp4 --slug mr-148-review-bugs
#   bash publish-demo.sh --in ticket-148.mp4 --out docs/ticket-demos/mr-148.mp4
set -euo pipefail

IN=""
SLUG=""
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --in) IN="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$IN" ]]; then
  echo "usage: $0 --in FINISHED.mp4 (--slug SLUG | --out PATH)" >&2
  exit 2
fi
if [[ ! -f "$IN" ]]; then
  echo "missing input: $IN" >&2
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ -z "$OUT" ]]; then
  if [[ -z "$SLUG" ]]; then
    echo "need --slug or --out" >&2
    exit 2
  fi
  OUT="${ROOT}/docs/ticket-demos/${SLUG}.mp4"
fi

mkdir -p "$(dirname "$OUT")"
cp -f "$IN" "$OUT"
echo "published $OUT"
