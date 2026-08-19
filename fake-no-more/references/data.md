# Playbook: data, numbers, and reported figures

Covers datasets, spreadsheets, dashboards, financial and operational reporting —
anything where the claim is a quantity.

## Where the primary source actually is

| Claim about | Primary source | Not the primary source |
|---|---|---|
| A count or total | The query against the system of record, with its date | A dashboard tile, a slide, a prior report |
| A metric's definition | The computation that produces it | Its label |
| A trend | The full series, including the periods you're not showing | Two endpoints |
| A financial figure | The reconciled statement or the ledger | A working spreadsheet |
| "Users/cases/items are N" | The query, plus the filter that defines who counts | A number someone said in a meeting |

## Every number carries four things

A quantity without these is not verifiable, only repeatable:

1. **Definition** — what is being counted, and what is excluded
2. **As-of** — the moment the count was taken; live systems move
3. **Source** — the system it came from, not the report that displayed it
4. **Filter** — the exact predicate; "active users" hides an enormous amount

> `[V]` 380 open cases — `select count(*) from cases where status not in
> ('closed','archived')`, run 2026-08-19 14:20. Excludes the 77 records with no
> identifier, which never migrated.

That exclusion clause is usually where the real story is.

## Recomputing, not re-reading

To verify a reported figure, recompute it from the underlying rows. Reading the
same number off a second dashboard verifies nothing — both tiles typically draw
from the same query.

When you recompute and get a different answer, do not silently prefer yours.
Reconcile: different filter, different as-of, different definition, or a genuine
error. Which one it is *is* the finding, and reporting "the numbers disagree"
without saying why is not much better than not checking.

## The checks that pay for themselves

**Do the parts sum to the total?** Category breakdowns that don't reconcile to
the headline mean a missing category, a double-count, or overlapping buckets.
Costs seconds, catches real errors.

**Is the magnitude plausible?** Compare against a known anchor — headcount,
population, prior period, physical limits. Impossible numbers are usually unit
errors or a misplaced decimal, and spotting that beats a full verification.

**Where does the denominator come from?** In any ratio, the denominator is
load-bearing and frequently unexamined. A percentage computed over a stale or
differently-filtered base is wrong even when the numerator is perfect.

**Does the total change when nothing should have changed it?** A "static"
historical figure that moves between reports means the query is not
as-of-anchored — every derived figure inherits that instability.

## Survivorship and selection

Before reporting any aggregate, ask what never made it into the dataset. Records
that failed to migrate, rows dropped by a join, respondents who didn't answer,
cases closed before the window opened. These are invisible in the output and
decisive for the conclusion.

If you know records were excluded, report the exclusion beside the figure —
a count of 380 with 77 known-missing is a different fact from a count of 380.

## Staleness

Note the as-of, and note the refresh cadence separately. A dashboard reading
"updated 2 minutes ago" may be showing a pipeline that last succeeded four days
ago; the timestamp on the page is a claim about the page, not about the data.

Where a pipeline can fail silently, check its last successful run before trusting
the figure — the same "success signal versus artifact" problem as in software.

## Presenting uncertainty honestly

Give a range or an explicit uncertainty when the underlying data does not support
a point estimate. A number stated to five significant figures from a source that
only supports two is a false precision claim — and readers reasonably treat
precision as a signal of confidence.

When the figure is genuinely uncertain, say what would reduce the uncertainty:

> `[U]` Somewhere between 200 and 250 pending items — the two systems of record
> disagree and neither has been reconciled since the migration. A join on the
> shared identifier would settle it.
