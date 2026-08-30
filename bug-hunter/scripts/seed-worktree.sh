#!/usr/bin/env bash
# Render generic prompts into ~/.<slug>-agents/ and copy them into the worktree.
# Usage: seed-worktree.sh [--dir REPO] [--force]
set -euo pipefail

DIR="."
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --force|-f) FORCE=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$(cd "$DIR" && pwd)"
ID="$DIR/.bug-hunter/identity.md"
if [[ ! -f "$ID" ]]; then
  echo "✗ no .bug-hunter/identity.md in $DIR — run /bug-hunter learn first" >&2
  exit 1
fi

NAME="$(sed -n 's/^name:[[:space:]]*//p' "$ID" | head -1)"
SLUG="$(sed -n 's/^slug:[[:space:]]*//p' "$ID" | head -1)"
if [[ -z "$NAME" || -z "$SLUG" ]]; then
  echo "✗ identity.md missing name or slug" >&2
  exit 1
fi

HOME_AGENTS="${HOME}/.${SLUG}-agents"
mkdir -p "$HOME_AGENTS"

FINDINGS=".${SLUG}-new-findings.md"
HUNTER_FILE="${SLUG}-bughunter-agent.md"
ORCH_FILE="${SLUG}-orchestrator-agent.md"
STACK_FILE="${SLUG}-stack.md"
TAG="by grok_$(printf '%s' "$SLUG" | tr '-' '_')_hunter"

render() {
  local src="$1" dest="$2"
  if [[ -e "$dest" && "$FORCE" -eq 0 ]]; then
    echo "  kept    $dest"
    return
  fi
  sed -e "s/{{NAME}}/${NAME}/g" \
      -e "s/{{SLUG}}/${SLUG}/g" \
      -e "s/{{FINDINGS}}/${FINDINGS}/g" \
      -e "s/{{HUNTER_FILE}}/${HUNTER_FILE}/g" \
      -e "s/{{TAG}}/${TAG}/g" \
      "$src" > "$dest"
  echo "  wrote   $dest"
}

render "$SKILL_DIR/references/orchestrator.md" "$HOME_AGENTS/$ORCH_FILE"
render "$SKILL_DIR/references/hunter.md" "$HOME_AGENTS/$HUNTER_FILE"

if [[ -f "$DIR/.bug-hunter/knowledge.md" ]]; then
  cp "$DIR/.bug-hunter/knowledge.md" "$HOME_AGENTS/$STACK_FILE"
fi

copy_into() {
  local src="$1" dest="$2"
  if [[ -e "$dest" && "$FORCE" -eq 0 ]]; then
    echo "  kept    $dest"
    return
  fi
  cp "$src" "$dest"
  echo "  seeded  $dest"
}

copy_into "$HOME_AGENTS/$ORCH_FILE" "$DIR/$ORCH_FILE"
copy_into "$HOME_AGENTS/$HUNTER_FILE" "$DIR/$HUNTER_FILE"
if [[ -f "$HOME_AGENTS/$STACK_FILE" ]]; then
  copy_into "$HOME_AGENTS/$STACK_FILE" "$DIR/$STACK_FILE"
fi

echo "seeded $NAME ($SLUG) → $DIR"
echo "home   $HOME_AGENTS"
