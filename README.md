# skill-set

Agent skills I reuse across Claude Code, Cursor, and Grok.

| Skill | Invoke | What it does |
| --- | --- | --- |
| [`fake-no-more`](fake-no-more/) | `/fake-no-more` | Verify factual claims against primary sources and mark every claim with where it came from. |
| [`claim-mr`](claim-mr/) | `/claim-mr` | Post a short “claimed for review” note on a GitHub, GitLab, or Gitea PR/MR so nobody double-starts the same review. |
| [`claim-fix-ticket`](claim-fix-ticket/) | `/claim-fix-ticket` | Claim a GitLab issue, record a highlighted **before** UI video, implement, run gates, record the same region **after**. |
| [`ticket-demo-video`](ticket-demo-video/) | `/ticket-demo-video` | Spoken Eve + live UI walkthrough, length = the explanation. Attach the mp4 to the MR; do not commit it. |
| [`explain-implementation-video`](explain-implementation-video/) | `/explain-implementation-video` | Two-act film: Eve narrates locked decisions on a studio board, then a product recording proves the result. |
| [`explain-in-browser`](explain-in-browser/) | `/explain-in-browser` | Mid/long explanations open as a readable HTML page; the terminal only gets a short teaser. |
| [`playwright-agent`](playwright-agent/) | `/playwright-agent` | Click and type in a real browser by **name** (Sign in, Email, a test id). Shared by ticket-demo login and claim-fix highlight. [Plain-language guide](playwright-agent/README.md). |

```
skill-set/
  README.md
  fake-no-more/                    SKILL.md + references + evals
  claim-mr/                        SKILL.md + detect-host
  claim-fix-ticket/                SKILL.md + scripts (red/green highlight)
  ticket-demo-video/               SKILL.md + scripts + Eve assets
  explain-implementation-video/    SKILL.md + scripts (two-act board + concat)
  explain-in-browser/              SKILL.md + markdown-to-HTML renderer
  playwright-agent/                standalone CLI + locator engine (used by the video skills)
  skill-explainers/                scripts + board for the README Eve videos
```

The three video skills are siblings. Install `ticket-demo-video` with the
other two — they reuse its Eve assets and compose/publish scripts.

| Skill | Picture | Audio |
| --- | --- | --- |
| `claim-fix-ticket` | Silent red/green pair, issue region boxed | none |
| `ticket-demo-video` | One live-UI route, Eve PIP | spoken explanation |
| `explain-implementation-video` | Act 1 studio cards + Act 2 host/.mov | one long Eve bed |
| `explain-in-browser` | Dark HTML reading page from markdown | none |

Eve is a talking-head cutout (both arms in frame, 72% opacity). She does
not point.

## Explainer videos

One short Eve + studio-board clip per README section. Watch them locally
(mp4s are gitignored — do not commit them):

| Section | Job-wired? | Local file |
| --- | --- | --- |
| Overview — what this repo is, and what you must change | **Start here** | `docs/ticket-demos/explainer-overview.mp4` |
| `/fake-no-more` | no — general | `docs/ticket-demos/explainer-fake-no-more.mp4` |
| `/claim-mr` | no — general | `docs/ticket-demos/explainer-claim-mr.mp4` |
| `/claim-fix-ticket` | **yes** — GitLab, demo login, Phoenix locators | `docs/ticket-demos/explainer-claim-fix-ticket.mp4` |
| `/ticket-demo-video` | **yes** — Eve assets, per-repo demo login | `docs/ticket-demos/explainer-ticket-demo-video.mp4` |
| `/explain-implementation-video` | **yes** — same family as ticket-demo | `docs/ticket-demos/explainer-explain-implementation-video.mp4` |
| `/explain-in-browser` | no — general | `docs/ticket-demos/explainer-explain-in-browser.mp4` |
| `/playwright-agent` | CLI is general; login helpers may be job-wired | `docs/ticket-demos/explainer-playwright-agent.mp4` |
| Installing | no — general | `docs/ticket-demos/explainer-installing.mp4` |
| Evals and demo videos | no — general | `docs/ticket-demos/explainer-evals-and-demos.mp4` |

**Job-wired** means the skill was built around *this* author’s stack
(GitLab issue boards, a Phoenix-style product, `demo-auth.json`, Eve
assets). It will not work on someone else’s repo until you swap those
hosts, login, and locators. The general skills only need the install
script.

Rebuild after changing a script:

```bash
node skill-explainers/build-explainers.mjs
# or one slug: node skill-explainers/build-explainers.mjs explainer-overview
```

## Installing

One script writes every skill into the three agent homes:

```bash
curl -fsSL https://raw.githubusercontent.com/Yuri-Lima/skill-set/main/install.sh \
  | bash -s -- --global
```

Or clone and run it:

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cd skill-set
./install.sh --global
```

| Flag | Where it copies |
| --- | --- |
| `--global` (default) | `~/.grok/skills`, `~/.claude/skills`, `~/.cursor/skills` |
| `--project` | this repo’s `.grok/skills`, `.claude/skills`, `.cursor/skills`, `.agents/skills` |
| `--skill NAME` | only that skill (repeatable) |
| `--update` | `git pull` the source, then recopy |
| `--list` | print skill names and exit |

```bash
./install.sh --skill ticket-demo-video --skill explain-implementation-video --global
./install.sh --update --global
./install.sh --project
```

Claude and Cursor can also use the skills CLI (no Grok target):

```bash
npx skills add Yuri-Lima/skill-set -g -a claude-code -a cursor
```

Grok already scans those Claude/Cursor folders. `--global` still writes
`~/.grok/skills` so Grok keeps them if compat is off.

Then invoke by slash command (`/claim-mr`, `/claim-fix-ticket`,
`/ticket-demo-video`, `/explain-implementation-video`,
`/explain-in-browser`, `/playwright-agent`) or let the `description`
frontmatter trigger.

Start a new session (or reload skills) after install.

## Playwright agent, in plain language

You tell it **which control**, the way you would tell a colleague:
“the Sign in button”, “the Email field”, “the card that says Next due”.
A real Chrome window does the click. If it cannot find exactly one
match, it stops instead of guessing.

That is the opposite of “AI looks at a page map and picks `@e12`”.
Those numbers go stale the moment the page changes.

`ticket-demo-video` (login) and `claim-fix-ticket` (red/green box)
already use this engine. The same four jobs:

| Job | What you run or write |
| --- | --- |
| Walk a public site | `node playwright-agent/src/cli.mjs open https://example.com --headed` then `click` / `fill` |
| Sign in for a spoken Eve demo | `emailLabel` / `passwordLabel` in `demo-auth.json` — see [use case 2](playwright-agent/README.md#2-sign-in-for-a-ticket-demo) |
| Box the bug for a silent before/after | `labelIssueArea(page, { text, closest })` — see [use case 3](playwright-agent/README.md#3-box-the-bug-for-a-beforeafter-video) |
| Save the clicks as a re-runnable test | `codegen /tmp/flow.spec.ts` — no AI on the next run |

Full install, flags, and copy-paste examples:
**[playwright-agent/README.md](playwright-agent/README.md)**.

```bash
cd playwright-agent && npm install && npx playwright install chromium
node src/cli.mjs open https://demo.playwright.dev/todomvc --headed
```

`install.sh` copies `playwright-agent` automatically when you install
`ticket-demo-video` or `claim-fix-ticket`. Track Microsoft’s official
Test Agent prompts with
`node playwright-agent/scripts/check-upstream.mjs --check`.

## Evals

Each skill that makes a judgment has `evals/evals.json` plus fixtures
(same shape as `fake-no-more`). They grade decisions, not live video
or API calls.

| Skill | What the evals catch |
| --- | --- |
| `fake-no-more` | Wrong / confirmed / unverifiable claims |
| `claim-fix-ticket` | Record-or-skip, auth stop, dirty tree |
| `ticket-demo-video` | Auth stop, stay vs handoff, watch path |
| `explain-implementation-video` | Handoff, ask-once, **no redaction** of the screencap, clip-clock |
| `claim-mr` | Claim-or-stop; `scripts/detect-host.test.mjs` is a unit test |
| `explain-in-browser` | Browser vs terminal; teaser-only TUI; keep-it-here; listen-in-page not `say`; `scripts/render-explanation.test.mjs` |
| `playwright-agent` | Strict resolve, journal codegen; `cd playwright-agent && npm test` |

```bash
node --test claim-mr/scripts/detect-host.test.mjs
node --test explain-in-browser/scripts/render-explanation.test.mjs
```

## Demo videos

Ticket before/after, Eve demos, and two-act films are **local + MR
uploads**. Do not commit `*.mp4` into product repos. The video skills
say to upload the file and paste the returned markdown into the merge
request body.

Authenticated UI recordings are **per project**. On first run the
agent scans the repo, suggests a sign-in method, and asks you for a
temporary/fake account (or a Playwright session file). That is written
to gitignored `docs/review-impact/demo-auth.json`. There is no
built-in product user. Env `DEMO_EMAIL` + `DEMO_PASSWORD` still works
if you already have them.
