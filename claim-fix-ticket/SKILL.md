---
name: claim-fix-ticket
description: >-
  Claim a GitLab issue, record a before UI video of the wrong behavior
  with the issue region highlighted, implement the fix, run
  lint/typecheck/tests, then record an after video that highlights the
  same region once it is fixed. One ticket at a time. Use when the user
  runs /claim-fix-ticket, or says "claim and fix this ticket", "before
  and after video then fix", "highlight the issue area", or wants the
  claim → repro video → implement → gates → after video loop.
---

# Claim + fix a ticket (before/after UI)

One GitLab issue per run. Do not start the next ticket until this one is
**fixed** (gates green + after video published).

Spoken Eve + PIP walkthroughs stay in `ticket-demo-video`. This skill is
the **silent before/after pair** that proves the bug, then the fix.

`$SKILL_DIR` is the folder that contains this `SKILL.md` (project
`.grok/skills/claim-fix-ticket` or `~/.grok/skills/claim-fix-ticket`).

## Defaults

Resolve from the workspace, then fall back:

| Need | How to resolve |
| --- | --- |
| GitLab project | `git remote get-url origin` → `group/project` |
| Demo login | First run: scan + ask (see Auth bootstrap). Never invent a product user. |
| Quality gates | Project lint / typecheck / test commands (Nx, uv, etc.) |
| Demo URLs | `PLAYWRIGHT_BASE_URL`, `MAILPIT_URL` from the local stack |

## 0. Auth bootstrap (blocking, first run in this repo)

UI recordings cannot start until sign-in is configured for **this**
project.

1. `node "$SKILL_DIR/../ticket-demo-video/scripts/resolve-demo-auth.mjs" --scan`
2. Show the scan (suggested method, login routes, providers, demo-user
   docs).
3. Ask the user which method to use: `password`, `storage_state`, or
   `none` (public route).
4. Ask for a **temporary or fake** account, or a Playwright
   `storageState` path. Do not invent credentials. Do not copy a user
   from another product.
5. Write gitignored `docs/review-impact/demo-auth.json`. Env
   `DEMO_EMAIL` + `DEMO_PASSWORD` is an alternative if they already
   export those.
6. Stop if they refuse — you cannot record an authenticated flow
   without this.

Reuse the file on later runs in the same repo. Re-ask only if login
fails.

## 1. Claim

1. Resolve IID from `#213`, `213`, or the issue URL.
2. `gitlab__get_issue` — skip if closed/merged unless the user insists.
3. If another human is implementing (assignee + in-progress + a recent
   claim note that is not you), **warn** and stop unless they said force.
4. Promote the card to in-progress using **this project's** board labels
   (`docs/team-boards.md` when it exists). Assignee = `gitlab__whoami`.
5. Post:

```markdown
**Claimed**

I've claimed this issue and am implementing it now so we avoid duplicate work.
```

WIP: at most one in-progress issue per person.

## 2. Branch + stack

- Branch from updated default branch: `feat/<iid>-<slug>` or
  `fix/<iid>-<slug>`.
- Start the local stack if the ticket is UI-reproducible.

## 3. Before video (when the bug is visible in the UI)

Record the wrong behavior **before any code change**.

1. Write a gitignored runner
   `docs/review-impact/<iid>-<slug>/record-before.mjs`.
   Import `login` / `recordTicket` / `clickHuman` / `typeHuman` from
   `$SKILL_DIR/../ticket-demo-video/scripts/record-live-ui.mjs` (or the
   sibling install of `ticket-demo-video`) and `labelIssueArea` from
   `$SKILL_DIR/scripts/label-issue-area.mjs`.
2. At the climax, `labelIssueArea(page, { kind: 'before', label, … })`
   so the **smallest widget** that shows the bug is boxed in red
   (`#dc2626`) with an `ISSUE:` badge. Dim the rest of the page.
3. Prefer **host** Playwright against published localhost ports. Auth
   emails often embed `localhost` in `redirect_to`; Docker DNS breaks
   that path.

```bash
export PLAYWRIGHT_BASE_URL=http://localhost:3000
export MAILPIT_URL=http://127.0.0.1:54324   # if the flow uses inbox links
node docs/review-impact/<iid>-<slug>/record-before.mjs
ffmpeg -y -i docs/review-impact/<iid>-<slug>/before.webm \
  -c:v libx264 -pix_fmt yuv420p -an \
  docs/ticket-demos/<iid>-<slug>-before.mp4
```

Keep the mp4 local. **Do not `git add` it.** When the ticket ships,
`gitlab__upload_markdown` and paste the returned markdown into the MR
description.

4. Extract a frame ~1s before the end. If the badge says
   `(region not found)` or the outline is on the wrong widget, fix the
   locator and re-record. Do not publish a miss.
5. If it is not UI-reproducible, say so and skip the clip.

### Highlight rules

- Box the row / card / alert / form, not the whole page.
- Pin the badge **on screen** (above the box, or overlay its top-left).
  Never park it below the viewport.
- Spotlight with a fixed hole + `box-shadow`, not `clip-path: evenodd`
  (that slashes a triangle across the frame).
- Do not assume `[role="alert"]`. Product errors are often a `<div>` /
  `<p>`. Mark the node (`data-issue-row`) then pass `selector`.
- Use the same selector family in the after clip so the region turns green.

### UI that lies in Playwright

- React-controlled hidden inputs (`value={state}`) ignore DOM `.value`
  writes. Click the real control, then `waitForFunction` until the
  submitted field matches.
- Inventory / leftover-data demos need a **fresh** entity. Prior runs
  can make an “illegal” action legal.
- After submit, race the error vs navigation. If a path that should
  reject succeeds, throw — the running API is not the fix.

### Running code vs git branch

Bind-mounted Compose/dev servers pick up files, but the process may
still serve the previous tree. After checkout:

- Frontend: clear the build cache (e.g. `apps/web/.next`) and restart
- API: restart and wait for health
- Copy local demo mp4s aside **before** `git checkout -f`

## 4. Implement

Keep the change scoped to the issue **Done when**. No drive-by
refactors. Follow the repo’s money / typing / lint rules.

## 5. Gates (must pass before “fixed”)

Touched apps only, via that repo’s quality commands. A single unrelated
pre-existing failure does not block if you verified it is outside the
diff. Do not call the ticket fixed if **your** tests or typecheck fail.

## 6. After video

Same path as the before clip (`record-after.mjs`), same user, **same
region**, `kind: 'after'` (green `#16a34a`, `FIXED:` badge). Restart the
stack so the process is serving **this** branch. Verify the climax
frame. Upload both clips onto the MR — do not commit them.

## 7. Report

- Issue IID + title + URL
- Clickable before/after (MR description uploads, not git)
- What region was boxed
- Gates run and outcome
- Branch name
- Then stop, or continue to the next IID **only if** the user listed
  more tickets and this one is fixed.

## Do not

- Implement several tickets in one mixed branch unless the user asked
  to ship a reviewed batch in one MR
- Skip the before video when the bug is visible in the UI
- Treat a screenshot as verification
- Push or merge unless the user asks
- Commit scratch webms or demo mp4s
- Publish a clip whose badge says `(region not found)`
- Invent or hard-code a product login. Ask, then persist what they gave you.
