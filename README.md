# skill-set

Agent skills I use with Claude Code.

| Skill | What it does |
|---|---|
| [`fake-no-more`](fake-no-more/) | Verify factual claims against primary sources before they ship, and mark every claim with where it came from. Domain-agnostic — code, legal, research, data. |

## Installing a skill

Copy the skill's folder into your skills directory:

```bash
git clone https://github.com/Yuri-Lima/skill-set.git
cp -R skill-set/fake-no-more ~/.claude/skills/
```

Then invoke it by name (`/fake-no-more`), or let it trigger on its own from the
`description` in its `SKILL.md` frontmatter.
