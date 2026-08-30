#!/usr/bin/env bash
# Check claude-rc after enable. Prints KEY=value. Exit 0; `verdict=` is the gate.
set -euo pipefail

WAIT=15
UNIT=claude-rc

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait) WAIT="$2"; shift 2 ;;
    --unit) UNIT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

kv() { printf '%s=%s\n' "$1" "$2"; }

have_systemctl=0
if command -v systemctl >/dev/null 2>&1; then
  have_systemctl=1
fi

sys() {
  if [[ "$have_systemctl" -eq 0 ]]; then
    return 1
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@" 2>/dev/null || systemctl "$@"
  fi
}

jctl() {
  if [[ "$(id -u)" -eq 0 ]]; then
    journalctl "$@"
  else
    sudo -n journalctl "$@" 2>/dev/null || journalctl "$@"
  fi
}

active="missing-systemctl"
enabled="missing-systemctl"
nrestarts=""
if [[ "$have_systemctl" -eq 1 ]]; then
  active="$(sys is-active "$UNIT" 2>/dev/null || echo inactive)"
  enabled="$(sys is-enabled "$UNIT" 2>/dev/null || echo disabled)"
  nrestarts="$(sys show "$UNIT" -p NRestarts --value 2>/dev/null || echo "")"
fi
kv active "$active"
kv enabled "$enabled"
kv nrestarts "${nrestarts:-}"

status_txt=""
if [[ "$have_systemctl" -eq 1 ]]; then
  status_txt="$(sys status "$UNIT" --no-pager 2>&1 || true)"
fi
kv status_present "$([[ -n "$status_txt" ]] && echo yes || echo no)"

journal=""
if command -v journalctl >/dev/null 2>&1; then
  journal="$(jctl -u "$UNIT" -n 50 --no-pager 2>/dev/null || true)"
fi
auth_error=no
if printf '%s' "$journal" | grep -qiE 'not logged in|not authenticated|/login|401|credentials'; then
  auth_error=yes
fi
kv journal_auth_error "$auth_error"

proc_line="$(ps -ax -o pid= -o args= 2>/dev/null | awk '/remote-control/ && !/awk/ { print }' | head -n 1 || true)"
if [[ -n "$proc_line" ]]; then
  kv process yes
else
  kv process no
fi

if [[ "$WAIT" -gt 0 ]]; then
  sleep "$WAIT"
fi

nrestarts_after="$nrestarts"
if [[ "$have_systemctl" -eq 1 ]]; then
  nrestarts_after="$(sys show "$UNIT" -p NRestarts --value 2>/dev/null || echo "")"
  active="$(sys is-active "$UNIT" 2>/dev/null || echo inactive)"
fi
kv nrestarts_after "${nrestarts_after:-}"
kv active_after "$active"

verdict=ok
if [[ "$have_systemctl" -eq 0 ]]; then
  verdict=no-systemd
elif [[ "$active" != active ]]; then
  verdict=inactive
elif [[ "$enabled" != enabled ]]; then
  verdict=not-enabled
elif [[ "$auth_error" == yes ]]; then
  verdict=auth-error
elif [[ -n "${nrestarts_after:-}" && "${nrestarts_after}" -gt 2 ]]; then
  verdict=crash-loop
elif [[ -z "$proc_line" ]]; then
  verdict=no-process
fi
kv verdict "$verdict"
