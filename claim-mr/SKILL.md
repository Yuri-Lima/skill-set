---
name: claim-mr
description: >-
  Post a short “claimed for review” note on a GitLab merge request so other
  developers do not double-work the same MR. Accepts an MR URL or IID (e.g.
  /claim-mr https://host/.../merge_requests/54 or /claim-mr 54). Uses the
  GitLab MCP to create the note; optional: add self as reviewer. Use when
  the user runs /claim-mr, or says "claim this MR", "claim MR", "I'm taking
  this review", "avoid double work on MR", or wants to mark an MR as being
  reviewed by them.
---

# Claim MR

Post a single **claim note** on a GitLab merge request so teammates do not
start a parallel full review.

## Parse the target

From the user message, extract:

1. **MR IID** — prefer an explicit number, else parse from URL:
   - `.../merge_requests/54` → `54`
   - `!54` → `54`
2. **Project path** — from the URL when present:
   - `https://host/group/project/-/merge_requests/54` → `group/project`
3. If only an IID is given (`/claim-mr 54`):
   - Prefer `git remote get-url origin`
     (`git@host:group/project.git` → `group/project`)
   - Else the project this workspace already uses for GitLab tools

If neither URL nor IID can be resolved, ask once for the MR URL or number.

## Note body (default)

Keep it short. Use this unless the user supplied their own text:

```markdown
**Claimed for review**

I've claimed this MR and am reviewing it now so we avoid duplicate work. Please don't start a parallel full review unless coordinating with me first — happy to take comments/questions while I'm on it.
```

## Steps

1. Resolve `project_id` + `merge_request_iid`.
2. Discover GitLab tools via `search_tool` if schemas are not already known.
3. Optionally `gitlab__get_merge_request` to confirm the MR is open.
   If closed/merged: tell the user and **do not** claim unless they insist.
4. Create the note with `gitlab__create_merge_request_note` (or
   `gitlab__create_note` with `noteable_type: merge_request`).
5. Best-effort (do not fail the claim if this errors): add the current
   GitLab user as a **reviewer** via `gitlab__update_merge_request`
   `reviewer_ids`. Do not steal the assignee.
6. If recent notes show **you** already claimed in the last few minutes,
   skip a second note. If another human claimed actively, **warn** before
   posting unless they said force.

## Report

```
Claimed MR !{iid}: {title}
- Note posted (avoid double review)
- {web_url}
```

## Do not

- Start a full code review unless the user also asked to review
- Force-push, merge, approve, or change MR state
- Spam a second claim note
