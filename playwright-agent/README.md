# Playwright agent

A small program that clicks and types in a **real browser**, the way a
person would: “the Sign in button”, “the Email field”, “the card that
says Next due”.

You (or an AI assistant) name the thing. **Playwright** finds it,
waits until it is ready, and clicks it. If it cannot find exactly one
match, it stops. It does not guess.

## What problem this solves

Typical “AI browser” tools dump a map of the page (`@e1`, `@e2`, …)
and let the model pick a number. That number is only valid for that
instant. After the page changes, `@e12` is a different button.

This tool never uses those numbers. You describe the control:

| You say | The tool does |
| --- | --- |
| the button named **Sign in** | `getByRole('button', { name: 'Sign in' })` |
| the field labeled **Email** | `getByLabel('Email')` |
| the test id **cash-on-hand** | `getByTestId('cash-on-hand')` |
| the text **Next due**, then the card around it | text + `closest` card |

Same words tomorrow, same control tomorrow.

## Install

From this folder (after you cloned [skill-set](https://github.com/Yuri-Lima/skill-set)):

```bash
cd playwright-agent
npm install
npx playwright install chromium
```

`./install.sh --global` in the repo root also copies this folder next
to your other skills (`~/.grok/skills/playwright-agent`, and the
Claude / Cursor copies). Run `npm install` in that copy if you want
the CLI from there.

Need Node 18+.

## Talk to it

Every command prints JSON. `ok` means it worked. Anything else is a
real stop — read the message, do not invent a CSS selector.

```bash
CLI="node src/cli.mjs"          # from this folder
# or: node ~/.grok/skills/playwright-agent/src/cli.mjs

$CLI open https://example.com --headed    # show the window
$CLI click --by role --role button --name "More information..."
$CLI shot /tmp/example.png
$CLI close
```

`--headed` shows Chrome. Omit it to run in the background.

The browser stays open between commands (one “session”). Close it
when you are done.

### Name a control

| Flag | Meaning | Example |
| --- | --- | --- |
| `--by role --role button --name "Sign in"` | A button (or link, checkbox…) by its visible name | Login |
| `--by label --name Email` | A field by the label next to it | Forms |
| `--by testid --name cash-on-hand` | A mark the app put on the widget | Phoenix cards |
| `--by text --name "Next due" --closest '[data-slot="card"]'` | Find the words, box the card that contains them | Bug videos |
| `--by css --selector "#email"` | Last resort, only if you already know a unique selector | Old demo-auth files |

If two things match, the tool returns `ambiguous` and a short list of
candidates. Pick one of **those** names. Do not click the first match.

### Check that it worked

```bash
$CLI assert visible --by text --name "1 item left"
$CLI assert url "**/dashboard"
$CLI state          # current URL and title
```

### Save the session as a test

After a successful walkthrough:

```bash
$CLI codegen /tmp/login.spec.ts
```

That file is a normal Playwright test (`getByLabel`, `getByRole`,
`expect`). You can re-run it later with **no AI**.

## Same use cases as the other skills

These are the flows this repo already uses.

### 1. Walk through a public page

“Open the site, click the named button, take a screenshot.”

```bash
node src/cli.mjs open https://demo.playwright.dev/todomvc --headed
node src/cli.mjs fill --by placeholder --name "What needs to be done?" "Buy milk"
node src/cli.mjs press --by placeholder --name "What needs to be done?" Enter
node src/cli.mjs assert visible --by text --name "Buy milk"
node src/cli.mjs shot /tmp/todo.png
node src/cli.mjs codegen /tmp/todo.spec.ts
node src/cli.mjs close
```

Ask Grok: `/playwright-agent` then “add a todo on the Playwright
TodoMVC demo and save a spec”.

### 2. Sign in for a ticket demo

The demo video skill logs in **before** it records, so the clip never
shows the login screen. That login now goes through this engine.

In `docs/review-impact/demo-auth.json` prefer labels (what a person
sees) over `#email`:

```json
{
  "method": "password",
  "loginPath": "/login",
  "email": "temporary-demo@example.test",
  "password": "replace-me",
  "emailLabel": "Email",
  "passwordLabel": "Password",
  "submitName": "sign in"
}
```

`emailSelector` / `passwordSelector` still work if that is all the
app has. The skill’s `login()` calls `resolveTarget` — if the button
is missing or there are two, login **throws** instead of clicking the
wrong one.

### 3. Box the bug for a before/after video

The silent red/green pair must outline the **same widget** twice. The
highlight helper no longer does `querySelector` and hopes.

In the gitignored recorder:

```js
import { labelIssueArea } from '../../claim-fix-ticket/scripts/label-issue-area.mjs';

await labelIssueArea(page, {
  kind: 'before',                 // red. Use 'after' for green.
  label: 'ISSUE: next due still 12 Aug',
  text: /next due/i,
  closest: '[data-slot="card"], tr, [role="alert"]',
});
```

Or a stable test id, if the product has one:

```js
await labelIssueArea(page, {
  kind: 'after',
  label: 'FIXED: next due is 12 Sep',
  testId: 'loan-next-due',
});
```

If the engine cannot find **exactly one** region, the badge says
`(region not found)` and you fix the locator — you do not publish
that clip.

### 4. Reuse a control from a script you already have

When a Playwright `page` is already open (the video skills do this):

```js
import { resolveTarget, assertResolved } from '../../playwright-agent/src/index.mjs';

const email = await resolveTarget(page, { by: 'label', name: 'Email' });
assertResolved(email, 'login email');
await email.locator.fill('user@test.com');
```

Do not add a new `page.locator('#whatever')` in those skills. Name
the control and let this module resolve it.

## When it says no

| Status | Meaning | What you do |
| --- | --- | --- |
| `ok` | Exactly one match; action or check passed | Continue |
| `not_found` | Nothing matched | Use a different **name** (label, role, test id). Do not invent CSS. |
| `ambiguous` | Two or more matches | Pick one entry from `candidates`. Narrow with `--name`, `--closest`, or a test id. |
| `verify_failed` | The click ran, but the check did not | The page is not in the state you expected |

It will not wait for `networkidle` (a flaky “wait until the network
is quiet” setting). Playwright’s own waiting on the locator is enough.

## Ask the assistant

After install, in Grok / Claude / Cursor:

```
/playwright-agent
```

or “click the Sign in button with the playwright agent”.

The skill file (`SKILL.md`) is the short policy for the model. This
README is the human guide.

## Keep the official Playwright agents in sync

Microsoft ships three **prompt** files (planner, generator, healer)
inside Playwright. They change when Playwright is upgraded. This
folder vendors a copy so we can see drift:

```bash
node scripts/check-upstream.mjs --check
node scripts/check-upstream.mjs --write --tag v1.56.0   # after you review
```

Docs: [playwright.dev/docs/test-agents](https://playwright.dev/docs/test-agents).
We copy their **rules** (live execute, then write the test from
Playwright’s log). We do not copy their “click `@e12`” loop.

## Tests

```bash
npm test
```
