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
**slightly translucent talking-head cutout** in the bottom-right (no
white box, no office TV, both arms in frame). She does **not** point.
Her voice is the only audio.

Two-act decision films (studio board, then a long host/.mov proof) live
in **`explain-implementation-video`**. Silent red/green pairs live in
**`claim-fix-ticket`**.

## 0. Auth bootstrap (blocking, first run in this repo)

Do this **before** recording. If sign-in is not configured, **stop** —
the skill cannot continue.

1. Run `node "$SKILL_DIR/scripts/resolve-demo-auth.mjs" --scan`.
2. Show the user what you found (login routes, auth providers, demo-user
   docs) and the **suggested** method.
3. Ask which method they want:
   - `password` — email + password on the app’s login page
   - `storage_state` — they already have a Playwright session JSON
   - `none` — the route is public; no sign-in
4. Ask for **temporary or fake** credentials (or a session file path).
   Do not invent a product user. Do not reuse credentials from another
   repo. Prefer a disposable account.
5. Write gitignored `docs/review-impact/demo-auth.json` (see
   `$SKILL_DIR/demo-auth.example.json`). Env `DEMO_EMAIL` +
   `DEMO_PASSWORD` also works if they already have those set.
6. Only then call `login()`. Later runs in the same repo reuse that
   file; do not re-ask unless login fails.

`login()` throws `AUTH_NOT_CONFIGURED` if step 5 never happened.

## Inputs (resolve before generating)

1. Ticket number + one sentence of what shipped
2. Route to demo
3. Spoken script — every sentence a viewer needs to understand the change.
   Write the full story first. Do not shrink, rush, or drop lines to fit
   a time box.
4. Keyword map: each picture-cut word → one UI action. Times come from
   measuring the finished Eve take, not from a words-per-minute guess.

If any of those is missing, ask once. Do not invent a UI surface.

Working files (Eve takes, studio, Playwright webms) go under
`docs/review-impact/<slug>/` (gitignored). The local watch path is
`docs/ticket-demos/<slug>.mp4` — also gitignored. Tell the user that
path. Do not send them to session `videos/N.mp4`. Do not commit mp4s,
scratch webms, or helper captures. For review, upload with
`gitlab__upload_markdown` (or the host’s file upload) and put the
markdown in the MR/PR body.

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
- Tell the user to click `videos/N.mp4` as the way to watch — always give `docs/ticket-demos/<slug>.mp4` (local) or the MR upload
- Generate Eve on an office, desk, or TV backdrop — she must be on flat `#00FF00` so the key can drop the background

## Pipeline (one ticket)

Audio is the master clock. Radio-edit the voice first, then cut picture
**onto the word** (vertical edit). Do not estimate UI times from
words-per-minute and hope Eve matches.

### 1. Script

Write the full story first. Put each picture-cut word at the start of a
phrase after a pause so alignment can hear it.

~140 words/min is only a **planning** hint for how long the take might
run. It is not the picture clock.

Typical full explanations land in the 25–45s range. Shorter is fine only
when the change is truly one beat.

### 2. Presenter + voice

Reuse the skill assets when they exist — do not regenerate Eve each ticket:

- `$SKILL_DIR/assets/eve-idle.jpg` — talking pose

If you must generate a new presenter: `image_gen` 16:9 on a **flat
chroma-key green (`#00FF00`)** backdrop. No desk, no office, no TV.
Talking pose only — do not generate a pointing still or arm-raise clip.

- Voice: **`eve`** (female). List voices only if the user asks for another.
- `reference_to_video` from **eve-idle.jpg**. The prompt must keep the
  **solid green screen** and include the **exact spoken lines**.
- If `TARGET` > 15s (the usual case), split the script on sentence
  boundaries into consecutive clips of 8–15s. Then stitch:

```bash
bash "$SKILL_DIR/scripts/stitch-eve.sh" \
  --out docs/review-impact/<slug>/eve-<id>.mp4 \
  <clip1.mp4> <clip2.mp4> [...]
```

- Do not rush or drop sentences to stay under 15s. The 15s number is
  only the per-clip API limit.
- Prefer 8–12s clips over one long take — lip-sync holds better.
- The stitched talking-head file is the audio bed. Green stays on the
  plate until `compose-pip.sh` keys it out.

### 3. Measure words (radio-edit lock)

```
python3 "$SKILL_DIR/scripts/align-vo.py" \
  --audio docs/review-impact/<slug>/eve-<id>.mp4 \
  --script docs/review-impact/<slug>/script.txt \
  --whisper-json docs/review-impact/<slug>/eve-<id>.json \
  --map "kicker=Ticket,cards=Annual rate" \
  --preroll 0.7 \
  --out-json docs/review-impact/<slug>/align.json \
  --out-studio docs/review-impact/<slug>/studio-beats.json \
  --out-ui docs/review-impact/<slug>/ui-clock.json
```

Whisper word JSON is the preferred lock (`whisper --word_timestamps True`
or a compatible dump). Without it, the script maps sentences onto
silencedetect islands.

- Studio `at` = the word start (card changes **on** the keyword).
- UI `go` = word start minus `--preroll` (default 0.7s) so the cursor
  arrives and the click lands **on** the word — a J-cut.

If a click needs to be seen, keep ≥1.5s of picture after the phrase
starts. Retake **only** the UI if a hit is >0.4s off; do not regenerate
Eve unless the script changed.

### 4. Studio board (optional)

The office TV warps product text. Instead, render **crisp HTML cards**
with the exact labels she speaks, timed to the beat table, and sit Eve
on the right of that board.

1. Copy `$SKILL_DIR/scripts/studio-board.html` and keep the card chrome.
   Change only the strings and the `actions` map so they match this ticket.
2. Use `studio-beats.json` from align-vo (measured word starts). Fade/type
   the phrase she is saying at that second.
3. Record the board, then composite:

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

`compose-studio.sh` crops Eve to her (drops the fake TV) and overlays
her on the right. That `eve-*-studio.mp4` is the presenter input for
PIP. Use `--pip-width 500` so the cards stay readable.

Do not `image_to_video` a product screenshot onto the TV. The studio
board is code-drawn text so button labels stay sharp.

### 5. Live UI recording

Resolve `PLAYWRIGHT_BASE_URL` from the local stack. Prefer host
localhost when auth emails use `localhost` in `redirect_to`.
Sign-in uses `docs/review-impact/demo-auth.json` or `DEMO_EMAIL` +
`DEMO_PASSWORD` (see Auth bootstrap). Selectors default to `#email` /
`#password` / a Sign in button and can be overridden in that file.

Helpers: `injectCursor`, `clickHuman`, `typeHuman`, `login`,
`recordTicket` in `$SKILL_DIR/scripts/record-live-ui.mjs`. Write the
ticket-specific `run(page)` in gitignored
`docs/review-impact/<slug>/` — do not hard-code ticket locators into
the skill script.

Recording rules:

- Login **without** `recordVideo`; save `storageState`; open a **new**
  context with `recordVideo` at `1440×900`
- Inject the demo cursor **before** `goto`
- `run(page, clock)` receives a clock whose `t=0` is 400ms after `ready`.
  Use `await clock.until(page, beat.go * 1000)` from `ui-clock.json`.
- A `<out>.sync.json` sidecar stores `runMs`. `compose-pip.sh` trims
  that many seconds off the webm so Eve t=0 matches the first UI action
  beat. Do not guess load time.
- Human motion: `mouse.move({ steps: 18 })`, click delay ~70ms, type
  `pressSequentially` ~95ms/char
- Scope locators to the widget you opened (`row.locator(...)`)
- End with ~0.7s hold so the last frame is readable

### 6. Compose PIP

```bash
bash "$SKILL_DIR/scripts/compose-pip.sh" \
  --ui docs/review-impact/<slug>/live/ui-<id>.webm \
  --presenter docs/review-impact/<slug>/eve-<id>.mp4 \
  --slug <slug> \
  --out docs/review-impact/<slug>/ticket-<id>.mp4
```

`--ui-trim` comes from `<ui>.sync.json` `runMs` when present so Eve t=0
matches the UI clock. Optional `--target SECONDS` pads both streams out
to at least that clock (never truncates). Default clock is
`max(ui, presenter)`.

Defaults: talking pose only (ignore `--point`), crop `820:720:360:0`
so both arms stay in frame, `--alpha 0.72`, `--pip-width 580`.
Chromakey `#00FF00`. Audio stays the talking-head track.

You can still run `compose-studio.sh` first if the ticket needs the KPI
cards behind her; that script also keys the green. Prefer piping the
raw green talking-head into `compose-pip.sh` so the live UI shows
through her.

### 7. Check sync

Extract a frame at each **keyword** time from `ui-clock.json` (`at`, not
`go`): `ffmpeg -ss <at> -frames:v 1`. Confirm:

- Cursor is on the control she is naming at that second
- Eve is a cutout (no green halo, no white box), slightly translucent,
  both arms visible, talking pose only
- PIP is not covering the control being used (if it is, scroll first)
- No login screen, no blank load

If every hit is late or early by the same amount, fix `--ui-trim` (or
`runMs` in the sidecar) and recompose. If one hit is >0.4s off, retake
**only** the UI recording. Do not regenerate Eve unless the script
changed.

### 8. Publish locally, attach to the MR

After sync is good, copy the finished mp4 out of the gitignored scratch
dir. Do not stop at `docs/review-impact/` — `git clean` wipes that folder.

```bash
bash "$SKILL_DIR/scripts/publish-demo.sh" \
  --in docs/review-impact/<slug>/ticket-<id>.mp4 \
  --slug <slug>
```

That writes `docs/ticket-demos/<slug>.mp4` locally (`*.mp4` is
gitignored). `compose-pip.sh --slug` does the same copy. **Finish only
after that file exists.** In the reply, give the local path. If there
is an MR, upload the mp4 and embed it in the description — do not
commit the binary.

## Several tickets

One presenter image for the set. One Eve talking-head (stitched if the
script ran long) **and** one UI recording **per ticket**, both as long as
that ticket’s beat table. Do not stitch tickets into one video unless the
user asks.

## Before / after bug clips

Silent red/green pairs that prove a ticket (issue region boxed, rest of
the page dimmed) live in **`claim-fix-ticket`**. Use that skill when the
user wants a before video of the wrong behavior and an after video of the
same region once it is fixed. Do not invent a second highlight helper —
import `labelIssueArea` from that skill's `scripts/label-issue-area.mjs`.

## Two-act decision films

A long walkthrough of locked implementation choices plus a host/.mov
proof is **`explain-implementation-video`**. It reuses this skill’s Eve
assets, stitch, chromakey PIP, and publish scripts.
