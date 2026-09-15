#!/usr/bin/env bash
# Copy the Grok hook + agent next to Grok's runtime paths.
# Does not overwrite an existing live-hosts.txt.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GROK_HOME="${GROK_HOME:-$HOME/.grok}"

mkdir -p "$GROK_HOME/hooks/live-ops-guard" "$GROK_HOME/agents"

cp "$SKILL_DIR/hooks/guard.py" "$GROK_HOME/hooks/live-ops-guard/guard.py"
chmod +x "$GROK_HOME/hooks/live-ops-guard/guard.py"
cp "$SKILL_DIR/hooks/live-ops-guard.json" "$GROK_HOME/hooks/live-ops-guard.json"
cp "$SKILL_DIR/agents/live-ops-guard.md" "$GROK_HOME/agents/live-ops-guard.md"

hosts="$GROK_HOME/hooks/live-ops-guard/live-hosts.txt"
if [[ ! -f "$hosts" ]]; then
  cp "$SKILL_DIR/hooks/live-hosts.example.txt" "$hosts"
  echo "created empty $hosts — paste live Host aliases/IPs there"
else
  echo "kept existing $hosts"
fi

echo "installed hook -> $GROK_HOME/hooks/live-ops-guard.json"
echo "installed agent -> $GROK_HOME/agents/live-ops-guard.md"
echo "reload Grok hooks (/hooks) or start a new session"
