#!/usr/bin/env bash
# run-hunt.sh — wake the named-project orchestrator in a headless grok session.
#
# Env:
#   BUG_HUNTER_WORKTREE   target repo          (default: cwd)
#   BUG_HUNTER_MAX_TURNS  grok turn cap        (default: 120)
#   BUG_HUNTER_TIME_BUDGET  seconds            (default: 3600)
#   BUG_HUNTER_MIN_BUGS   quota                (default: 5)
#   BUG_HUNTER_MAX_ATTEMPTS                    (default: 4)
#   BUG_HUNTER_FOCUS      focus text
#   BUG_HUNTER_DRY_RUN=1  assemble prompt only
#   BUG_HUNTER_AUTO_PUBLISH  default 1; set 0 to prepare-only
#   BUG_HUNTER_SYNC_LESSONS  default 1
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREE="${BUG_HUNTER_WORKTREE:-$(pwd)}"
MAX_TURNS="${BUG_HUNTER_MAX_TURNS:-120}"
TIME_BUDGET="${BUG_HUNTER_TIME_BUDGET:-3600}"
MIN_BUGS="${BUG_HUNTER_MIN_BUGS:-5}"
MAX_ATTEMPTS="${BUG_HUNTER_MAX_ATTEMPTS:-4}"
export BUG_HUNTER_AUTO_PUBLISH="${BUG_HUNTER_AUTO_PUBLISH:-1}"

ID="$WORKTREE/.bug-hunter/identity.md"
KNOWLEDGE="$WORKTREE/.bug-hunter/knowledge.md"
PROFILE="$WORKTREE/.bug-hunter/hunt-profile.md"
BRIEF="$WORKTREE/.bug-hunter/hunt-brief.md"

if [[ ! -f "$ID" ]]; then
  echo "✗ no .bug-hunter/identity.md in $WORKTREE — run /bug-hunter learn" >&2
  exit 1
fi
if [[ ! -f "$KNOWLEDGE" ]]; then
  echo "✗ no .bug-hunter/knowledge.md — run /bug-hunter learn" >&2
  exit 1
fi

NAME="$(sed -n 's/^name:[[:space:]]*//p' "$ID" | head -1)"
SLUG="$(sed -n 's/^slug:[[:space:]]*//p' "$ID" | head -1)"
BASE="${HOME}/.${SLUG}-agents"
FINDINGS=".${SLUG}-new-findings.md"
ORCH_FILE="${SLUG}-orchestrator-agent.md"
mkdir -p "$BASE/logs" "$BASE/status"

LOCK="$BASE/run.lock"
LOGDIR="$BASE/logs"
STATUSDIR="$BASE/status"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/run-$STAMP.log"
STATUS="$STATUSDIR/last-run.json"
START_EPOCH="$(date +%s)"
START_TS="$(date +%Y-%m-%dT%H:%M:%S)"
TOTAL_FOUND=0
attempt=0

ts() { date +%Y-%m-%dT%H:%M:%S; }
elapsed_total() { echo $(( $(date +%s) - START_EPOCH )); }

write_status() {
  printf '{"start":"%s","end":"%s","result":"%s","exit":%s,"found":%s,"quota":%s,"attempts":%s,"log":"%s","worktree":"%s","slug":"%s"}\n' \
    "$START_TS" "$(ts)" "$1" "$2" "${TOTAL_FOUND:-0}" "$MIN_BUGS" "${attempt:-0}" "$LOG" "$WORKTREE" "$SLUG" > "$STATUS"
}

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(ts) another run holds $LOCK — exiting" | tee -a "$LOG"
  exit 0
fi
printf '%s\n' "$$" > "$LOCK/pid"
PROMPT=""
trap 'rm -f "$PROMPT"; rm -f "$LOCK/pid"; rmdir "$LOCK" 2>/dev/null || true' EXIT

# Optional tokens from a sibling env file (same place the old runner used).
if [[ -z "${YOU_TRACK_TOKEN:-}" && -f "$HOME/Downloads/phx/.env_updateServers" ]]; then
  YOU_TRACK_TOKEN="$(sed -n 's/^YOU_TRACK_TOKEN="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$HOME/Downloads/phx/.env_updateServers" | head -1)"
  export YOU_TRACK_TOKEN
fi
if [[ -z "${GITEA_TOKEN:-}" && -f "$HOME/Downloads/phx/.env_updateServers" ]]; then
  GITEA_TOKEN="$(sed -n 's/^GITEA_TOKEN="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$HOME/Downloads/phx/.env_updateServers" | head -1)"
  export GITEA_TOKEN
fi

if [[ ! -d "$WORKTREE/.git" && ! -f "$WORKTREE/.git" ]]; then
  echo "✗ $WORKTREE is not a git worktree" >&2
  write_status "bad-worktree" 1
  exit 1
fi

HUNT_BRANCH="$(grep -E 'Hunt branch:' "$KNOWLEDGE" | sed -n 's/.*`\([^`]*\)`.*/\1/p' | head -1 || true)"
branch="$(git -C "$WORKTREE" branch --show-current 2>/dev/null || true)"
if [[ -n "$HUNT_BRANCH" && "$branch" != "$HUNT_BRANCH" ]]; then
  echo "✗ worktree is on '$branch', hunts run only on $HUNT_BRANCH" >&2
  write_status "wrong-branch" 1
  exit 1
fi

if [[ "${BUG_HUNTER_SYNC_LESSONS:-1}" = "1" && -x "$SKILL_DIR/scripts/sync-lessons.sh" ]]; then
  bash "$SKILL_DIR/scripts/sync-lessons.sh" --dir "$WORKTREE" >> "$LOG" 2>&1 || \
    echo "$(ts) lessons refresh skipped — using existing lessons.md" | tee -a "$LOG"
fi

bash "$SKILL_DIR/scripts/seed-worktree.sh" --dir "$WORKTREE" >/dev/null 2>&1 || true

PROMPT="$(mktemp "$BASE/prompt.XXXXXX.md")"
if [[ -f "$WORKTREE/$ORCH_FILE" ]]; then
  sed -n '/^```text$/,/^```$/p' "$WORKTREE/$ORCH_FILE" | sed '1d;$d' > "$PROMPT"
else
  sed -n '/^```text$/,/^```$/p' "$SKILL_DIR/references/orchestrator.md" | sed '1d;$d' \
    | sed -e "s/{{NAME}}/${NAME}/g" -e "s/{{SLUG}}/${SLUG}/g" -e "s/{{FINDINGS}}/${FINDINGS}/g" \
          -e "s/{{HUNTER_FILE}}/${SLUG}-bughunter-agent.md/g" > "$PROMPT"
fi

{
  echo
  echo "=== IDENTITY ==="
  echo "You are the $NAME hunter (slug $SLUG). Agent home: $BASE"
  echo
  echo "=== KNOWLEDGE ==="
  cat "$KNOWLEDGE"
  echo
  echo "=== HUNT PROFILE ==="
  if [[ -f "$PROFILE" ]]; then cat "$PROFILE"; else echo "(no profile)"; fi
  echo
  echo "=== HUNT FOCUS ==="
  if [[ -n "${BUG_HUNTER_FOCUS:-}" ]]; then
    printf '%s\n' "$BUG_HUNTER_FOCUS"
  elif [[ -f "$BRIEF" ]]; then
    brief_content="$(sed '/<!--/,/-->/d' "$BRIEF" | grep -vE '^\s*(#|$)' || true)"
    if [[ -n "$brief_content" ]]; then cat "$BRIEF"; else
      echo "No focus set — hunt the grounds in the profile."
    fi
  else
    echo "No focus set — hunt the grounds in the profile."
  fi
  echo
  echo "=== HUNT QUOTA ==="
  echo "At least $MIN_BUGS real bugs, each confirmed through the repro gate and either fixed+published or ticketed."
  echo
  echo "=== HUNTED LEDGER (already caught — never re-hunt; write new findings to ./$FINDINGS) ==="
  cat "$BASE/hunted-ledger.md" 2>/dev/null || echo "(no ledger yet)"
  echo
  echo "=== LESSONS LEARNED (if a candidate matches, DO NOT file it) ==="
  if [[ -s "$BASE/lessons.md" ]]; then grep -vE '^#( |$)|^Hash:' "$BASE/lessons.md"; else echo "(no lessons yet)"; fi
} >> "$PROMPT"

if [[ "${BUG_HUNTER_DRY_RUN:-0}" = "1" ]]; then
  echo "$(ts) DRY RUN — prompt assembled ($NAME / $SLUG)"
  sed -n '/=== IDENTITY/,$p' "$PROMPT"
  write_status "dry-run" 0
  exit 0
fi

run_grok() {
  "$HOME/.grok/bin/grok" "$@" \
    --cwd "$WORKTREE" \
    --always-approve \
    --max-turns "$MAX_TURNS" \
    --output-format plain \
    >> "$LOG" 2>&1 &
  GROK_PID=$!
  while kill -0 "$GROK_PID" 2>/dev/null; do
    sleep 15
    if [[ "$(elapsed_total)" -ge "$TIME_BUDGET" ]]; then
      kill "$GROK_PID" 2>/dev/null; sleep 5; kill -9 "$GROK_PID" 2>/dev/null
      return 124
    fi
  done
  wait "$GROK_PID"
}

harvest() {
  if [[ -f "$WORKTREE/$FINDINGS" ]]; then
    local n
    n="$(grep -cE '\|[[:space:]]*(fixed|ticketed)' "$WORKTREE/$FINDINGS" 2>/dev/null || true)"
    n="${n:-0}"
    cat "$WORKTREE/$FINDINGS" >> "$BASE/hunted-ledger.md"
    rm -f "$WORKTREE/$FINDINGS"
    TOTAL_FOUND=$((TOTAL_FOUND + n))
    echo "$(ts) merged findings: +$n confirmed (total $TOTAL_FOUND/$MIN_BUGS)" | tee -a "$LOG"
  fi
}

echo "$(ts) starting $NAME hunt in $WORKTREE (quota ${MIN_BUGS})" | tee -a "$LOG"
LAST_COMPLETE=0
EXIT_CODE=0
while :; do
  attempt=$((attempt + 1))
  log_offset="$(wc -c < "$LOG" | tr -d ' ')"
  if [[ "$attempt" -eq 1 ]]; then
    run_grok --prompt-file "$PROMPT"; EXIT_CODE=$?
  else
    reason="Your previous session ended without a final report — pick up where it stopped."
    [[ "$LAST_COMPLETE" -eq 1 ]] && reason="You declared HUNT COMPLETE with only $TOTAL_FOUND of $MIN_BUGS required bugs."
    echo "$(ts) attempt $attempt — resuming ($TOTAL_FOUND/$MIN_BUGS)" | tee -a "$LOG"
    run_grok --continue -p "RESUME THE HUNT. $reason Confirmed findings this run: $TOTAL_FOUND of $MIN_BUGS required. Keep hunting NEW bugs — never re-hunt anything in the ledger. Each new bug is appended to ./$FINDINGS. When you reach $MIN_BUGS (or have exhausted the grounds), give the full final report and end with HUNT COMPLETE."
    EXIT_CODE=$?
  fi
  harvest
  LAST_COMPLETE=0
  tail -c "+$((log_offset + 1))" "$LOG" | grep -q "HUNT COMPLETE" && LAST_COMPLETE=1
  [[ "$EXIT_CODE" -ne 0 ]] && break
  [[ "$LAST_COMPLETE" -eq 1 && "$TOTAL_FOUND" -ge "$MIN_BUGS" ]] && break
  [[ "$attempt" -ge "$MAX_ATTEMPTS" ]] && break
  [[ "$(( TIME_BUDGET - $(elapsed_total) ))" -lt 300 ]] && break
done

if [[ "$EXIT_CODE" -eq 124 ]]; then
  write_status "killed-timeout" 124
  exit 124
elif [[ "$EXIT_CODE" -ne 0 ]]; then
  write_status "failed" "$EXIT_CODE"
  exit "$EXIT_CODE"
elif [[ "$LAST_COMPLETE" -ne 1 ]]; then
  write_status "aborted-no-report" 0
elif [[ "$TOTAL_FOUND" -lt "$MIN_BUGS" ]]; then
  write_status "ok-quota-short" 0
else
  echo "$(ts) hunt complete: $TOTAL_FOUND/$MIN_BUGS" | tee -a "$LOG"
  write_status "ok" 0
fi
