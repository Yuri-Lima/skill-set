---
name: eve-narration
description: >
  Narra um vídeo já gravado com a voz Eve da Grok, em ritmo natural, e queima
  a legenda no tempo da fala. Segura o quadro quando a frase é mais longa que
  a cena e não acelera o áudio. Use quando o usuário pedir narração Eve, voz
  no vídeo, legenda sincronizada, ou rodar /eve-narration.
---

# Eve narration

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

Turn a finished video plus a timed script into a new file with Eve's voice and burned captions. The picture waits when a line is longer than the scene. The voice is never sped up or slowed down.

This is not `ticket-demo-video`. Do not record the UI, do not generate a presenter, and do not call `reference_to_video` or macOS `say`.

## Before spawning

Resolve the inputs. If the mp4 is missing, ask once. The words come from an `.srt`, a narration text with timestamps, or both. If neither text exists, ask once. If the words are not Portuguese, stop and ask before any subagent runs.

Scratch directory: `/tmp/eve-narration-<stem>/`. Do not write scratch into the repo. Do not overwrite the source mp4.

Outputs, beside the source:

- `<stem>-com-audio.mp4`
- `<stem>-com-audio.srt`

## Team

Spawn these five subagents **one at a time**. Wait until the handoff file exists. Paste the contract into the prompt. Do not assume the subagent loaded this skill. A subagent runs only the script named in its contract.

### 1. Roteiro

Read the srt and the narration. Write `/tmp/eve-narration-<stem>/cues.json`: a JSON array ordered by time.

```json
{"start": 6.051, "spoken": "Frase um. [pause] Frase dois.", "caption": "Frase um. Frase dois."}
```

- `start` is seconds. Copy it from the srt. If there is no srt, copy `[mm:ss]` or `[hh:mm:ss]` from the narration. Do not estimate times.
- Same meaning. You may break a sentence for breath, say a filename or code the way a person would, and say section numbers as words ("Um", "Dois"). Do not add facts.
- `spoken` may contain `[pause]` or `[long-pause]` between sentences. No other tags.
- `caption` is `spoken` without tags.

### 2. Voz

```bash
python3 "$SKILL_DIR/scripts/tts_eve.py" \
  --cues /tmp/eve-narration-<stem>/cues.json \
  --out-dir /tmp/eve-narration-<stem>/clips
```

The script owns the voice, the language, and the pace. Do not pass a speed and do not time-stretch the wavs. It writes `00.wav`, `01.wav`, ...

### 3. Relógio

```bash
python3 "$SKILL_DIR/scripts/clock.py" \
  --video <source.mp4> \
  --cues /tmp/eve-narration-<stem>/cues.json \
  --clips-dir /tmp/eve-narration-<stem>/clips \
  --out /tmp/eve-narration-<stem>/bounds.json
```

The script owns how long each picture holds. Do not edit the pads. Do not change the audio to fit the old cut.

### 4. Montagem

```bash
python3 "$SKILL_DIR/scripts/assemble.py" \
  --video <source.mp4> \
  --clips-dir /tmp/eve-narration-<stem>/clips \
  --bounds /tmp/eve-narration-<stem>/bounds.json \
  --work /tmp/eve-narration-<stem> \
  --out <source-dir>/<stem>-com-audio.mp4 \
  --srt <source-dir>/<stem>-com-audio.srt
```

The script burns the caption and writes `timeline.json` in the work directory. Do not burn a second subtitle with the ffmpeg `subtitles` filter.

### 5. Checagem

```bash
python3 "$SKILL_DIR/scripts/check.py" \
  --video <source-dir>/<stem>-com-audio.mp4 \
  --timeline /tmp/eve-narration-<stem>/timeline.json
```

Exit 0 is the numeric pass. Then extract one frame at the first spoken cue's `out_start` plus 0.8s and look at it. The new caption is one line along the bottom. A block over the center of the frame fails.

The source may already have its own caption. The new line is still burned, and both may be visible. That is expected. A giant or clipped new line is not.

If the script exits non-zero or the frame fails, run Montagem again with that finding, then Checagem once more. If it still fails, stop and report the path plus the failing check.

## Finish

Tell the user the mp4 path, the srt path, and the duration. Say that Eve's pace was kept and the picture held where the line was longer than the scene.
