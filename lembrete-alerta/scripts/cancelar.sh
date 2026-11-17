#!/bin/bash
# cancelar.sh — remove um lembrete da skill lembrete-alerta
# Uso: cancelar.sh <rotulo>
set -euo pipefail
[ $# -eq 1 ] || { echo "Uso: cancelar.sh <rotulo>" >&2; exit 1; }
SLUG=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//')

FOUND=0
for p in "$HOME/Library/LaunchAgents/com.lembrete.$SLUG-"*.plist; do
  [ -e "$p" ] || continue
  FOUND=1
  lbl=$(basename "$p" .plist)
  launchctl bootout "gui/$(id -u)/$lbl" 2>/dev/null || true
  rm -f "$p"
  echo "Removido: $lbl"
done
rm -f "$HOME/Library/Scripts/lembrete-$SLUG.sh" && echo "Removido: ~/Library/Scripts/lembrete-$SLUG.sh"
[ "$FOUND" -eq 1 ] || echo "Nenhum agendamento encontrado para o rótulo: $SLUG"
