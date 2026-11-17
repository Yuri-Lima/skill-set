#!/bin/bash
# listar.sh — mostra os lembretes agendados pela skill lembrete-alerta
echo "== Agents carregados =="
launchctl list | grep com.lembrete. || echo "(nenhum)"
echo
echo "== Arquivos .plist =="
ls -1 "$HOME/Library/LaunchAgents"/com.lembrete.*.plist 2>/dev/null || echo "(nenhum)"
echo
echo "== Horários =="
for p in "$HOME/Library/LaunchAgents"/com.lembrete.*.plist; do
  [ -e "$p" ] || continue
  lbl=$(basename "$p" .plist)
  m=$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Month' "$p" 2>/dev/null)
  d=$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Day' "$p" 2>/dev/null)
  h=$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Hour' "$p" 2>/dev/null)
  mi=$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval:Minute' "$p" 2>/dev/null)
  printf '%s -> dia %02d/%02d às %02d:%02d\n' "$lbl" "$d" "$m" "$h" "$mi"
done
