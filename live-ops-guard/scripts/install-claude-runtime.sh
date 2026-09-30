#!/usr/bin/env bash
# Merge live-ops-guard into ~/.claude/settings.json. Reuses ~/.grok/hooks/live-ops-guard/guard.py.
# Does not remove other Claude Code hooks.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"

# Guard script, ledger and host files live next to Grok's hook.
bash "$SKILL_DIR/scripts/install-grok-runtime.sh"

mkdir -p "$CLAUDE_HOME/hooks"
cp "$SKILL_DIR/hooks/claude-entry.py" "$CLAUDE_HOME/hooks/live-ops-guard.py"

python3 - "$CLAUDE_HOME/settings.json" "$SKILL_DIR/hooks/claude-code.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
fragment = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["hooks"]
marker = "live-ops-guard.py"

if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {}
if not isinstance(data, dict):
    raise SystemExit(f"unexpected settings.json shape: {path}")
hooks = data.setdefault("hooks", {})

def has_marker(group: dict) -> bool:
    return any(marker in str(h.get("command", "")) for h in group.get("hooks", []) if isinstance(h, dict))

for event, groups in fragment.items():
    items = hooks.setdefault(event, [])
    if not isinstance(items, list):
        raise SystemExit(f"hooks.{event} is not a list")
    if any(isinstance(g, dict) and has_marker(g) for g in items):
        continue
    items.extend(groups)

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"merged Claude Code hooks -> {path}")
PY

echo "installed Claude Code entry -> $CLAUDE_HOME/hooks/live-ops-guard.py"
echo "start a new Claude Code session so the hooks load"
