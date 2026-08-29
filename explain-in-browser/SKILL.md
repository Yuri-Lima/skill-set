---
name: explain-in-browser
description: >
  Open mid-to-long explanations as a readable HTML page in the browser
  instead of dumping them in the terminal. Keep a short teaser in the
  TUI (headline, a few bullets, file path). Use when the answer would
  be a how/why/analysis/walkthrough, when terminal reading would be
  painful, or when the user runs /explain-in-browser.
---

# Explain in browser

The TUI is a bad surface for mid-to-long prose. Write the full
explanation as markdown, render it, open the HTML, and keep the
terminal to a teaser.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

## When this applies

Any of:

- The reply would be ~250+ words or 3+ sections
- The user asked how / why / analyze / walk through / explain
- The answer is a system map, investigation, or design
- The user ran `/explain-in-browser`

Stay in the terminal for short answers: yes/no, a path, a 5-line
status, a single command.

## Steps

1. Write the full explanation as markdown to
   `.grok/explanations/<slug>-<YYYYMMDD-HHMMSS>.md` under the repo
   (create the directory). First line is `# Title`. Use headings,
   lists, and tables — not one unsectioned wall.

2. Render and open:

```bash
node "$SKILL_DIR/scripts/render-explanation.mjs" \
  --in ".grok/explanations/<file>.md"
```

The script writes a sibling `.html`, opens it, and prints the HTML
path. Pass `--no-open` only when a test or the user said not to open.

3. Terminal reply is only:

- One headline
- 4–6 bullets
- The HTML path

Do not paste the full explanation into the TUI after opening.

## Do not

- Use this for short answers
- Skip the render step and dump the markdown in chat
- Commit files under `.grok/explanations/`
