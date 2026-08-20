# skill-set

Agent skills I reuse across Claude Code and Grok.

| Skill | Invoke | What it does |
| --- | --- | --- |
| [`fake-no-more`](fake-no-more/) | `/fake-no-more` | Verify factual claims against primary sources and mark every claim with where it came from. |
| [`claim-mr`](claim-mr/) | `/claim-mr` | Post a short “claimed for review” note on a GitLab MR so nobody double-starts the same review. |
| [`claim-fix-ticket`](claim-fix-ticket/) | `/claim-fix-ticket` | Claim a GitLab issue, record a highlighted **before** UI video, implement, run gates, record the same region **after**. |
| [`ticket-demo-video`](ticket-demo-video/) | `/ticket-demo-video` | Spoken Eve + live UI walkthrough, length = the explanation. Attach the mp4 to the MR; do not commit it. |

```
skill-set/
  README.md
  fake-no-more/           SKILL.md + references + evals
  claim-mr/               SKILL.md
  claim-fix-ticket/       SKILL.md + scripts (red/green highlight)
  ticket-demo-video/      SKILL.md + scripts + Eve assets
```

`claim-fix-ticket` and `ticket-demo-video` are siblings: the silent
before/after pair vs the spoken demo. Install both if you want the full
loop.

## Installing

Copy the skill folder into the agent’s skills directory.

**Grok**

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cp -R skill-set/claim-mr ~/.grok/skills/
cp -R skill-set/claim-fix-ticket ~/.grok/skills/
cp -R skill-set/ticket-demo-video ~/.grok/skills/
```

**Claude Code**

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cp -R skill-set/claim-mr ~/.claude/skills/
cp -R skill-set/claim-fix-ticket ~/.claude/skills/
cp -R skill-set/ticket-demo-video ~/.claude/skills/
```

Or copy into a project’s `.grok/skills/` / `.claude/skills/` so only
that repo sees them.

Then invoke by slash command (`/claim-mr`, `/claim-fix-ticket`,
`/ticket-demo-video`) or let the `description` frontmatter trigger.

## Demo videos

Ticket before/after and Eve demos are **local + MR uploads**. Do not
commit `*.mp4` into product repos. `claim-fix-ticket` and
`ticket-demo-video` both say to `gitlab__upload_markdown` and paste the
returned markdown into the merge request body.

Authenticated UI recordings need `DEMO_EMAIL` and `DEMO_PASSWORD` in
the environment. There is no product-specific default user.
