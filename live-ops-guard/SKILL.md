---
name: live-ops-guard
description: >
  Guard live TeamCity and GitLab writes, and every SSH/scp/sftp/sshfs call.
  Spawn the live-ops-guard watcher and wait for the operator before TeamCity
  POST/PUT/DELETE, GitLab MCP mutations, leaked tokens, any ssh/scp/sftp/sshfs
  (any host — including uptime), rsync over ssh, glab/curl API writes to GitLab
  hosts, or other irreversible commands. Use when changing TeamCity, mutating
  GitLab via MCP or API, running ssh, using a live host, granting live access,
  running /live-ops-guard, or any write that cannot be undone. Also covers
  Cursor beforeMCPExecution / beforeShellExecution (CallDynamicTool, Shell).
---

# Live-ops guard

A live TeamCity or GitLab server is production. This skill is the
agent-side procedure. Hooks are the last gate — do not skip either layer.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

| Runtime | Events | Config |
|---------|--------|--------|
| **Grok** | `PreToolUse` / `PostToolUse` | `~/.grok/hooks/live-ops-guard.json` |
| **Cursor** | `beforeMCPExecution` / `beforeShellExecution` / `postToolUse` | `~/.cursor/hooks.json` |

Same script: `~/.grok/hooks/live-ops-guard/guard.py`. It flags:

- TeamCity writes
- **GitLab MCP writes** (`gitlab__*` in Grok; Cursor MCP `create_*` / `merge_*` / … when the server is GitLab) and shell bypasses (`glab`, `curl` mutations to GitLab hosts)
- secret-like payloads
- **every `ssh` / `scp` / `sftp` / `sshfs`** (any host). `rsync` when it is remote or uses ssh. Live-listed hosts and destructive remotes are extra findings, not a filter.

**Cursor gate:** `permission: ask` is enforced on `beforeMCPExecution` and `beforeShellExecution` only. Cursor `preToolUse` accepts `ask` but does not hold — do not treat it as the gate.

After `./install.sh --skill live-ops-guard --global`, the installer writes the Grok hook + agent and merges Cursor hook entries. Paste live SSH Host aliases into `~/.grok/hooks/live-ops-guard/live-hosts.txt`. Do not invent a hostname, alias, or IP. Do not commit the filled hosts file.

## SSH — always trigger the watcher

`ssh` is never “just a read”. As soon as the command is `ssh` / `scp` / `sftp` / `sshfs` (or `rsync` over ssh):

1. **Stop.** Do not run Shell / `run_terminal_command` in the same turn you first invent the SSH.
2. **Spawn `live-ops-guard`** with the exact command (host, remote argv, why). Grok: `mcpInheritance` none. Cursor: child must not get Shell.
3. Show the operator the verdict. Wait for an explicit yes.
4. Only then run SSH. The Cursor `beforeShellExecution` hook will also `permission: ask` — treat a reject as final.

This includes `ssh host uptime`, `ssh -N -L …`, interactive `ssh host`, and hosts **not** in `live-hosts.txt`.

## GitLab policy

| Kind | Examples | Hook |
|------|----------|------|
| **Allow** | `gitlab__get_*`, `list_*`, `search_*`, `whoami`, `mr_discussions`, dry_run patches, GET curl | allow |
| **Ask** | `create_*`, `update_*`, `delete_*`, `merge_*`, `approve_*`, `publish_*`, `upload_*`, `bulk_*`, notes, labels, … | ask operator |
| **Ask + irreversible** | merge MR, delete issue/MR/project/branch/tag | ask operator |
| **Ask (shell bypass)** | `glab` mutations, `curl` POST/PUT/PATCH/DELETE to a GitLab host | ask operator |

Reads do **not** need the agent. Writes do: spawn `live-ops-guard` with the exact tool name + redacted args before the first mutating call in a turn, unless the operator already approved that exact action this session.

## Cursor tool shapes

Do not wait for a Grok-style `gitlab__*` / `teamcity__*` name. Cursor live writes look like:

- `CallDynamicTool` `namespace` matching `teamcity` + `toolName` `teamcity_rest_post` / `put` / `delete`
- `CallDynamicTool` `namespace` matching `gitlab` + mutating `toolName` (`create_note`, `merge_merge_request`, …)
- MCP `beforeMCPExecution`: `mcp_server_name` `teamcity` / `gitlab` + the same bare tool names
- `Shell` / `beforeShellExecution`: **any** `ssh`/`scp`/`sftp`/`sshfs` (hook asks immediately), remote `rsync`, `glab` mutations, `curl` writes to GitLab hosts

YouTrack `create_issue` is **not** GitLab. Only prefix/server/url that actually say GitLab.

## Before any live write

1. Stop. Do not call `teamcity__teamcity_rest_post|put|delete` or Cursor `teamcity_rest_post|put|delete` in the same turn you first invent the change.
2. Do not call mutating `gitlab__*` MCP tools, Cursor GitLab MCP tools, or `CallDynamicTool` wrapping them, in the same turn you first invent the change.
3. Do not run `ssh` / `scp` / `sftp` / `sshfs` (any host) or remote `rsync` in the same turn you first invent the command. Spawn the watcher first — including `ssh host uptime`.
4. Do not run `glab` mutations or scripted GitLab API writes without prior approval.
5. If any decision is missing (project, build config, MR/issue, branch, personal vs team-visible, create vs edit, SSH host, whether to write or delete), ask the operator. Do not pick a default.
6. Spawn `live-ops-guard` with the exact proposed call (tool, path/args redacted, SSH command, why). Grok: `mcpInheritance` none. Cursor: do not give the child `CallDynamicTool` / Shell that can execute the write.
7. After the guard returns, show the verdict, findings, and questions. Wait for an explicit yes.
8. Only then make the call. Prefer `"personal": true` on TeamCity `/app/rest/buildQueue` unless the operator asked for a team-visible build. Prefer GitLab reads over writes.

## Never

- Put API keys, tokens, passwords, private keys, or SSH private key material in tool arguments. Use `${ENV_VAR}` names and `-i $KEY_PATH` only.
- Delete a TeamCity project, buildType, VCS root, or agent unless the operator named that object and said delete.
- Merge/close/delete a GitLab MR or issue unless the operator named it and said to.
- Queue a non-personal TeamCity build, edit production steps, or change parameters because it is "probably fine".
- Run `rm`, `systemctl stop/restart`, `docker rm`, `reboot`, or edit TeamCity data dirs over SSH unless the operator named that command.
- Open an interactive SSH shell unless the operator asked for a shell. Live-listed hosts are extra-sensitive.
- Echo a secret from a tool result. If the hook redacted it, keep it redacted.
- Commit `live-hosts.txt` with real IPs, aliases, or key paths. The public copy is `hooks/live-hosts.example.txt` only.

## After a hook ask

If Grok or Cursor prompts because of `live-ops-guard`, treat a reject as final for that call. Change the call or ask the operator; do not immediately retry the same payload.

## Files

- Agent: `~/.grok/agents/live-ops-guard.md`
- Grok hook config: `~/.grok/hooks/live-ops-guard.json`
- Cursor hook config: `~/.cursor/hooks.json`
- Hook script: `~/.grok/hooks/live-ops-guard/guard.py`
- Live hosts: `~/.grok/hooks/live-ops-guard/live-hosts.txt`
- Self-test: `python3 $SKILL_DIR/hooks/test_guard.py`
