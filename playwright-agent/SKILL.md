---
name: playwright-agent
description: >
  Drive a real browser with Playwright locators, not snapshot refs or
  invented CSS. Use when the user needs deterministic UI clicks, form
  fills, screenshots, ticket-demo login, claim-fix highlights, or a
  recorded Playwright spec. Use when they run /playwright-agent or say
  "browser agent", "playwright agent", "click this button", or
  "record a locator spec".
---

# Playwright agent

`$SKILL_DIR` is this folder. The CLI is `$SKILL_DIR/src/cli.mjs`.

The model names an **intent + locator contract**. Playwright resolves,
waits, and fails closed. Do not pick `@e12`. Do not invent CSS from an
HTML dump. Do not use `networkidle`.

## Locator contract

```json
{ "by": "role", "role": "button", "name": "Sign in" }
{ "by": "label", "name": "Email" }
{ "by": "testid", "name": "cash-on-hand" }
{ "by": "text", "name": "Next due", "closest": "[data-slot=card]" }
```

`by` order when omitted (`preferTestId`, default for Phoenix): testid,
css, role, label, placeholder, text. Use `--strategy preferUserFacing`
to try role/label first.

Outcomes: `ok` | `not_found` | `ambiguous` | `verify_failed`. On
`ambiguous`, choose only from `candidates[].generated`. Never `.first()`.

## Commands

```bash
node "$SKILL_DIR/src/cli.mjs" open <url> [--headed] [--seed auth.json]
node "$SKILL_DIR/src/cli.mjs" click --by role --role button --name "Sign in"
node "$SKILL_DIR/src/cli.mjs" fill --by label --name Email "user@test.com"
node "$SKILL_DIR/src/cli.mjs" assert visible --by text --name "1 item left"
node "$SKILL_DIR/src/cli.mjs" assert url "**/dashboard"
node "$SKILL_DIR/src/cli.mjs" resolve --by label --name Email
node "$SKILL_DIR/src/cli.mjs" shot [path]
node "$SKILL_DIR/src/cli.mjs" codegen [out.spec.ts]
node "$SKILL_DIR/src/cli.mjs" state
node "$SKILL_DIR/src/cli.mjs" close
```

Stdout is JSON. Session default is `default` (`--session name`).

From a Playwright `page` already in hand (ticket-demo / claim-fix):

```js
import { resolveTarget, assertResolved, highlightRegion } from
  '../../playwright-agent/src/index.mjs';
```

## Do not

- Snapshot then click a ref
- Heal a miss by guessing a new CSS string
- Call `waitForLoadState('networkidle')`
- Paint a highlight on the first of several matches
