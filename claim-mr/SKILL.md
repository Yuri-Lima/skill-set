---
name: claim-mr
description: >-
  Post a short “claimed for review” note on a pull/merge request so other
  developers do not double-work the same review. Works on GitHub, GitLab,
  and Gitea (and Forgejo / Codeberg). Accepts a PR/MR URL or number
  (e.g. /claim-mr https://github.com/acme/app/pull/12, /claim-mr 54,
  /claim-mr !54). Use when the user runs /claim-mr, or says "claim this
  MR", "claim this PR", "claim MR", "I'm taking this review", "avoid
  double work on MR", or wants to mark a review as theirs.
---

# Claim PR / MR

Post a single **claim note** on a pull request or merge request so
teammates do not start a parallel full review.

Hosts: **GitHub**, **GitLab**, **Gitea** (same API as Forgejo / Codeberg).
Detect the host from the URL or `git remote`; do not assume GitLab.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

## Parse the target

```bash
node "$SKILL_DIR/scripts/detect-host.mjs" "<user text or URL>"
```

That prints `provider`, `host`, `owner`, `repo`, `number`, `slug`, `note`.

If the user pasted a URL, prefer it. If they only gave `54` / `!54`,
use `origin`. If `provider` is `unknown` or `unknown-pull`, ask once:
GitHub, GitLab, or Gitea?

| URL shape | Provider |
| --- | --- |
| `…/pull/12` on github.com or `*.ghe.com` | github |
| `…/-/merge_requests/54` or host contains `gitlab` | gitlab |
| `…/pulls/12` on gitea / forgejo / codeberg.org | gitea |

## Note body (default)

```markdown
**Claimed for review**

I've claimed this MR and am reviewing it now so we avoid duplicate work. Please don't start a parallel full review unless coordinating with me first — happy to take comments/questions while I'm on it.
```

Use the user’s text instead if they supplied one.

## Post the claim

Confirm the PR/MR is **open**. If it is closed/merged, tell the user and
do not claim unless they insist.

If recent comments show **you** already claimed in the last few minutes,
skip a second note. If another human claimed actively, **warn** before
posting unless they said force.

Best-effort: add yourself as a **reviewer**. Do not steal the assignee.
Do not fail the claim if reviewer assignment errors.

### GitHub

```bash
gh pr view {number} --repo {slug} --json title,state,url,comments
gh pr comment {number} --repo {slug} --body "{note}"
gh pr edit {number} --repo {slug} --add-reviewer "$(gh api user --jq .login)"
```

Self-hosted GHES: `GH_HOST={host}` or `gh -R {host}/{slug}`.

### GitLab

Use the GitLab MCP (`search_tool` if schemas are not loaded):

1. `gitlab__get_merge_request` — confirm open
2. `gitlab__create_merge_request_note` (or `gitlab__create_note` with
   `noteable_type: merge_request`)
3. Optional: `gitlab__update_merge_request` with your id in
   `reviewer_ids` (`gitlab__whoami`)

`project_id` is the URL path (`group/project`). Self-hosted GitLab
(e.g. nova.teachx.ai) uses the same tools when that host is configured.

### Gitea / Forgejo / Codeberg

Prefer `tea` when logged in:

```bash
tea pulls {number} --repo {slug}
tea comment {number} --repo {slug} "{note}"
```

Otherwise REST (token in `GITEA_TOKEN` or `TEA_TOKEN`):

```bash
curl -sS -X POST \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"body\": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$NOTE")}" \
  "https://{host}/api/v1/repos/{owner}/{repo}/issues/{number}/comments"
```

Adding a reviewer is best-effort:
`PUT /api/v1/repos/{owner}/{repo}/pulls/{number}/requested_reviewers`
with `{"reviewers":["<your-login>"]}`.

## Report

```
Claimed {PR|MR} #{number} on {provider}: {title}
- Note posted (avoid double review)
- {web_url}
```

## Do not

- Start a full code review unless the user also asked to review
- Force-push, merge, approve, or change PR/MR state
- Spam a second claim note
- Assume every repo is GitLab
