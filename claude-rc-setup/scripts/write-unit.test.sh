#!/usr/bin/env bash
# Render the unit file on any OS. Does not touch systemd.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WRITE="$DIR/write-unit.sh"

die() { echo "FAIL: $*" >&2; exit 1; }

out="$("$WRITE" --print \
  --name box-1 \
  --user yuri \
  --home /home/yuri \
  --workdir /home/yuri/app \
  --bin /home/yuri/.local/bin/claude)"

printf '%s\n' "$out" | grep -q '^Description=Claude Code Remote Control (box-1)$' \
  || die "description"
printf '%s\n' "$out" | grep -q '^User=yuri$' || die "user"
printf '%s\n' "$out" | grep -q '^WorkingDirectory=/home/yuri/app$' || die "workdir"
printf '%s\n' "$out" | grep -q '^Environment=HOME=/home/yuri$' || die "home"
printf '%s\n' "$out" | grep -q '^ExecStart=/home/yuri/.local/bin/claude remote-control --name "box-1" --spawn same-dir$' \
  || die "execstart: $out"
printf '%s\n' "$out" | grep -q '^Restart=always$' || die "restart"

spaced="$("$WRITE" --print \
  --name 'lab box' \
  --user yuri \
  --home /home/yuri \
  --workdir /srv/proj \
  --bin /usr/bin/claude)"
printf '%s\n' "$spaced" | grep -q 'Description=Claude Code Remote Control (lab box)' \
  || die "spaced description"
printf '%s\n' "$spaced" | grep -q 'ExecStart=/usr/bin/claude remote-control --name "lab box" --spawn same-dir' \
  || die "spaced execstart"

if "$WRITE" --print --name x --user y --home /h --workdir /w --bin claude >/dev/null 2>&1; then
  die "relative bin should fail"
fi
if "$WRITE" --print --name x --user y --home /home/y --workdir /home/y --bin /usr/bin/claude >/dev/null 2>&1; then
  die "WORKDIR=HOME should fail"
fi
if "$WRITE" --print --name x --user y --home /h --workdir / --bin /usr/bin/claude >/dev/null 2>&1; then
  die "WORKDIR=/ should fail"
fi
if "$WRITE" --print --name 'say "hi"' --user y --home /h --workdir /w --bin /usr/bin/claude >/dev/null 2>&1; then
  die "quoted NAME should fail"
fi

echo ok
