#!/usr/bin/env bash
# Smoke-test hook decisions. No network.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
G="$DIR/hooks/guard.py"
fail=0

run() {
  local title="$1" expect="$2"
  shift 2
  local out
  out="$(python3 "$G" --event pre)"
  if ! printf '%s' "$out" | grep -q "$expect"; then
    echo "FAIL $title"
    echo "  expected to match: $expect"
    echo "  got: $out"
    fail=1
  else
    echo "ok   $title"
  fi
}

run "get-allow" '"decision": "allow"' <<'EOF'
{"toolName":"teamcity__teamcity_rest_get","toolInput":{"path":"/app/rest/server"}}
EOF

run "delete-ask" '"decision": "ask"' <<'EOF'
{"toolName":"teamcity__teamcity_rest_delete","toolInput":{"path":"/app/rest/buildTypes/id:Example_Build"}}
EOF

run "secret-ask" 'github-pat' <"$DIR/evals/fixtures/leaked-token-event.json"

run "placeholder-allow" '"decision": "allow"' <<'EOF'
{"toolName":"run_terminal_command","toolInput":{"command":"echo Bearer ${TC_AUTH_TOKEN}"}}
EOF

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "all guard smokes passed"
