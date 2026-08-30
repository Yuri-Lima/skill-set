# Ticket adapters

The orchestrator uses the **ticketHost** value from knowledge. Never pick a host that knowledge does not name.

## none

Do not create or comment on tickets. Unverified findings go only to the ledger. Say so in the report.

## youtrack

Write-side only. Never query open tickets to build a work list.

- Token: env `YOU_TRACK_TOKEN` (Bearer). Missing → skip, say so.
- Create: `POST {instance}/api/issues?fields=idReadable` with project, summary, description.
- Comment: `POST {instance}/api/issues/{id}/comments` `{ "text": "..." }`.
- Tag every created ticket with the tag from knowledge (`POST /api/commands`).
- Instance, project short name, and ticket id shape live in knowledge, not here.

## github

Stub this slice. Leave the local `fix/*` branch. Report: create a GitHub issue by hand and paste the PR link. Do not call `gh issue create` unless knowledge later grows a verified recipe.

## gitlab

Stub this slice. Leave the local `fix/*` branch. Report: create a GitLab issue by hand. Do not call `glab` unless knowledge later grows a verified recipe.

## gitea

Gitea is a PR host, not a ticket host. If knowledge set `ticketHost: gitea`, treat it as `none` and say so.
