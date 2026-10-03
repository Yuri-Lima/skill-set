#!/usr/bin/env bash
# Smoke-test hook decisions. No network. Uses a throwaway LIVE_OPS_GUARD_HOME so
# the real ledger / marker are never touched.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
G="$DIR/hooks/guard.py"
export LIVE_OPS_GUARD_HOME LIVE_OPS_GUARD_MODE LIVE_OPS_GUARD_INTERRUPT
LIVE_OPS_GUARD_MODE=gate
LIVE_OPS_GUARD_INTERRUPT=immediate
LIVE_OPS_GUARD_HOME="$(mktemp -d)"
trap 'rm -rf "$LIVE_OPS_GUARD_HOME"' EXIT
fail=0

run() {
  local title="$1" expect="$2" event="${3:-pre}"
  local out
  out="$(python3 "$G" --event "$event")"
  if ! printf '%s' "$out" | grep -q -- "$expect"; then
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
{"toolName":"run_terminal_command","toolInput":{"command":"printf '%s' \"Bearer ${TC_AUTH_TOKEN}\""}}
EOF

run "secret-read-ask" 'secret-read(env-file)' <<'EOF'
{"toolName":"run_terminal_command","toolInput":{"command":"cat .env"}}
EOF

run "claude-shape-ask" '"permissionDecision": "ask"' <<'EOF'
{"session_id":"smoke-1","transcript_path":"/tmp/smoke.jsonl","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ssh box uptime"}}
EOF

run "unreadable-payload-is-loud" 'could NOT evaluate' <<'EOF'
{not json
EOF

run "secret-read-post-exposure" 'NEEDS_TRACE_REVIEW' post <<'EOF'
{"session_id":"smoke-1","transcript_path":"/tmp/smoke.jsonl","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"cat .env"},"tool_response":"X=1"}
EOF

LIVE_OPS_GUARD_MODE=notify
run "notify-ssh-runs" '"additionalContext": "live-ops-guard (notify mode)' <<'EOF'
{"session_id":"smoke-1","transcript_path":"/tmp/smoke.jsonl","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ssh box uptime"}}
EOF

run "notify-exposure-blocks-with-options" '"decision": "block"' post <<'EOF'
{"session_id":"smoke-1","transcript_path":"/tmp/smoke.jsonl","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"bash x.sh"},"tool_response":"ghp_abcdefghijklmnopqrstuvwxyz0123456789"}
EOF
LIVE_OPS_GUARD_MODE=gate

run "stop-summary" 'Trace review required: YES' stop <<'EOF'
{"session_id":"smoke-1","transcript_path":"/tmp/smoke.jsonl","hook_event_name":"Stop"}
EOF

run "start-nags" 'need a trace review' start <<'EOF'
{"session_id":"smoke-2","transcript_path":"/tmp/smoke2.jsonl","hook_event_name":"SessionStart"}
EOF

if [[ ! -f "$LIVE_OPS_GUARD_HOME/ledger.jsonl" ]]; then
  echo "FAIL ledger not written"; fail=1
else
  echo "ok   ledger written"
fi
if grep -q "ghp_abcdefghijklmnopqrstuvwxyz" "$LIVE_OPS_GUARD_HOME/ledger.jsonl"; then
  echo "FAIL ledger contains the fixture token"; fail=1
else
  echo "ok   ledger has no payload"
fi

python3 "$G" review smoke-1 --ack | grep -q "acknowledged" && echo "ok   review --ack" || { echo "FAIL review --ack"; fail=1; }

python3 "$DIR/hooks/test_guard.py"
echo "python classify tests passed"

python3 "$DIR/scripts/eval-detection.py" --quiet
echo "detection eval: all must cases pass"

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "all guard smokes passed"
