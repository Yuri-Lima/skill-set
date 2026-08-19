# Playbook: software, repositories, and running systems

## Where the primary source actually is

| Claim about | Primary source | Not the primary source |
|---|---|---|
| What the code does | The file, at a specific commit | The README, the architecture doc, a comment |
| Counts (routes, tables, endpoints, services) | `find`/`grep`/`wc` on the tree, or the generated manifest | Any number written in prose |
| What is deployed | The platform's API or console | The repo, a config file, a changelog |
| Schema | The database (`information_schema`, `\dt`, a migration run) | The ORM models, the migration folder |
| Dependencies | The installed tree (`node_modules`, `pip freeze`, `go list -m all`) | The manifest (`package.json`, `requirements.txt`) |
| "This breaks the build" | A build you ran | Reading the linter config or the style guide |
| Test coverage of a behavior | The test that exercises it, and its result | A test file named after it |
| Whether a job runs | The scheduler's own tables/logs and the last run's output | The cron definition in source control |

The recurring shape: **source control describes intent; the running system holds
the fact.** A migration file is a request that a schema change happen; only the
database knows whether it did.

## Verifying counts

Show the command and the raw number, then any adjustment:

```bash
find src/routes -name "*.tsx" | wc -l     # 28
# minus __root.tsx and _authenticated.tsx (layouts, not routes) → 26
```

Cross-check against a *generated* artifact where one exists — a route manifest, an
OpenAPI spec, a build output. A hand-count and a generated count agreeing is much
stronger than either alone, and when they disagree the disagreement is the finding.

Watch for definition drift: "26 routes" and "28 route files" are both true and
mean different things. State which you counted.

## Reproducing behavioral claims

Do it in a throwaway copy so verification cannot damage anything:

```bash
git worktree add /tmp/verify HEAD --detach
cd /tmp/verify && <install> && <build/test>
# ... then always:
git worktree remove --force /tmp/verify
```

Equivalents elsewhere: a scratch branch, a container, a copied database, a
sandbox tenant, a dry-run flag.

Three traps that turn a "verified" run into a false result:

**Your environment is not their environment.** Before reporting "the build is
broken", separate *broken at HEAD* from *broken on this machine*. Private
registries, missing credentials, platform differences, and cached state all
produce failures that have nothing to do with the code. Say which one you found —
and if it is environmental, that is still often worth reporting, because it will
hit the next person who clones.

**Exit codes lie.** Installers and build tools do exit 0 after partial failures.
Never take the exit code as the result: check that the artifact exists. Did
`node_modules/<the-package>/` actually get created? Is the output file there and
non-empty? Does the built binary run?

**A passing test is not a covering test.** A green suite proves the tests that
exist passed, not that the behavior is correct. When the claim is "X is tested",
find the assertion that would fail if X broke.

## Dependency and supply-chain claims

The manifest states a range; the lockfile states a resolution; `node_modules`
states reality. All three routinely disagree.

Read the lockfile's resolved URLs, not just versions — packages pinned to private
or internal registries fail for anyone outside that network, and the failure
looks like a mysterious build error rather than an access problem.

## Deployment and live-state claims

"It's deployed", "the flag is on", "the job is running", "that service is down" —
these need the platform, not the repo. Without credentials, they are `[U]`, and
saying so is far more useful than a confident guess.

When you cannot reach the platform, name the exact command that would settle it,
so whoever has access can close the gap in one step:

> `[U]` — needs `select * from cron.job` against the production database.

## Documentation-versus-code drift

The single most productive check in a mature repository:

```bash
git log --oneline <last-doc-update>..HEAD -- <code paths> | wc -l
git diff --stat <last-doc-update>..HEAD -- docs/ README.md
```

If the code moved and the docs did not, every figure in those docs is stale by
construction — and you know it without checking any figure individually.

Also worth a minute: does the doc reference files, routes, tables, or flags that
no longer exist? `find`/`grep` for each named thing. Dead references accumulate
silently and are trivially disproved.
