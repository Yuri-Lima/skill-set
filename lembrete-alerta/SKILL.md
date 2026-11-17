---
name: lembrete-alerta
description: Agenda lembretes locais no macOS que tocam um alarme sonoro real e mostram um diálogo na tela com os detalhes (endereço, documentos, checklist), usando launchd — funciona offline, sem depender do Claude estar aberto. Use sempre que o usuário pedir um lembrete, alarme, alerta ou aviso antes de um compromisso — cita, consulta, reunião, voo, entrega, medicação — ou disser "me lembra de X", "me avisa N horas antes", "cria um alerta com barulho", mesmo que não mencione som, script ou launchd. Também cobre listar e cancelar lembretes já agendados.
---

# Lembrete com alerta sonoro (macOS)

Cria lembretes agendados que disparam localmente no Mac do usuário: notificação do macOS, **alarme sonoro contínuo que só para quando o usuário clica OK**, e um diálogo na tela com o conteúdo do lembrete. O diálogo tem um botão **"Soneca 5 min"** que silencia e volta a tocar depois de 5 minutos; se o diálogo expirar sem resposta, ele reaparece e o som continua (trava de segurança: para sozinho após ~2 h). Sem voz (sem `say`) — o usuário prefere apenas som + diálogo.

## Fluxo

1. **Colete do usuário (ou da conversa):**
   - O evento: o quê, onde, quando (data e hora exatas).
   - Antecedência dos disparos. Padrão se não disser: 2 h e 1 h antes. Converta para datas/horas absolutas.
   - O que o diálogo deve mostrar: endereço, documentos a levar, checklist. Monte um corpo multilinha com bullets (•).

2. **Agende com o script empacotado** (um único comando; datas em ordem cronológica — a última marca a limpeza automática):

   ```bash
   bash ~/.claude/skills/lembrete-alerta/scripts/agendar.sh \
     "cita-aeat" \
     "Cita AEAT hoje às 10:15" \
     "Cl Palacio Valdés, 7 — Oviedo
   • Código: 236152052
   • TIE
   • Passaporte" \
     "2026-11-19 08:15" "2026-11-19 09:15"
   ```

   - 1º arg: rótulo curto (vira `com.lembrete.<rotulo>`); use letras minúsculas, números e hífens.
   - 2º arg: título (aparece na notificação e no diálogo).
   - 3º arg: corpo multilinha (endereço + checklist). Evite aspas duplas no texto; o script escapa o básico, mas texto simples é mais robusto.
   - Demais args: cada horário de disparo, formato `YYYY-MM-DD HH:MM`, em ordem. Após o último disparo os agendamentos se removem sozinhos (launchd repetiria todo ano sem isso).

3. **Teste na hora** — o usuário deve ouvir o alerta agora, em versão curta (toca por ~8 s e para sozinho; soneca vira 5 s). O script `agendar.sh` imprime o caminho do script de alerta gerado; rode-o com `test`:

   ```bash
   bash ~/Library/Scripts/lembrete-<rotulo>.sh test
   ```

   Confirme com o usuário que ouviu/viu. Se a saída contiver `button returned:OK`, ele clicou — prova de que chegou.

4. **Avise as condições:** o Mac precisa estar ligado e com sessão iniciada no horário. Dormindo, o macOS dispara ao acordar; desligado, perde o disparo. Se o compromisso for crítico, ofereça uma segunda via (tarefa agendada na nuvem com notificação no celular), mas só crie se o usuário pedir.

## Listar e cancelar

```bash
bash ~/.claude/skills/lembrete-alerta/scripts/listar.sh
```

```bash
bash ~/.claude/skills/lembrete-alerta/scripts/cancelar.sh <rotulo>
```

`cancelar.sh` remove os agendamentos do launchd, os .plist e o script de alerta daquele rótulo.

## Como funciona (para depurar)

- `agendar.sh` gera `~/Library/Scripts/lembrete-<rotulo>.sh` (o alerta: notificação + loop contínuo de `Sosumi.aiff` a volume 75% em segundo plano, diálogo `osascript` com botões "Soneca 5 min"/"OK"; OK encerra o som e restaura o volume anterior, soneca silencia por 5 min e recomeça, timeout do diálogo reabre-o com o som ainda tocando, até 12 ciclos de 10 min) e um `~/Library/LaunchAgents/com.lembrete.<rotulo>-<i>.plist` por horário, registrados com `launchctl bootstrap gui/$UID`.
- O último disparo roda com argumento `last`, que faz `launchctl bootout` de todos os agents do rótulo e apaga os .plist (o script de alerta fica, inofensivo, para re-uso/teste).
- `DRY_RUN=1 agendar.sh ...` gera tudo em `./dry-run/` sem tocar no launchd — use para verificar a geração sem efeitos.
- Falha comum: data no passado ou formato errado → `agendar.sh` aborta indicando o argumento; aspas duplas no título/corpo → prefira reescrever o texto sem elas.
