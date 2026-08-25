# skill-set

Agent skills I reuse across Claude Code and Grok.

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

Copy the skill folder into the agent’s skills directory.

**Grok**

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cp -R skill-set/claim-mr ~/.grok/skills/
cp -R skill-set/claim-fix-ticket ~/.grok/skills/
cp -R skill-set/ticket-demo-video ~/.grok/skills/
cp -R skill-set/explain-implementation-video ~/.grok/skills/
```

**Claude Code**

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cp -R skill-set/claim-mr ~/.claude/skills/
cp -R skill-set/claim-fix-ticket ~/.claude/skills/
cp -R skill-set/ticket-demo-video ~/.claude/skills/
cp -R skill-set/explain-implementation-video ~/.claude/skills/
```

Or copy into a project’s `.grok/skills/` / `.claude/skills/` so only
that repo sees them.

Then invoke by slash command (`/claim-mr`, `/claim-fix-ticket`,
`/ticket-demo-video`, `/explain-implementation-video`) or let the
`description` frontmatter trigger.

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
