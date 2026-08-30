#!/usr/bin/env bash
# Fill .bug-hunter/ from an existing ~/.<slug>-agents tree (e.g. today's ~/.phx-agents).
# Does not move or delete the home. Ledger and lessons stay there.
#
#   import-existing.sh --dir REPO --name Phoenix --slug phx
#   import-existing.sh --dir REPO --name Phoenix --slug phx --home ~/.phx-agents
set -euo pipefail

DIR="."
NAME=""
SLUG=""
HOME_AGENTS=""
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --slug) SLUG="$2"; shift 2 ;;
    --home) HOME_AGENTS="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

DIR="$(cd "$DIR" && pwd)"
[[ -n "$NAME" && -n "$SLUG" ]] || { echo "✗ --name and --slug are required" >&2; exit 2; }

node "$SKILL_DIR/scripts/project-id.mjs" --validate "$SLUG" >/dev/null

HOME_AGENTS="${HOME_AGENTS:-$HOME/.${SLUG}-agents}"
if [[ ! -d "$HOME_AGENTS" ]]; then
  echo "✗ no agent home at $HOME_AGENTS" >&2
  exit 1
fi

STACK=""
for cand in "$HOME_AGENTS/${SLUG}-stack.md" "$HOME_AGENTS/phx-stack.md" "$HOME_AGENTS/stack.md"; do
  if [[ -f "$cand" ]]; then STACK="$cand"; break; fi
done
if [[ -z "$STACK" ]]; then
  echo "✗ no stack file in $HOME_AGENTS" >&2
  exit 1
fi

node "$SKILL_DIR/scripts/write-knowledge.mjs" identity --dir "$DIR" --name "$NAME" --slug "$SLUG" --force

mkdir -p "$DIR/.bug-hunter"
cp "$STACK" "$DIR/.bug-hunter/knowledge.md"
# Keep a slug-named copy in the home so the generic runner can find it.
if [[ "$STACK" != "$HOME_AGENTS/${SLUG}-stack.md" ]]; then
  cp "$STACK" "$HOME_AGENTS/${SLUG}-stack.md"
fi

if [[ -f "$HOME_AGENTS/hunt-brief.md" && ! -f "$DIR/.bug-hunter/hunt-brief.md" ]]; then
  cp "$HOME_AGENTS/hunt-brief.md" "$DIR/.bug-hunter/hunt-brief.md"
fi
if [[ ! -f "$DIR/.bug-hunter/hunt-brief.md" ]]; then
  printf '# Hunt focus — %s\n\n## Focus\n\n' "$NAME" > "$DIR/.bug-hunter/hunt-brief.md"
fi

# Build a hunt profile from grounds listed in an existing orchestrator prompt, if any.
ORCH=""
for cand in "$HOME_AGENTS/${SLUG}-orchestrator-agent.md" "$HOME_AGENTS/phx-orchestrator-agent.md"; do
  [[ -f "$cand" ]] && ORCH="$cand" && break
done

PROFILE="$DIR/.bug-hunter/hunt-profile.md"
{
  printf '# %s hunter — hunt profile\n\nImported from %s on %s.\n\n## Grounds in season\n\n' \
    "$NAME" "$HOME_AGENTS" "$(date +%Y-%m-%d)"
  if [[ -n "$ORCH" ]] && grep -q 'Productive hunting grounds' "$ORCH"; then
    # Copy the bullet list that follows that heading, until the next blank-then-non-bullet.
    awk '
      /Productive hunting grounds/ {grab=1; next}
      grab && /^[[:space:]]*-/ {print; seen=1; next}
      grab && seen && /^[[:space:]]+[^[:space:]-]/ {print; next}
      grab && NF==0 {next}
      grab && seen {exit}
    ' "$ORCH"
  else
    echo "_(imported stack has no grounds list — run /bug-hunter learn to confirm hot spots)_"
  fi
  printf '\n## Repro gate\n\nNo code change until the bug shows itself.\n'
} > "$PROFILE"

# Do not --force: an existing home (e.g. ~/.phx-agents) already has the live prompts.
bash "$SKILL_DIR/scripts/seed-worktree.sh" --dir "$DIR"

echo "imported $NAME ($SLUG)"
echo "  knowledge  $DIR/.bug-hunter/knowledge.md"
echo "  profile    $PROFILE"
echo "  home       $HOME_AGENTS  (ledger/lessons left in place)"
