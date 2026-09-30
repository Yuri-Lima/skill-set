---
name: live-ops-guard
description: >
  Guard live TeamCity and GitLab writes, every SSH/scp/sftp/sshfs call, and
  reads of secret stores — and leave a trail the operator can audit. Spawn the
  live-ops-guard watcher and wait for the operator before TeamCity
  POST/PUT/DELETE, GitLab MCP mutations, leaked tokens, any ssh/scp/sftp/sshfs
  (any host — including uptime), rsync over ssh, glab/curl API writes to GitLab
  hosts, `cat .env` / `gh auth token` style secret reads, or other irreversible
  commands. Every ask, redaction and fail-open goes to a ledger; sessions that
  exposed secret-like data are marked NEEDS_TRACE_REVIEW until a person runs
  `/live-ops-guard review`. Use when changing TeamCity, mutating GitLab via MCP
  or API, running ssh, using a live host, granting live access, running
  /live-ops-guard or /live-ops-guard review, or any write that cannot be undone.
  Covers Grok, Claude Code and Cursor hooks.
---

# Live-ops guard

A live TeamCity or GitLab server is production. This skill is the
agent-side procedure. Hooks are the last gate — do not skip either layer.
The guard addresses the person at the keyboard as **Dear Lazy User** unless
`LIVE_OPS_GUARD_OPERATOR` says otherwise; no real name or host is baked in.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

| Runtime | Events | Config |
|---------|--------|--------|
| **Grok** | `SessionStart` / `PreToolUse` / `PostToolUse` / `Stop` | `~/.grok/hooks/live-ops-guard.json` |
| **Claude Code** | `SessionStart` / `PreToolUse` / `PostToolUse` / `Stop` | `~/.claude/settings.json` (merged from `hooks/claude-code.json`) |
| **Cursor** | `sessionStart` / `beforeMCPExecution` / `beforeShellExecution` / `postToolUse` / `stop` | `~/.cursor/hooks.json` |

Same script for all three: `~/.grok/hooks/live-ops-guard/guard.py` (Claude Code
and Cursor get a one-line entry file that runs it). It flags:

- TeamCity writes
- **GitLab MCP writes** (`gitlab__*` in Grok, `mcp__gitlab__*` in Claude Code, Cursor MCP `create_*` / `merge_*` / … when the server is GitLab) and shell bypasses (`glab`, `curl` mutations to GitLab hosts)
- secret-like payloads (tokens, keys, JWTs, DB URLs with passwords)
- **secret-store reads**: `cat .env`, `~/.ssh/id_*`, `~/.aws/credentials`, `.netrc`, `gh auth token`, `op read`, `security find-*-password`, `vault kv get`, `kubectl get secret`, `echo $SOME_TOKEN`, bare `env` / `printenv`
- **every `ssh` / `scp` / `sftp` / `sshfs`** (any host). `rsync` when it is remote or uses ssh. Live-listed hosts and destructive remotes are extra findings, not a filter.

**Cursor gate:** `permission: ask` is enforced on `beforeMCPExecution` and `beforeShellExecution` only. Cursor `preToolUse` accepts `ask` but does not hold — do not treat it as the gate.

After `./install.sh --skill live-ops-guard --global`, the installer writes the Grok hook + agent, merges the Claude Code hook entries into `~/.claude/settings.json`, and merges the Cursor hook entries. Paste live SSH Host aliases into `~/.grok/hooks/live-ops-guard/live-hosts.txt` and self-hosted GitLab hostnames into `gitlab-hosts.txt` next to it (`gitlab.com` and any `gitlab.*` host are recognised without it). Do not invent a hostname, alias, or IP. Do not commit the filled files.

## The trail: ledger, marker, review

The guard is only useful if the operator can later answer "did a guarded
step run, was a secret exposed, do I have to look at the trace?". Three
files next to `guard.py` (or under `$LIVE_OPS_GUARD_HOME`) answer that:

| File | Written when | Contains |
|------|--------------|----------|
| `ledger.jsonl` | every ask, every redaction, every secret-store read, every fail-open, every payload the guard had to coerce | timestamp, session, runtime, tool name, finding **kinds**, decision. **Never the payload.** |
| `NEEDS_TRACE_REVIEW` | a secret-like value was found in a tool result, a secret store was read, or the guard failed open | session, runtime, reason, transcript path when the runtime gives one |
| (session start) | the marker is non-empty | the operator sees "N earlier session(s) … still need a trace review" before doing anything else |
| (session stop) | the session has ledger rows | counts: asked / redacted / secret reads / fail-opens, and `Trace review required: YES → …` |

The marker is **never cleared by the guard**. Only a person does it, after
looking at the trace:

```bash
python3 ~/.grok/hooks/live-ops-guard/guard.py review            # what is pending
python3 ~/.grok/hooks/live-ops-guard/guard.py review --last     # most recent flagged session
python3 ~/.grok/hooks/live-ops-guard/guard.py review <session>  # ledger + hand-off
python3 ~/.grok/hooks/live-ops-guard/guard.py review <session> --ack
```

`review <session>` prints the ledger rows, the transcript path if known, and
the exact next step: `/trace-analysis <transcript>` (or `/trace-watch <session>`
while it is still running). Rotate whatever the ledger says was exposed, then
`--ack`. `/live-ops-guard review` in a session means: run that command and
report the output; do not `--ack` on the operator's behalf.

### Honesty about redaction

The post hook asks the runtime to replace the tool result with a redacted
copy (`updatedToolOutput` / `updated_mcp_tool_output`). Not every runtime
honours that for every tool. The note the operator sees says so, and the
ledger + marker record the exposure **regardless** — a redaction claim is
never the reason to skip the trace review.

### Fail-open is loud

A payload the guard cannot read, or a crash inside it, still lets the call
through (a hook must not brick the session). But it says so to the operator
and the agent ("could NOT evaluate this call … treat it as unguarded"),
writes a `fail-open` ledger row, and marks the session. Non-dict tool inputs
(a list, a bare string) are flattened and still scanned for ssh/secrets, and
recorded as `shape: coerced`.

## SSH — always trigger the watcher

`ssh` is never "just a read". As soon as the command is `ssh` / `scp` / `sftp` / `sshfs` (or `rsync` over ssh):

1. **Stop.** Do not run Shell / `run_terminal_command` / `Bash` in the same turn you first invent the SSH.
2. **Spawn `live-ops-guard`** with the exact command (host, remote argv, why). Grok: `mcpInheritance` none. Cursor / Claude Code: child must not get Shell / Bash.
3. Show the operator the verdict. Wait for an explicit yes.
4. Only then run SSH. The hook will also ask — treat a reject as final.

This includes `ssh host uptime`, `ssh -N -L …`, interactive `ssh host`, and hosts **not** in `live-hosts.txt`.

## Secret reads — same rule

`cat .env`, `gh auth token`, `op read …`, `echo $API_KEY` and friends put a
secret into the transcript. The hook asks; if the operator approves, the
session is marked for trace review anyway, because the value is now in the
trace. Prefer `${VAR}` references, `-i $KEY_PATH`, and tools that consume a
secret without printing it.

## GitLab policy

| Kind | Examples | Hook |
|------|----------|------|
| **Allow** | `gitlab__get_*`, `list_*`, `search_*`, `whoami`, `mr_discussions`, dry_run patches, GET curl | allow |
| **Ask** | `create_*`, `update_*`, `delete_*`, `merge_*`, `approve_*`, `publish_*`, `upload_*`, `bulk_*`, notes, labels, … | ask operator |
| **Ask + irreversible** | merge MR, delete issue/MR/project/branch/tag | ask operator |
| **Ask (shell bypass)** | `glab` mutations, `curl` POST/PUT/PATCH/DELETE to a GitLab host | ask operator |

Reads do **not** need the agent. Writes do: spawn `live-ops-guard` with the exact tool name + redacted args before the first mutating call in a turn, unless the operator already approved that exact action this session.

## Tool shapes per runtime

Do not wait for a Grok-style `gitlab__*` / `teamcity__*` name.

- **Claude Code**: `mcp__gitlab__create_note`, `mcp__teamcity__teamcity_rest_post`; shell is `Bash`.
- **Cursor**: `CallDynamicTool` with `namespace` matching `teamcity` / `gitlab` + bare `toolName`; `beforeMCPExecution` with `mcp_server_name`; `Shell` / `beforeShellExecution`.
- **Grok**: `gitlab__*`, `teamcity__*`, `use_tool` wrappers, `run_terminal_command`.

YouTrack `create_issue` is **not** GitLab. Only prefix/server/url that actually say GitLab (or a host in `gitlab-hosts.txt`).

## Before any live write

1. Stop. Do not call a TeamCity POST/PUT/DELETE in the same turn you first invent the change.
2. Do not call mutating GitLab MCP tools (any runtime's spelling) in the same turn you first invent the change.
3. Do not run `ssh` / `scp` / `sftp` / `sshfs` (any host) or remote `rsync` in the same turn you first invent the command. Spawn the watcher first — including `ssh host uptime`.
4. Do not run `glab` mutations or scripted GitLab API writes without prior approval.
5. If any decision is missing (project, build config, MR/issue, branch, personal vs team-visible, create vs edit, SSH host, whether to write or delete), ask the operator. Do not pick a default.
6. Spawn `live-ops-guard` with the exact proposed call (tool, path/args redacted, SSH command, why). Grok: `mcpInheritance` none. Cursor / Claude Code: do not give the child a tool that can execute the write.
7. After the guard returns, show the verdict, findings, and questions. Wait for an explicit yes.
8. Only then make the call. Prefer `"personal": true` on TeamCity `/app/rest/buildQueue` unless the operator asked for a team-visible build. Prefer GitLab reads over writes.

## Never

- Put API keys, tokens, passwords, private keys, or SSH private key material in tool arguments. Use `${ENV_VAR}` names and `-i $KEY_PATH` only.
- Delete a TeamCity project, buildType, VCS root, or agent unless the operator named that object and said delete.
- Merge/close/delete a GitLab MR or issue unless the operator named it and said to.
- Queue a non-personal TeamCity build, edit production steps, or change parameters because it is "probably fine".
- Run `rm`, `systemctl stop/restart`, `docker rm`, `reboot`, or edit TeamCity data dirs over SSH unless the operator named that command.
- Open an interactive SSH shell unless the operator asked for a shell. Live-listed hosts are extra-sensitive.
- Echo a secret from a tool result. If the hook redacted it, keep it redacted. If the hook said the runtime may not have honoured the redaction, do not "help" by quoting the value.
- Clear `NEEDS_TRACE_REVIEW` (`--ack`) on the operator's behalf, or tell them the session is clean because a redaction note appeared.
- Commit `live-hosts.txt`, `gitlab-hosts.txt`, `ledger.jsonl` or `NEEDS_TRACE_REVIEW`. The public copies are the `*.example.txt` files only.

## After a hook ask

If the runtime prompts because of `live-ops-guard`, treat a reject as final for that call. Change the call or ask the operator; do not immediately retry the same payload.

## Files

- Agent: `~/.grok/agents/live-ops-guard.md`
- Grok hook config: `~/.grok/hooks/live-ops-guard.json`
- Claude Code hook fragment: `$SKILL_DIR/hooks/claude-code.json` → merged into `~/.claude/settings.json`; entry `~/.claude/hooks/live-ops-guard.py`
- Cursor hook config: `~/.cursor/hooks.json`; entry `~/.cursor/hooks/live-ops-guard.py`
- Hook script: `~/.grok/hooks/live-ops-guard/guard.py`
- Live hosts: `~/.grok/hooks/live-ops-guard/live-hosts.txt`; GitLab hosts: `gitlab-hosts.txt`
- Ledger / marker: `~/.grok/hooks/live-ops-guard/ledger.jsonl`, `NEEDS_TRACE_REVIEW`
- Self-test: `bash $SKILL_DIR/scripts/test-guard.sh` (runs `hooks/test_guard.py` in a throwaway home)
