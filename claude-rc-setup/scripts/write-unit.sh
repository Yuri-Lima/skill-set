#!/usr/bin/env bash
# Render (and optionally install) claude-rc.service from the template.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMPL="$SKILL_DIR/references/claude-rc.service.tmpl"
UNIT_PATH="/etc/systemd/system/claude-rc.service"

NAME=""
RUNUSER=""
HOMEDIR=""
WORKDIR=""
BIN=""
MODE="print"

usage() {
  cat <<'EOF'
Usage: write-unit.sh --name NAME --user USER --home HOME --workdir DIR --bin ABS_CLAUDE
                     [--print | --install] [--unit-path PATH]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --user) RUNUSER="$2"; shift 2 ;;
    --home) HOMEDIR="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --bin) BIN="$2"; shift 2 ;;
    --print) MODE="print"; shift ;;
    --install) MODE="install"; shift ;;
    --unit-path) UNIT_PATH="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

need() {
  local label="$1" val="$2"
  if [[ -z "$val" ]]; then
    echo "missing $label" >&2
    exit 2
  fi
}

need --name "$NAME"
need --user "$RUNUSER"
need --home "$HOMEDIR"
need --workdir "$WORKDIR"
need --bin "$BIN"

if [[ ! -f "$TMPL" ]]; then
  echo "missing template: $TMPL" >&2
  exit 2
fi

is_abs() { [[ "$1" == /* ]]; }

if ! is_abs "$BIN"; then
  echo "ExecStart bin must be absolute, got: $BIN" >&2
  exit 2
fi
if ! is_abs "$WORKDIR"; then
  echo "WORKDIR must be absolute, got: $WORKDIR" >&2
  exit 2
fi
if ! is_abs "$HOMEDIR"; then
  echo "HOME must be absolute, got: $HOMEDIR" >&2
  exit 2
fi
if [[ "$WORKDIR" == / ]]; then
  echo "WORKDIR cannot be /" >&2
  exit 2
fi
if [[ "$WORKDIR" == "$HOMEDIR" ]]; then
  echo "WORKDIR cannot be HOME ($HOMEDIR); pick a project directory" >&2
  exit 2
fi
if [[ "$NAME" == *$'\n'* || "$NAME" == *'"'* ]]; then
  echo "NAME cannot contain quotes or newlines" >&2
  exit 2
fi

render() {
  python3 - "$TMPL" "$NAME" "$RUNUSER" "$HOMEDIR" "$WORKDIR" "$BIN" <<'PY'
import sys

path, name, user, home, workdir, binary = sys.argv[1:]
text = open(path, encoding="utf-8").read()
quoted = '"' + name.replace("\\", "\\\\") + '"'
out = []
for line in text.splitlines(True):
    if line.startswith("ExecStart="):
        line = line.replace("@BIN@", binary).replace("@NAME@", quoted)
    else:
        line = (
            line.replace("@NAME@", name)
            .replace("@RUNUSER@", user)
            .replace("@HOMEDIR@", home)
            .replace("@WORKDIR@", workdir)
            .replace("@BIN@", binary)
        )
    out.append(line)
sys.stdout.write("".join(out))
PY
}

body="$(render)"

if [[ "$MODE" == print ]]; then
  printf '%s' "$body"
  [[ "$body" == *$'\n' ]] || printf '\n'
  exit 0
fi

tmp="$(mktemp)"
printf '%s' "$body" >"$tmp"
[[ "$body" == *$'\n' ]] || printf '\n' >>"$tmp"
if [[ "$(id -u)" -eq 0 ]]; then
  mkdir -p "$(dirname "$UNIT_PATH")"
  cp "$tmp" "$UNIT_PATH"
  chmod 644 "$UNIT_PATH"
else
  sudo mkdir -p "$(dirname "$UNIT_PATH")"
  sudo cp "$tmp" "$UNIT_PATH"
  sudo chmod 644 "$UNIT_PATH"
fi
rm -f "$tmp"
printf 'wrote %s\n' "$UNIT_PATH"
