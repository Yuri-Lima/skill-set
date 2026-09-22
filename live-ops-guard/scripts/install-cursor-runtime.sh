#!/usr/bin/env bash
# Merge live-ops-guard into ~/.cursor/hooks.json. Reuses ~/.grok/hooks/live-ops-guard/guard.py.
# Does not remove other Cursor hooks.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CURSOR_HOME="${CURSOR_HOME:-$HOME/.cursor}"

# Guard script lives next to Grok's hook.
bash "$SKILL_DIR/scripts/install-grok-runtime.sh"

mkdir -p "$CURSOR_HOME/hooks"
cp "$SKILL_DIR/hooks/cursor-entry.py" "$CURSOR_HOME/hooks/live-ops-guard.py"

python3 - "$CURSOR_HOME/hooks.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
marker = "live-ops-guard.py"
pre = {
    "command": "python3 ./hooks/live-ops-guard.py --event pre --runtime cursor",
    "timeout": 10,
}
post = {
    "command": "python3 ./hooks/live-ops-guard.py --event post --runtime cursor",
    "timeout": 10,
}

if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {"version": 1, "hooks": {}}

if not isinstance(data, dict):
    raise SystemExit(f"unexpected hooks.json shape: {path}")
hooks = data.setdefault("hooks", {})
data.setdefault("version", 1)

def ensure(event: str, entry: dict) -> None:
    items = hooks.setdefault(event, [])
    if not isinstance(items, list):
        raise SystemExit(f"hooks.{event} is not a list")
    if any(marker in str(item.get("command", "")) for item in items if isinstance(item, dict)):
        return
    items.append(entry)

ensure("beforeShellExecution", pre)
ensure("beforeMCPExecution", pre)
ensure("postToolUse", post)
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"merged Cursor hooks -> {path}")
PY

echo "installed Cursor entry -> $CURSOR_HOME/hooks/live-ops-guard.py"
echo "reload Cursor Hooks settings or start a new session"
