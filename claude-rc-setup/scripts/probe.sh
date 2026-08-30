#!/usr/bin/env bash
# Discover whether this box can run claude-rc as a systemd unit.
# Prints KEY=value lines. Exit 0 even on failed preconditions so the
# agent can show the block; `precondition=` is the gate.
set -euo pipefail

kv() { printf '%s=%s\n' "$1" "$2"; }

hostname_val="$(hostname 2>/dev/null || echo unknown)"
kv hostname "$hostname_val"

ip=""
if command -v ip >/dev/null 2>&1; then
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}' || true)"
fi
if [[ -z "$ip" ]]; then
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
if [[ -z "$ip" ]] && command -v ipconfig >/dev/null 2>&1; then
  ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
kv ip "${ip:-unknown}"

claude_bin="$(command -v claude 2>/dev/null || true)"
kv claude_bin "${claude_bin:-}"

claude_version=""
if [[ -n "$claude_bin" ]]; then
  claude_version="$("$claude_bin" --version 2>/dev/null | head -n 1 || true)"
fi
kv claude_version "$claude_version"

init="$(ps -p 1 -o comm= 2>/dev/null | tr -d ' ' || true)"
if [[ -n "$init" ]]; then
  init="$(basename "$init")"
fi
kv init "${init:-unknown}"

user_name="$(id -un 2>/dev/null || echo unknown)"
home_dir="${HOME:-}"
if [[ -z "$home_dir" ]]; then
  home_dir="$(getent passwd "$user_name" 2>/dev/null | awk -F: '{print $6}')"
fi
kv user "$user_name"
kv home "${home_dir:-}"

claude_dir=no
if [[ -n "$home_dir" && -d "$home_dir/.claude" ]]; then
  first="$(find "$home_dir/.claude" -maxdepth 2 -type f 2>/dev/null | head -n 1 || true)"
  if [[ -n "$first" ]]; then
    claude_dir=yes
  fi
fi
kv claude_dir "$claude_dir"

claude_json=no
if [[ -n "$home_dir" && -f "$home_dir/.claude.json" ]]; then
  claude_json=yes
fi
kv claude_json "$claude_json"

existing_unit=none
if command -v systemctl >/dev/null 2>&1; then
  units="$(systemctl list-unit-files --no-legend --no-pager 2>/dev/null | awk '{print $1}' | grep -i claude || true)"
  if [[ -n "$units" ]]; then
    existing_unit="$(printf '%s' "$units" | tr '\n' ',' | sed 's/,$//')"
  fi
fi
if [[ -f /etc/systemd/system/claude-rc.service ]]; then
  if [[ "$existing_unit" == none ]]; then
    existing_unit=claude-rc.service
  elif [[ "$existing_unit" != *claude-rc.service* ]]; then
    existing_unit="${existing_unit},claude-rc.service"
  fi
fi
kv existing_unit "$existing_unit"

stray_pids="$(ps -ax -o pid= -o args= 2>/dev/null | awk '/remote-control/ && !/awk/ { print $1 }' | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
kv stray_pids "${stray_pids:-}"

cwd="$(pwd)"
kv cwd "$cwd"
if [[ -n "$home_dir" && "$cwd" == "$home_dir" ]]; then
  kv workdir_is_home yes
else
  kv workdir_is_home no
fi

blocking=""
for var in ANTHROPIC_BASE_URL DISABLE_TELEMETRY DO_NOT_TRACK \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC DISABLE_GROWTHBOOK; do
  eval "val=\${$var-}"
  if [[ -n "${val:-}" ]]; then
    blocking="${blocking}${var},"
  fi
done
kv blocking_env "${blocking%,}"

fails=""
if [[ "$init" != systemd ]]; then
  fails="${fails}no-systemd,"
fi
if [[ -z "$claude_bin" || -z "$claude_version" ]]; then
  fails="${fails}no-claude,"
fi
if [[ "$claude_dir" != yes ]]; then
  fails="${fails}no-auth,"
fi
fails="${fails%,}"
if [[ -z "$fails" ]]; then
  kv precondition ok
  kv fail ""
else
  kv precondition fail
  kv fail "$fails"
fi
