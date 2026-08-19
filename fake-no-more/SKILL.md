---
name: fake-no-more
description: Verify factual claims against primary sources before they ship, and mark every claim with where it came from. Use whenever the user asks to audit, fact-check, verify, validate, double-check, or sanity-check something; whenever they push back on a claim ("are you sure?", "is that actually true?", "did you really check?", "prove it"); and whenever you are producing a deliverable other people will act on — a report, overview, README, status summary, audit, migration plan, research brief, or case summary. Also use when a previous answer's numbers, dates, states, or citations need confirming before someone relies on them. Domain-agnostic — works for code and repositories as well as legal, research, financial, medical, and operational material.
---

# Fake No More

## The failure this prevents

Almost nobody fabricates outright. The common failure is quieter: a claim that is
true *in a document* gets restated as true *in the world*, and the provenance
falls off in transit.

A number read in an architecture doc becomes "the system has 43 tables." A count
that a README asserts becomes "there are 29 services." Each restatement is
honest and each one is a little more confident than the last, until someone
plans a migration around a number that nobody has actually observed since
whenever that doc was written.

The cost never lands on the person who dropped the provenance. It lands on
whoever acts on it.

## The rule

**Every factual claim ships with its provenance.**

Unverified claims are allowed — most of what anyone knows is secondhand, and
demanding first-hand verification of everything would stop all work. What is not
allowed is an unverified claim that *looks* verified because nothing marks it.

The reader must be able to tell, without asking, which claims you checked and
which you inherited.

## Provenance marks

| Mark | Meaning | What you owe the reader |
|---|---|---|
| `[V]` | **Verified** — you observed it yourself, this session | The exact command, query, file+line, or observation, in the appendix, so they can repeat it |
| `[R]` | **Reported** — a source asserts it; you did not confirm it | The source, and its date |
| `[I]` | **Inferred** — you derived it from `[V]` inputs | The derivation, briefly |
| `[U]` | **Unverifiable here** — you tried, or determined you can't | Why, and what access would settle it |

`[R]` is not an admission of laziness. A properly attributed `[R]` with a date is
often the correct and sufficient answer. The mark exists so the reader can decide
whether to trust it, not to shame you for using it.

If a deliverable ends up almost entirely `[R]`, that is itself the finding —
report it plainly rather than dressing it up.

## Method

### 1. Inventory the claims

Extract every **falsifiable** statement — one that could be shown wrong by
observation. Counts, dates, versions, names, states ("X is enabled", "Y is
down"), causal claims ("A breaks B"), and existence claims ("there is a Z").

Not claims, and not your business here: recommendations, priorities, opinions,
plans, and value judgments. Verifying those is a category error, and padding an
audit with them hides the real work.

### 2. Rank by blast radius, not by ease

Verify in this order:

1. Claims someone will act on irreversibly — a delete, a deploy, a filing, a
   payment, a diagnosis.
2. **Load-bearing claims** — ones other claims rest on. If the count is wrong,
   every ratio built from it is wrong too. These are worth disproportionate effort.
3. Claims that are cheap to check. Cheap and high-stakes first; cheap and
   decorative last.

Decorative claims that nobody will act on can be left at `[R]`. Say that you
left them there. Silent triage reads as full coverage.

### 3. Walk to the primary source

**A document repeating another document is not evidence.** Neither is a summary,
a cached answer, a memory, or your own earlier message in this conversation.

Go to the thing itself: the filesystem, the database, the running system, the
signed original, the published dataset, the statute. If you cannot reach it, the
claim is `[U]` — not `[V]` with a shrug.

Watch for the circular case, which is extremely common: doc A cites doc B, and
doc B cites doc A. Two sources, one origin, zero evidence.

### 4. Reproduce claims about behavior

Claims of the form *"X breaks Y"*, *"this fails"*, *"the process rejects Z"*,
*"the rule prevents W"* are claims about **what happens**. Reading the code, the
policy, or the contract tells you what someone *intended* to happen.

These need a run, not a reading — and the run belongs in a scratch copy
(a worktree, a branch, a sandbox, a photocopy, a test account) so that verifying
a claim cannot damage the thing the claim is about.

This step routinely inverts the expected answer. A rule that everyone believes is
enforced is frequently not enforced any more, and only an attempt reveals it.

### 5. Declare the verification boundary — before the findings

State what you could reach and what you could not, up front:

> Verified against: the repository at commit `abc1234`, and a clean build in an
> isolated worktree.
> **Not reachable:** the production database and the deployed services. Every
> number about live state below is `[R]` from `docs/architecture.md`, dated
> 2026-08-15, and I could not confirm any of it.

Put this before the findings, not in a footnote. A reader who stops after the
first paragraph should already know how much to trust the rest.

## What counts as evidence

| Counts | Does not count |
|---|---|
| A command and its actual output | "I checked" / "I verified" with nothing attached |
| `file.ts:142` — a specific, resolvable locator | "somewhere in the auth module" |
| A query and its result set | A number quoted from a doc, README, or ticket |
| A reproduction, with the steps to repeat it | Reading the code that ought to do it |
| A quote plus its locator (page, clause, timestamp) | A paraphrase from memory |
| A screenshot or artifact you actually inspected | A success signal claiming the artifact exists |

The test for `[V]`: **could a skeptical stranger repeat this and get the same
result?** If your evidence only works because you already believe the conclusion,
it isn't evidence.

## High-yield checks

These are cheap and catch a surprising share of real errors. Run them early.

**Internal contradiction.** Does the source disagree with itself? A headline
figure that its own table contradicts, a total that doesn't match its parts, a
summary that outruns its own body. This needs no external access at all and is
often the fastest disproof available.

**Staleness by construction.** When was this source last updated, relative to the
thing it describes? If the underlying system changed 24 times and the doc changed
zero times, every number in it is at least 24 changes old — you know it is stale
without checking a single figure.

**Success signal versus artifact.** A green check, an exit code 0, a "completed"
status, an approval stamp — each is a *claim* that something happened, not the
thing itself. Check for the artifact: the file, the row, the signature, the
built output. Tools do report success while failing.

**Existence.** The cheapest check of all, and it fails more often than anyone
expects: does the named thing exist at all? The route, the table, the clause, the
account, the person. Long-lived docs accumulate references to things that were
removed, renamed, or never built.

**Order of magnitude.** Before verifying a number precisely, ask whether it is
even plausible. Impossible numbers are usually unit errors or a decimal in the
wrong place, and spotting that is faster than a full check.

## Output format

### Inline

Attach the mark to the claim, closest to the number or statement:

> The repository has **26 routes** `[V]` and **28 deployed functions** `[R]`
> (`docs/architecture.md`, 2026-08-15 — not independently confirmed).

Keep it light. One mark per claim, no restating the mark in prose.

### Appendix

End the deliverable with a reproducible appendix. This is what separates an audit
from an assertion — it lets the reader re-run your work instead of trusting it.

```markdown
## Verification appendix

Verified against: <what — repo at commit / dataset version / signed original>
Date: <when>
Not reachable: <what you could not check, and what access would settle it>

| # | Claim | Mark | Evidence |
|---|---|---|---|
| 1 | 26 routes | V | `find src/routes -name "*.tsx" \| wc -l` → 28, minus 2 layout files |
| 2 | Build succeeds at HEAD | V | Clean worktree, `bun install && bun run build` → exit 0, 4.07s |
| 3 | 43 tables | R | `docs/architecture.md` §4, dated 2026-08-15; needs DB access |
| 4 | Route `/repasses` exists | U | **Disproved** — `find . -iname "*repasse*"` returns nothing |
```

Adapt the columns to the domain — a legal review's evidence column holds clause
and page references, a data review's holds queries and row counts. The structure
holds: claim, mark, and something a stranger could repeat.

### Scale the format to the deliverable

A one-paragraph answer does not need an appendix table — inline marks and a
sentence naming the boundary are enough. Reserve the full appendix for
deliverables someone will act on or circulate. Ceremony that outweighs the
content makes the discipline look like theater and trains people to skip it.

## When verification contradicts something you said earlier

State the correction plainly, once, and continue:

> Correction: I said 29 functions earlier. The repository has 28 — the source I
> took it from contradicts its own table.

No apology paragraph, no re-litigating how it happened, no tallying your errors.
The reader needs the corrected fact and a reason to trust the new number. Being
visibly hard on yourself is not the same as being accurate, and it costs the
reader attention that belongs on the finding.

The same applies to claims made by a source, a colleague, or another agent:
report what you found without editorializing about the source's reliability.

## Domain playbooks

Load the one that matches the material — each lists where the primary sources
actually live and the failure modes specific to that domain.

- **`references/software.md`** — repositories, builds, dependencies, deployments,
  code metrics, "this breaks that" claims
- **`references/documents.md`** — legal, research, policy, and reference material;
  citations, quotations, versions, and signatures
- **`references/data.md`** — datasets, spreadsheets, dashboards, and reported
  figures; provenance, aggregation, and staleness

## What this skill is not

It is not a license to refuse work until everything is proven. Most tasks have a
handful of load-bearing claims and a long tail of ordinary ones; verify the
former, attribute the latter, and deliver.

It is also not a reason to hedge everything. A verified claim should be stated
flatly and confidently — that is the entire payoff for having checked it. Hedging
a `[V]` claim wastes the work.
