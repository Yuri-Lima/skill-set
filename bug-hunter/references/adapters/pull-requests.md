# Pull-request adapters

The orchestrator uses the **prHost** value from knowledge. Never pick a host that knowledge does not name.

Common to every host:

- One bug = one branch = one commit. Message from knowledge (default `🐛 FIX: <what>`). No AI attribution lines.
- Cut `fix/*` from the base branch knowledge names. Never branch off the hunt branch if knowledge says the hunt branch is terminal.
- Push only the fix branch. Revert the fix from the hunt worktree after the commit (knowledge Git recipe).
- Missing token → leave the local branch, do not pretend the PR exists.

## none

Stop after the local `fix/*` branch. Report the branch name and the exact human publish steps.

## gitea

```
POST {instance}/api/v1/repos/{owner}/{repo}/pulls
Authorization: token $GITEA_TOKEN
{"base":"<base>","head":"<fix-branch>","title":"...","body":"..."}
```

Instance, owner, repo, and base live in knowledge. Do not use a `tea` CLI if knowledge says it breaks on this repo.

## github

Stub this slice unless knowledge includes a verified `gh pr create` recipe. Default: push the fix branch if `$GITHUB_TOKEN` or `gh` auth works, then tell the human to open the PR.

## gitlab

Stub this slice unless knowledge includes a verified `glab mr create` recipe. Default: push the fix branch if `$GITLAB_TOKEN` works, then tell the human to open the MR.

## youtrack

YouTrack is a ticket host, not a PR host. If knowledge set `prHost: youtrack`, treat it as `none` and say so.
