# Specialist — onboard a repo

The agent follows this when `/bug-hunter` has no identity or knowledge, or when the user asked `learn`. Do not start a hunt from this file.

## Identity is blocking

Until `.bug-hunter/identity.md` exists you may write **only** that file.

1. Run `node "$SKILL_DIR/scripts/probe-project.mjs"` and print the JSON.
2. Run `node "$SKILL_DIR/scripts/project-id.mjs"` (same cwd) and show the suggested names and slugs.
3. Ask the display name. Then ask them to confirm the slug (`[a-z][a-z0-9-]{0,31}`).
4. Write identity:

```bash
node "$SKILL_DIR/scripts/write-knowledge.mjs" identity \
  --dir . --name "<Display>" --slug "<slug>"
```

That creates `.bug-hunter/identity.md` and `~/.<slug>-agents/`. Nothing else yet.

If `~/.<slug>-agents/<slug>-stack.md` already exists, offer import instead of a blank grill:

```bash
bash "$SKILL_DIR/scripts/import-existing.sh" --dir . --name "<Display>" --slug "<slug>"
```

## Grill (after identity)

Ask in batches. Do not re-ask a fact the probe already answered unless they reject it. Every answer you write later must be marked `[V]`, `[R]`, or `[I]`.

Collect an `answers.json` with this shape (omit keys they skipped):

```json
{
  "packageManager": "yarn",
  "testOne": "yarn workspace @scope/name test",
  "typecheck": "tsc --noEmit -p packages/core/tsconfig.json",
  "e2e": "",
  "forbidden": ["yarn build"],
  "ports": [
    { "name": "API", "source": "path/to/.env KEY", "value": "3020", "exclusive": true }
  ],
  "start": ["..."],
  "huntBranch": "acme-hunter",
  "baseBranch": "main",
  "terminalBranch": false,
  "fixFrom": "main",
  "prHost": "github",
  "ticketHost": "none",
  "autoPublish": false,
  "houseRules": [],
  "hotSpots": ["skipped-tests", "swallowed-errors", "leaks"],
  "outOfSeason": ["generated/", "vendor/"],
  "notBugs": [],
  "lessonQuery": ""
}
```

`hotSpots` may only include: `skipped-tests`, `concurrency`, `swallowed-errors`, `money`, `leaks`, `todos`, `sibling-plugins`. Show a batch only for categories the probe hinted, plus any the human adds.

`prHost` / `ticketHost`: `github` | `gitlab` | `gitea` | `youtrack` | `none`.

Batches, in order:

1. Confirm scan (package manager, languages, layout).
2. Commands (one-package test, typecheck, e2e, forbidden).
3. Runtime (ports, start/stop, exclusive vs shared).
4. Git (hunt branch, base branch, terminal-branch?, fix/* from where).
5. Publish (PR host, ticket host, auto-publish).
6. Domain hot spots (only hinted categories).
7. House rules (framework musts).
8. Out of season + not-a-bug seeds (these become the first lessons).
9. Learning (how a rejected ticket becomes a lesson, or `none`).

Write:

```bash
node "$SKILL_DIR/scripts/write-knowledge.mjs" from-answers \
  --dir . --probe /tmp/probe.json --answers /tmp/answers.json
```

Then seed the worktree:

```bash
bash "$SKILL_DIR/scripts/seed-worktree.sh"
```

Stop. Speak as the **{name} hunter**. List `[V]` vs `[R]`. Tell them `/bug-hunter` now hunts. Do not hunt in the same turn unless they asked.
