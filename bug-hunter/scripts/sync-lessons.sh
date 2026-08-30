#!/usr/bin/env bash
# Refresh ~/.<slug>-agents/lessons.md from the ticket host in knowledge.
# YouTrack is implemented. Other hosts are a no-op with a message.
set -uo pipefail

DIR="."
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --show)
      DIR="$(cd "$DIR" && pwd)"
      ID="$DIR/.bug-hunter/identity.md"
      [[ -f "$ID" ]] || { echo "no identity"; exit 1; }
      SLUG="$(sed -n 's/^slug:[[:space:]]*//p' "$ID" | head -1)"
      LESSONS="$HOME/.${SLUG}-agents/lessons.md"
      [[ -f "$LESSONS" ]] && cat "$LESSONS" || echo "no lessons.md yet"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

DIR="$(cd "$DIR" && pwd)"
ID="$DIR/.bug-hunter/identity.md"
KNOWLEDGE="$DIR/.bug-hunter/knowledge.md"
[[ -f "$ID" && -f "$KNOWLEDGE" ]] || { echo "✗ need identity + knowledge" >&2; exit 1; }

SLUG="$(sed -n 's/^slug:[[:space:]]*//p' "$ID" | head -1)"
HOST="$(grep -i 'Ticket host:' "$KNOWLEDGE" | head -1 || true)"

if ! printf '%s' "$HOST" | grep -qi youtrack; then
  echo "lessons sync: ticket host is not youtrack — left lessons.md unchanged"
  exit 0
fi

# Delegate to the existing YouTrack sync if this slug's home still has it
# (Phoenix: ~/.phx-agents/sync-lessons.sh). Otherwise skip cleanly.
if [[ -x "$HOME/.${SLUG}-agents/sync-lessons.sh" ]]; then
  bash "$HOME/.${SLUG}-agents/sync-lessons.sh"
  exit $?
fi

echo "lessons sync: no YouTrack helper in ~/.${SLUG}-agents — left lessons.md unchanged"
exit 0
