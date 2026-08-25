# skill-set

Agent skills I reuse across Claude Code, Cursor, and Grok.

| Skill | Invoke | What it does |
| --- | --- | --- |
| [`fake-no-more`](fake-no-more/) | `/fake-no-more` | Verify factual claims against primary sources and mark every claim with where it came from. |
| [`claim-mr`](claim-mr/) | `/claim-mr` | Post a short “claimed for review” note on a GitHub, GitLab, or Gitea PR/MR so nobody double-starts the same review. |
| [`claim-fix-ticket`](claim-fix-ticket/) | `/claim-fix-ticket` | Claim a GitLab issue, record a highlighted **before** UI video, implement, run gates, record the same region **after**. |
| [`ticket-demo-video`](ticket-demo-video/) | `/ticket-demo-video` | Spoken Eve + live UI walkthrough, length = the explanation. Attach the mp4 to the MR; do not commit it. |
| [`explain-implementation-video`](explain-implementation-video/) | `/explain-implementation-video` | Two-act film: Eve narrates locked decisions on a studio board, then a product recording proves the result. |

```
skill-set/
  README.md
  fake-no-more/                    SKILL.md + references + evals
  claim-mr/                        SKILL.md + detect-host
  claim-fix-ticket/                SKILL.md + scripts (red/green highlight)
  ticket-demo-video/               SKILL.md + scripts + Eve assets
  explain-implementation-video/    SKILL.md + scripts (two-act board + concat)
```

The three video skills are siblings. Install `ticket-demo-video` with the
other two — they reuse its Eve assets and compose/publish scripts.

| Skill | Picture | Audio |
| --- | --- | --- |
| `claim-fix-ticket` | Silent red/green pair, issue region boxed | none |
| `ticket-demo-video` | One live-UI route, Eve PIP | spoken explanation |
| `explain-implementation-video` | Act 1 studio cards + Act 2 host/.mov | one long Eve bed |

Eve is a talking-head cutout (both arms in frame, 72% opacity). She does
not point.

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
`/ticket-demo-video`, `/explain-implementation-video`) or let the
`description` frontmatter trigger. Start a new session (or reload
skills) after install.

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
