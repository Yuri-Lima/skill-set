---
name: explain-implementation-video
description: >-
  Make a two-act implementation-explanation video: Eve narrates locked
  decisions on a studio board, then a product recording proves the result.
  Use when the user runs /explain-implementation-video, or says "full video
  zero to here", "explain the implementation decisions", "decision film",
  "use my Desktop recording", "presenter plus screencap", or wants a long
  walkthrough of what shipped plus a live/host .mov. Not for a short
  single-route ticket demo — that is ticket-demo-video.
---

# Explain implementation video

Two acts, **one Eve audio bed**. Length follows the story (often 90s–3min), never a 15s or 45s cap.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.
`$DEMO_DIR` is the sibling `ticket-demo-video` install
(`$SKILL_DIR/../ticket-demo-video`).

| Act | Picture | Eve talks about |
| --- | --- | --- |
| 1 | Studio decision cards | Problem, locked options, what shipped |
| 2 | User `.mov` or host walkthrough | Proof after the change |

Reuse **`ticket-demo-video`** for Eve assets, stitch, chromakey PIP, and publish. This skill owns the two-act clock, bring-your-own recording, and clip-boundary beats.

Eve scripts / compose / publish:

- `$DEMO_DIR/scripts/stitch-eve.sh`
- `$DEMO_DIR/scripts/compose-pip.sh`
- `$DEMO_DIR/scripts/publish-demo.sh`
- `$DEMO_DIR/assets/eve-idle.jpg`

Do not copy crop, alpha, or publish-path facts here. Follow that skill.

Scratch: `docs/review-impact/<slug>/`. Watch path: `docs/ticket-demos/<slug>.mp4`. Never send the user to session `videos/N.mp4`. Do not commit mp4s.

## When not to use

- One screen, one beat, Playwright can drive it → **`ticket-demo-video`**
- Silent red/green bug pair → **`claim-fix-ticket`**

## Inputs (resolve before generating)

1. Ticket / topic + locked decisions (what is *not* still open)
2. Spoken script — full story, with finance-expert first-mention expansions only (see Script). Do not shrink to fit a time box.
3. Act 2 picture: a local `.mov`/`.mp4`, **or** a host URL you will record. Do not invent a UI.
4. Keyword list for Act 1 cards (option names, identifiers, counts)

If a recording is missing and no host is reachable, ask once.

## Original picture (no redaction)

Act 2 is the user’s recording or a host capture **as shot**. Scale and pad
to 1280×720 only (letterbox). That is a format convert, not an edit.

Do **not**:

- Blur, mosaic, pixelate, or black-bar anything in the frame
- Overlay a cover-up, sticker, or “redacted” box on the source
- Crop or zoom to hide a field, toast, URL, or value
- Drop or reorder frames to omit what was recorded
- Replace the user’s `.mov`/`.mp4` with a sanitized cut
- Ask the user to re-record so a secret is off screen

If a password, token, or env value is in the screencap, it stays in the
picture. Eve may talk about what the frame shows. Do not hide it.

## 1. Script

Write Act 1 then Act 2. Put picture-cut words at the start of a phrase after a pause (`Option A`, `admin`, `clone`, `Forty-nine`, `live host`).

### First-mention expansions (finance-expert terms only)

The audience already knows this product and stack. **Do not** pause to define system, ticket, vendor, or everyday money words.

Before generating Eve, scan the spoken script. On the **first** time she says a **finance-expert** term (Act 1 + Act 2 share one audio bed), keep the short form **and** say what it means in the same breath:

> `[short form] — that stands for [full name]`

Expand only terms a general engineer on this team would not already know — return methodologies, institutional reporting, and instrument jargon:

- `T-W-R — that stands for time-weighted return`
- `M-W-R — that stands for money-weighted return`
- `G-I-P-S — that stands for Global Investment Performance Standards`
- `N-A-V — that stands for net asset value`
- `I-R-R — that stands for internal rate of return`
- `T-bill — that stands for Treasury bill`
- `A-F-F-O — that stands for adjusted funds from operations`

**Never expand** product, stack, board, or vendor names, or money words everyone here already uses:

- Product / board: IPT, ADR, MR, ticket numbers
- Stack / files: API, UI, CSV, HTTP, JWT, CORS, OFX, QIF
- Vendors / markets: Yahoo, FMP, IBKR, USD, ETF, FX
- Proper names already spoken in full: Sharpe, Sortino, Eve

Later mentions stay short. If the expansion would push a clip past 13s, split after that sentence — do not drop a *finance* expansion to fit Imagine’s 15s cap.

If you are not sure it is finance-expert jargon, **do not expand it**. Look up the expansion in the repo or ticket; do not invent one.

Write the spoken line into `script.txt` **before** the first `reference_to_video` call. The Imagine prompt must include that exact sentence.

Split Eve on sentence boundaries into **8–13s** clips. Prefer ~10s. Do not drop lines so a clip fits 15s — 15s is only the Imagine per-clip limit.

## 2. Eve takes

From `eve-idle.jpg`, voice **`eve`**, 16:9, solid `#00FF00`, talking pose, both arms, no desk/office/TV, no pointing. Prompt must include the **exact** spoken lines plus `<IMAGE_0>` and `<AUDIO_0>`.

Batching (Imagine):

- At most **4** `reference_to_video` calls per step
- After a 429, **2** per step (team cap is 2 req/s)
- Session files (`videos/1.mp4`…) are **completion order**, not script order

Copy into spoken order **before** stitch:

```text
docs/review-impact/<slug>/eve-01.mp4
docs/review-impact/<slug>/eve-map.txt   # 01 = videos/1.mp4 = "Ticket …"
```

Then `bash "$DEMO_DIR/scripts/stitch-eve.sh" --out docs/review-impact/<slug>/eve-full.mp4 eve-01.mp4 …`

## 3. Beats (clip boundaries, not silencedetect)

Each Imagine clip is padded to the requested duration. `align-vo.py` without Whisper packs later sentences into early islands on a long stitch. **Do not use those times** for a multi-clip decision film.

```
studio_at_ms = 1000 * sum(duration(eve-01) … duration(eve-N-1)) + offset_ms_inside_clip
```

`ffprobe` each `eve-NN.mp4`. Confirm speech starts with `silencedetect` **inside that clip** if the keyword is not at 0.

Act 2 starts at `sum(durations of Act 1 clips)`. Trim the studio recording to that instant so the first Act 2 sentence lands on the screencap.

Write `studio-beats.json` as `[{ "at": ms, "action": "kicker" }, …]` for this skill’s board.

## 4. Act 1 studio board

Copy `$SKILL_DIR/scripts/studio-board-decisions.html` into `docs/review-impact/<slug>/` and change only strings + `actions`. Do not put product UI text on an Imagine TV.

Record with `$SKILL_DIR/scripts/record-studio.mjs` (this skill — the ticket-demo recorder resolves Playwright from the skill path and fails when the skill lives outside the repo):

```bash
node "$SKILL_DIR/scripts/record-studio.mjs" \
  --html docs/review-impact/<slug>/studio-board.html \
  --beats docs/review-impact/<slug>/studio-beats.json \
  --out docs/review-impact/<slug>/studio.webm \
  --duration <act1_seconds>
```

Uses `playwright` from **cwd** and `channel: 'chrome'` if bundled Chromium is missing.

## 5. Act 2 ingest

If the user handed a recording:

```bash
bash "$SKILL_DIR/scripts/build-two-act-picture.sh" \
  --studio docs/review-impact/<slug>/studio.webm \
  --studio-end <act1_seconds> \
  --screencap /path/to/user.mov \
  --out docs/review-impact/<slug>/picture.mp4
```

That scales/pads to **1280×720 @ 24fps** (source may be 120fps / 4K) and concats Act 1 + Act 2. No `xfade` (ffmpeg 7 CFR `rate of 1/0`). No filters that hide pixels.

Before writing Act 2 lines, extract 1 frame every ~3s from the screencap and read them. Time Eve’s last clips to what the file actually shows (login, list, error toast).

If there is no file, record the host the same way as `ticket-demo-video` live UI, then pass that webm as `--screencap`.

## 6. Compose + publish

```bash
bash "$DEMO_DIR/scripts/compose-pip.sh" \
  --ui docs/review-impact/<slug>/picture.mp4 \
  --presenter docs/review-impact/<slug>/eve-full.mp4 \
  --slug <slug> \
  --ui-trim 0 \
  --pip-width 500 \
  --out docs/review-impact/<slug>/ticket-<slug>.mp4

bash "$DEMO_DIR/scripts/publish-demo.sh" \
  --in docs/review-impact/<slug>/ticket-<slug>.mp4 \
  --slug <slug>
```

`--ui-trim 0` — picture t=0 is already Eve t=0. Smaller PIP so Act 2 lists/login stay readable.

## 7. Check

Extract frames at Act 1 keywords and at Act 2 start + each proof beat:

- Eve is a cutout (no green, no white box), both arms, talking pose
- Card text matches the line she is on
- First mention of each **finance-expert** term in `script.txt` / Eve audio includes the full name; later hits stay short. Product/stack names (IPT, API, FMP, CSV) are **not** expanded
- At Act 2 start the screencap is on screen, not the board
- PIP is not covering the control she names (move Eve, do not cover the UI)
- Act 2 still shows the original frame contents — nothing blurred or barred

Finish only when `docs/ticket-demos/<slug>.mp4` exists. Give the user that path.
