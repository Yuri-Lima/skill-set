---
name: ticket-demo-video
description: >-
  Record a per-ticket product demo whose length follows a full spoken
  explanation (not a 15s cap): Eve (woman) presents in the corner while a
  live UI walkthrough (real cursor, clicks, typing) stays in sync with her
  voice. Use when the user runs /ticket-demo-video, or says "ticket demo
  video", "explain this ticket in a video", "presenter plus live UI", "Eve
  demo", or wants a synced walkthrough of a shipped issue/MR.
---

# Ticket demo video

One clip per ticket. **Length = the explanation**, never a fixed 15s. The
working recipe is **live UI + Eve PIP**, not stills or Ken Burns B-roll.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

Target look: full-frame product UI being operated like a human; Eve is a
**transparent cutout** in the bottom-right (no white box, no office TV);
on important keywords she **raises her arm and points** at the control
the cursor is on. Her voice is the only audio.

## Inputs (resolve before generating)

1. Ticket number + one sentence of what shipped
2. Route to demo
3. Spoken script — every sentence a viewer needs to understand the change.
   Write the full story first. Do not shrink, rush, or drop lines to fit
   a time box.
4. Keyword map: each picture-cut word → one UI action. Times come from
   measuring the finished Eve take, not from a words-per-minute guess.

If any of those is missing, ask once. Do not invent a UI surface.

Working files go under gitignored `docs/review-impact/<slug>/`. The local
watch path is `docs/ticket-demos/<slug>.mp4` (also gitignored). Do not
commit mp4s. For review, `gitlab__upload_markdown` and put the markdown
in the MR body. Do not send the user to session `videos/N.mp4`.

## Do not

- Force, pad-to, or cut the finished video at 15s
- Shrink, rush, or drop spoken lines so Eve fits in one clip
- `image_edit` or `image_to_video` a real product screenshot (text warps)
- Cut away to stills while she talks (desyncs)
- Use `xfade` + `fps=` in ffmpeg 7 (CFR error `rate of 1/0`)
- Leave login in the recorded clip (login in a separate context)
- Click a global `input[name=amount]` when every row mounts an edit form —
  scope to the opened row
- Use `Meta+A` inside the Playwright Linux image (`Control+A`)
- Estimate picture times from words-per-minute and record UI against that guess
- Leave the finished clip only under `docs/review-impact/` or session `videos/`
- Commit `docs/ticket-demos/*.mp4`
- Generate Eve on an office, desk, or TV backdrop — she must be on flat
  `#00FF00` so the key can drop the background

## Pipeline (one ticket)

Audio is the master clock. Radio-edit the voice first, then cut picture
**onto the word**. Do not estimate UI times from words-per-minute.

### 1. Script

Write the full story first. Put each picture-cut word at the start of a
phrase after a pause so alignment can hear it.

~140 words/min is only a planning hint. Typical full explanations land
in the 25–45s range.

### 2. Presenter + voice

Reuse the skill assets — do not regenerate Eve each ticket:

- `$SKILL_DIR/assets/eve-idle.jpg` — talking pose
- `$SKILL_DIR/assets/eve-point.jpg` — held point
- `$SKILL_DIR/assets/eve-point.mp4` — arm raise (6s)

If you must generate a new presenter: `image_gen` 16:9 on a **flat
chroma-key green (`#00FF00`)** backdrop. No desk, no office, no TV.
Pointing pose via `image_edit` from that still (right arm, index finger
up-left). Animate the raise with `image_to_video` from the idle still.

- Voice: **`eve`** (female). List voices only if the user asks for another.
- `reference_to_video` from **eve-idle.jpg**. Keep the solid green screen
  and include the **exact spoken lines**.
- If `TARGET` > 15s, split the script on sentence boundaries into
  consecutive 8–15s clips. Then stitch:

```bash
bash "$SKILL_DIR/scripts/stitch-eve.sh" \
  --out docs/review-impact/<slug>/eve-<id>.mp4 \
  <clip1.mp4> <clip2.mp4> [...]
```

- Do not rush or drop sentences to stay under 15s. 15s is only the
  per-clip API limit. Prefer 8–12s clips — lip-sync holds better.

### 3. Measure words (radio-edit lock)

```
python3 "$SKILL_DIR/scripts/align-vo.py" \
  --audio docs/review-impact/<slug>/eve-<id>.mp4 \
  --script docs/review-impact/<slug>/script.txt \
  --whisper-json docs/review-impact/<slug>/eve-<id>.json \
  --map "kicker=Ticket,cards=Annual rate" \
  --point "cards" \
  --point-hold 2.0 \
  --preroll 0.7 \
  --out-json docs/review-impact/<slug>/align.json \
  --out-studio docs/review-impact/<slug>/studio-beats.json \
  --out-ui docs/review-impact/<slug>/ui-clock.json
```

Whisper word JSON is the preferred lock. Without it, the script maps
sentences onto silencedetect islands.

- Studio `at` = the word start.
- UI `go` = word start minus `--preroll` (default 0.7s) so the click
  lands **on** the word.
- `--point` marks keywords where Eve's arm should raise.

If a click needs to be seen, keep ≥1.5s of picture after the phrase
starts. Retake **only** the UI if a hit is >0.4s off.

### 4. Studio board (optional)

The office TV warps product text. Render crisp HTML cards with the
labels she speaks. Copy `$SKILL_DIR/scripts/studio-board.html`, change
only the strings and `actions` map.

```bash
node "$SKILL_DIR/scripts/record-studio.mjs" \
  --html "$SKILL_DIR/scripts/studio-board.html" \
  --beats docs/review-impact/<slug>/studio-beats.json \
  --out docs/review-impact/<slug>/studio.webm \
  --duration <TARGET>

bash "$SKILL_DIR/scripts/compose-studio.sh" \
  --eve docs/review-impact/<slug>/eve-<id>.mp4 \
  --studio docs/review-impact/<slug>/studio.webm \
  --out docs/review-impact/<slug>/eve-<id>-studio.mp4
```

### 5. Live UI recording

Resolve `PLAYWRIGHT_BASE_URL` from the local stack. Prefer host
localhost when auth emails use `localhost` in `redirect_to`.

Helpers: `injectCursor`, `clickHuman`, `typeHuman`, `login`,
`recordTicket` in `$SKILL_DIR/scripts/record-live-ui.mjs`. Write the
ticket-specific `run(page)` in gitignored
`docs/review-impact/<slug>/` — do not hard-code ticket locators into
the skill script.

Recording rules:

- Login **without** `recordVideo`; save `storageState`; open a **new**
  context with `recordVideo` at `1440×900`
- Inject the demo cursor **before** `goto`
- `run(page, clock)` — `t=0` is 400ms after `ready`. Use
  `await clock.until(page, beat.go * 1000)`
- `<out>.sync.json` stores `runMs`. `compose-pip.sh` trims that many
  seconds off the webm
- Human motion: `mouse.move({ steps: 18 })`, click delay ~70ms, type
  `pressSequentially` ~95ms/char
- Scope locators to the widget you opened
- End with ~0.7s hold so the last frame is readable

### 6. Compose PIP

```bash
bash "$SKILL_DIR/scripts/compose-pip.sh" \
  --ui docs/review-impact/<slug>/live/ui-<id>.webm \
  --presenter docs/review-impact/<slug>/eve-<id>.mp4 \
  --point "$SKILL_DIR/assets/eve-point.mp4" \
  --clock docs/review-impact/<slug>/ui-clock.json \
  --pip-width 520 \
  --slug <slug> \
  --out docs/review-impact/<slug>/ticket-<id>.mp4
```

Chromakeys `#00FF00` off Eve. On each `point` beat she swaps to
`eve-point.mp4` for `--point-hold` seconds (default 2.0). Audio stays
the talking-head track.

### 7. Check sync

Extract a frame at each keyword time from `ui-clock.json` (`at`, not
`go`). Confirm: cursor on the named control, Eve is a cutout (no green
halo), PIP is not covering the control, no login screen.

If every hit is late or early by the same amount, fix `--ui-trim` /
`runMs`. If one hit is >0.4s off, retake only the UI.

### 8. Publish locally, attach to the MR

```bash
bash "$SKILL_DIR/scripts/publish-demo.sh" \
  --in docs/review-impact/<slug>/ticket-<id>.mp4 \
  --slug <slug>
```

Writes `docs/ticket-demos/<slug>.mp4` locally (gitignored). Give the
user that path. If there is an MR, upload the mp4 and embed it in the
description — do not commit the binary.

## Several tickets

One presenter image for the set. One Eve talking-head **and** one UI
recording **per ticket**. Do not stitch tickets into one video unless
the user asks.

## Before / after bug clips

Silent red/green pairs that prove a ticket live in **`claim-fix-ticket`**.
Import `labelIssueArea` from that skill's
`scripts/label-issue-area.mjs`. Do not invent a second highlight helper.
