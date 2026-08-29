#!/usr/bin/env bash
# Copy skill-set skills into Claude, Cursor, and Grok.
#
#   ./install.sh --global
#   ./install.sh --project
#   ./install.sh --skill ticket-demo-video --global
#   ./install.sh --update --global
#   curl -fsSL https://raw.githubusercontent.com/Yuri-Lima/skill-set/main/install.sh | bash -s -- --global
set -euo pipefail

REPO_URL="${SKILL_SET_REPO:-https://github.com/Yuri-Lima/skill-set.git}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/skill-set"

SCOPE=""
UPDATE=0
DRY=0
LIST=0
declare -a ONLY=()

usage() {
  cat <<'EOF'
Usage: install.sh [--global | --project] [--skill NAME]... [--update] [--list] [--dry-run]

  --global     User install (default): ~/.grok/skills ~/.claude/skills ~/.cursor/skills
  --project    This repo: .grok/skills .claude/skills .cursor/skills .agents/skills
  --skill NAME Only this skill (repeatable)
  --update     git pull the source, then recopy
  --list       Print skills in the source and exit
  --dry-run    Print destinations, do not copy

Source is this clone when install.sh sits next to SKILL.md folders.
Otherwise a shallow clone of github.com/Yuri-Lima/skill-set is used
(override URL with SKILL_SET_REPO).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) SCOPE="global"; shift ;;
    --project) SCOPE="project"; shift ;;
    --skill)
      [[ $# -ge 2 ]] || { echo "need a name after --skill" >&2; exit 2; }
      ONLY+=("$2")
      shift 2
      ;;
    --update) UPDATE=1; shift ;;
    --list) LIST=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

is_source_root() {
  local dir="$1"
  [[ -n "$dir" && -d "$dir" ]] || return 1
  local f
  for f in "$dir"/*/SKILL.md; do
    [[ -f "$f" ]] && return 0
  done
  return 1
}

self="${BASH_SOURCE[0]:-}"
SOURCE=""
if [[ -n "$self" && -f "$self" ]]; then
  SOURCE="$(cd "$(dirname "$self")" && pwd)"
fi
if ! is_source_root "${SOURCE:-}"; then
  SOURCE="$CACHE_DIR"
fi

ensure_source() {
  if is_source_root "$SOURCE"; then
    if [[ "$UPDATE" -eq 1 && -d "$SOURCE/.git" ]]; then
      git -C "$SOURCE" pull --ff-only
    fi
    return
  fi
  if [[ -d "$SOURCE/.git" ]]; then
    git -C "$SOURCE" pull --ff-only
  else
    mkdir -p "$(dirname "$SOURCE")"
    git clone --depth 1 "$REPO_URL" "$SOURCE"
  fi
  is_source_root "$SOURCE" || {
    echo "no SKILL.md folders in $SOURCE" >&2
    exit 1
  }
}

skill_names() {
  local f name
  for f in "$SOURCE"/*/SKILL.md; do
    [[ -f "$f" ]] || continue
    name="$(basename "$(dirname "$f")")"
    printf '%s\n' "$name"
  done | LC_ALL=C sort
}

ensure_source

if [[ "$LIST" -eq 1 ]]; then
  skill_names
  exit 0
fi

SCOPE="${SCOPE:-global}"

declare -a NAMES=()
skill_deps() {
  case "$1" in
    ticket-demo-video) printf '%s\n' playwright-agent ;;
    claim-fix-ticket) printf '%s\n' playwright-agent ticket-demo-video ;;
    explain-implementation-video) printf '%s\n' ticket-demo-video ;;
  esac
}

list_has() {
  local needle="$1" item
  shift || true
  [[ $# -eq 0 ]] && return 1
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

if [[ ${#ONLY[@]} -eq 0 ]]; then
  while IFS= read -r name; do
    NAMES+=("$name")
  done < <(skill_names)
else
  declare -a WANT=()
  add_with_deps() {
    local name="$1" dep
    if [[ ! -f "$SOURCE/$name/SKILL.md" ]]; then
      echo "unknown skill: $name" >&2
      echo "available:" >&2
      skill_names >&2
      exit 2
    fi
    if [[ ${#WANT[@]} -gt 0 ]] && list_has "$name" "${WANT[@]}"; then
      return 0
    fi
    WANT+=("$name")
    while IFS= read -r dep; do
      [[ -n "$dep" ]] || continue
      add_with_deps "$dep"
    done < <(skill_deps "$name")
  }
  for name in "${ONLY[@]}"; do
    add_with_deps "$name"
  done
  while IFS= read -r name; do
    if [[ ${#WANT[@]} -gt 0 ]] && list_has "$name" "${WANT[@]}"; then
      NAMES+=("$name")
    fi
  done < <(skill_names)
fi

project_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

declare -a DIRS=()
if [[ "$SCOPE" == "global" ]]; then
  DIRS=("$HOME/.grok/skills" "$HOME/.claude/skills" "$HOME/.cursor/skills")
else
  root="$(project_root)"
  DIRS=(
    "$root/.grok/skills"
    "$root/.claude/skills"
    "$root/.cursor/skills"
    "$root/.agents/skills"
  )
fi

copy_skill() {
  local src="$1" dest="$2"
  if command -v rsync >/dev/null 2>&1; then
    mkdir -p "$dest"
    rsync -a --delete --exclude '.git' --exclude 'node_modules' "$src/" "$dest/"
  else
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    cp -R "$src" "$dest"
  fi
}

echo "source: $SOURCE"
echo "scope:  $SCOPE"
for dest in "${DIRS[@]}"; do
  echo "dest:   $dest"
done

for name in "${NAMES[@]}"; do
  for dest in "${DIRS[@]}"; do
    target="$dest/$name"
    if [[ "$DRY" -eq 1 ]]; then
      echo "would copy $name -> $target"
      continue
    fi
    mkdir -p "$dest"
    copy_skill "$SOURCE/$name" "$target"
    echo "copied $name -> $target"
  done
done

if [[ "$DRY" -eq 0 ]]; then
  echo
  echo "Start a new Claude / Cursor / Grok session (or reload skills) so they appear."
fi
