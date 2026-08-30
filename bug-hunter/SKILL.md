---
name: bug-hunter
description: >-
  Onboard a repo (scan + grill) into a named project hunter, then hunt
  bugs the way that repo actually breaks. First questions are the real
  project name and slug; every write goes under that name. Use when the
  user runs /bug-hunter, or says "bug hunter", "hunt bugs", "onboard the
  hunter", "learn this repo", or "generic bug hunter".
---

# Bug hunter

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

One skill, three modes. Pick from the user text; if they only ran
`/bug-hunter`, choose:

| State | Mode |
| --- | --- |
| no `.bug-hunter/identity.md` | **learn** (identity first) |
| identity, no `.bug-hunter/knowledge.md` | **learn** (grill) |
| identity + knowledge, user said `learn` | **learn** (re-grill, slug stays) |
| identity + knowledge, user said `status` | **status** |
| identity + knowledge | **hunt** |

Until identity exists you may write **only** `.bug-hunter/identity.md`.

The hunter’s public name is the display name the human gave. The slug
owns `~/.<slug>-agents/`, `<slug>-*.md` seeds, `.<slug>-new-findings.md`,
and the ticket tag `by grok_<slug>_hunter` (hyphens → underscores).

## learn

Follow [`references/specialist.md`](references/specialist.md). Summary:

1. `node "$SKILL_DIR/scripts/probe-project.mjs"` — print the JSON.
2. `node "$SKILL_DIR/scripts/project-id.mjs"` — show name/slug suggestions.
3. Ask display name, then confirm slug. Validate with
   `node "$SKILL_DIR/scripts/project-id.mjs" --validate <slug>`.
4. `node "$SKILL_DIR/scripts/write-knowledge.mjs" identity --dir . --name NAME --slug SLUG`
5. If `~/.<slug>-agents/<slug>-stack.md` already exists, offer
   `bash "$SKILL_DIR/scripts/import-existing.sh" --dir . --name NAME --slug SLUG`
   instead of a blank grill.
6. Grill in the batches in `specialist.md`. Write `answers.json`, then
   `write-knowledge.mjs from-answers`.
7. `bash "$SKILL_DIR/scripts/seed-worktree.sh"`
8. **Stop.** Speak as the **{name} hunter**. Do not hunt unless they asked.

Re-learn keeps the slug. Merge: keep `[V]` facts the new probe still
supports; re-ask only drifted or unanswered sections.

## hunt

If identity or knowledge is missing, switch to **learn**. Do not hunt.

1. Read `.bug-hunter/identity.md`, `knowledge.md`, `hunt-profile.md`,
   and `hunt-brief.md` (empty brief = whole profile in season).
2. Read `~/.<slug>-agents/lessons.md` and `hunted-ledger.md` if they exist.
3. Load [`references/orchestrator.md`](references/orchestrator.md) and
   [`references/hunter.md`](references/hunter.md). Substitute
   `{{NAME}}` `{{SLUG}}` `{{FINDINGS}}` `{{HUNTER_FILE}}`.
4. Load the adapter that matches knowledge:
   [`references/adapters/tickets.md`](references/adapters/tickets.md),
   [`references/adapters/pull-requests.md`](references/adapters/pull-requests.md).
5. Seed if the `{slug}-*.md` files are missing:
   `bash "$SKILL_DIR/scripts/seed-worktree.sh"`
6. Run the orchestrator loop from that prompt. Headless equivalent:
   `bash "$SKILL_DIR/scripts/run-hunt.sh"`

Hunt only grounds in `hunt-profile.md`. Check lessons before filing.
Hunters never run git. End a finished hunt with `HUNT COMPLETE`.

## status

Print, do not hunt:

- name, slug, agent home
- whether knowledge / profile / brief exist
- ledger line count and lessons count
- hunt branch vs current branch (if knowledge names one)
- missing publish tokens named in knowledge

```bash
node "$SKILL_DIR/scripts/probe-project.mjs" --status
```

## Do not

- Write ledger, lessons, prompts, or knowledge before identity exists
- Hard-code a product name, ticket host, package manager, or port in a
  prompt you generate — those live in knowledge
- Hunt a ground the profile does not list
- Fetch open tickets to build a work list
- Run a command knowledge marks forbidden
- Start a hunt in the same turn as a first-time learn unless they asked
