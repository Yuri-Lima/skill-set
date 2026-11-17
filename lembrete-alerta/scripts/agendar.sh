#!/bin/bash
# agendar.sh — cria um lembrete local com alarme sonoro contínuo + diálogo via launchd (macOS)
#
# Uso:
#   agendar.sh <rotulo> "<título>" "<corpo multilinha>" "YYYY-MM-DD HH:MM" [...mais horários em ordem]
#
# Comportamento do alarme gerado:
#   - toca sem parar até o usuário clicar OK (diálogo reaparece a cada 10 min se expirar)
#   - botão "Soneca 5 min": silencia, espera 5 min e toca de novo
#   - trava de segurança: para sozinho após ~2 h sem resposta
#
# DRY_RUN=1 gera os arquivos em ./dry-run/ sem registrar nada no launchd.
set -euo pipefail

if [ $# -lt 4 ]; then
  echo "Uso: agendar.sh <rotulo> <titulo> <corpo> <datetime1> [datetime2 ...]" >&2
  exit 1
fi

LABEL_RAW="$1"; TITLE="$2"; BODY="$3"; shift 3

# rótulo seguro: minúsculas, números e hífens
SLUG=$(printf '%s' "$LABEL_RAW" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//')
[ -n "$SLUG" ] || { echo "Rótulo inválido: $LABEL_RAW" >&2; exit 1; }

if [ "${DRY_RUN:-0}" = "1" ]; then
  SCRIPTS_DIR="$PWD/dry-run/Scripts"
  AGENTS_DIR="$PWD/dry-run/LaunchAgents"
else
  SCRIPTS_DIR="$HOME/Library/Scripts"
  AGENTS_DIR="$HOME/Library/LaunchAgents"
fi
mkdir -p "$SCRIPTS_DIR" "$AGENTS_DIR"

ALERT_SCRIPT="$SCRIPTS_DIR/lembrete-$SLUG.sh"

# escapa aspas duplas e barras para uso dentro de strings AppleScript
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
TITLE_ESC=$(esc "$TITLE")
BODY_ESC=$(esc "$BODY")
BODY_NOTIF=$(printf '%s' "$BODY_ESC" | tr '\n' ' ' | cut -c1-180)

# ---------- gera o script de alerta ----------
cat > "$ALERT_SCRIPT" <<EOF
#!/bin/bash
# Gerado pela skill lembrete-alerta — rótulo: $SLUG
# Uso: lembrete-$SLUG.sh [test|last]
# Toca continuamente até clicar OK; "Soneca 5 min" silencia e volta a tocar.
STAGE="\${1:-manual}"

if [ "\$STAGE" = "test" ]; then
  GIVEUP=8        # diálogo expira em 8 s no teste
  MAX_CYCLES=2    # permite demonstrar uma soneca no teste
  SNOOZE=5        # soneca de 5 s no teste
else
  GIVEUP=600      # rediálogo a cada 10 min
  MAX_CYCLES=12   # ~2 h de insistência no máximo
  SNOOZE=300      # soneca de 5 min
fi

RING_FLAG=""
RING_PID=""

start_ring() {
  osascript -e 'set volume output volume 75' 2>/dev/null
  RING_FLAG=\$(mktemp /tmp/lembrete-$SLUG.XXXXXX)
  ( while [ -e "\$RING_FLAG" ]; do
      afplay /System/Library/Sounds/Sosumi.aiff
      sleep 0.4
    done ) &
  RING_PID=\$!
}

stop_ring() {
  [ -n "\$RING_FLAG" ] && rm -f "\$RING_FLAG"
  [ -n "\$RING_PID" ] && wait "\$RING_PID" 2>/dev/null
  RING_FLAG=""; RING_PID=""
}

notify() {
  osascript -e "display notification \"$BODY_NOTIF\" with title \"$TITLE_ESC\" sound name \"Glass\"" 2>/dev/null
}

PREV_VOL=\$(osascript -e 'output volume of (get volume settings)' 2>/dev/null)

notify
start_ring
CYCLE=0
while :; do
  CYCLE=\$((CYCLE + 1))
  RES=\$(osascript 2>/dev/null <<APPLESCRIPT
display dialog "🔔 $TITLE_ESC

$BODY_ESC" with title "Lembrete" buttons {"Soneca 5 min", "OK"} default button "OK" with icon caution giving up after \$GIVEUP
APPLESCRIPT
) || RES=""

  case "\$RES" in
    *"button returned:OK"*)
      stop_ring
      break
      ;;
    *"Soneca"*)
      stop_ring
      if [ "\$STAGE" = "test" ] && [ \$CYCLE -ge \$MAX_CYCLES ]; then break; fi
      sleep "\$SNOOZE"
      notify
      start_ring
      ;;
    *)
      # diálogo expirou ou falhou: continua tocando e mostra de novo,
      # até a trava de segurança
      if [ \$CYCLE -ge \$MAX_CYCLES ]; then
        stop_ring
        break
      fi
      ;;
  esac
done

if [ -n "\$PREV_VOL" ]; then
  osascript -e "set volume output volume \$PREV_VOL" 2>/dev/null
fi

# último disparo agendado: remove os agendamentos deste rótulo
if [ "\$STAGE" = "last" ]; then
  for p in "\$HOME/Library/LaunchAgents/com.lembrete.$SLUG-"*.plist; do
    [ -e "\$p" ] || continue
    lbl=\$(basename "\$p" .plist)
    launchctl bootout "gui/\$(id -u)/\$lbl" 2>/dev/null
    rm -f "\$p"
  done
fi
EOF
chmod +x "$ALERT_SCRIPT"

# ---------- gera e registra um plist por horário ----------
TOTAL=$#
IDX=0
for DT in "$@"; do
  IDX=$((IDX + 1))
  if ! date -j -f "%Y-%m-%d %H:%M" "$DT" +%s >/dev/null 2>&1; then
    echo "Data/hora inválida (use YYYY-MM-DD HH:MM): $DT" >&2
    exit 1
  fi
  TS=$(date -j -f "%Y-%m-%d %H:%M" "$DT" +%s)
  if [ "$TS" -le "$(date +%s)" ] && [ "${DRY_RUN:-0}" != "1" ]; then
    echo "Horário já passou: $DT" >&2
    exit 1
  fi
  MONTH=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$DT" +%m)))
  DAY=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$DT" +%d)))
  HOUR=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$DT" +%H)))
  MIN=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$DT" +%M)))

  STAGE_ARG="alarm"
  [ "$IDX" -eq "$TOTAL" ] && STAGE_ARG="last"

  PLIST="$AGENTS_DIR/com.lembrete.$SLUG-$IDX.plist"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lembrete.$SLUG-$IDX</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$ALERT_SCRIPT</string>
        <string>$STAGE_ARG</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Month</key>
        <integer>$MONTH</integer>
        <key>Day</key>
        <integer>$DAY</integer>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MIN</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

  plutil -lint -s "$PLIST" >/dev/null

  if [ "${DRY_RUN:-0}" != "1" ]; then
    launchctl bootout "gui/$(id -u)/com.lembrete.$SLUG-$IDX" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
  fi
  echo "Agendado: $DT -> com.lembrete.$SLUG-$IDX ($STAGE_ARG)"
done

echo "Script de alerta: $ALERT_SCRIPT"
echo "Teste agora com: bash $ALERT_SCRIPT test"
