---
name: live-ops-guard
description: >
  Guard live TeamCity (and other live-server) writes. Spawn the live-ops-guard
  agent and wait for the operator before POST/PUT/DELETE, leaked tokens,
  destructive SSH/scp/rsync/sftp/sshfs, or irreversible commands. Use when
  changing TeamCity, using SSH to a live CI host, granting live access, running
  /live-ops-guard, or any write that cannot be undone.
---

# Live-ops guard

A live TeamCity (or other CI) server is production. This skill is the
agent-side procedure. A PreToolUse hook is the last gate — do not skip
either layer.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

Live SSH hosts are only names the operator pasted into
`~/.grok/hooks/live-ops-guard/live-hosts.txt`. Do not invent a hostname,
alias, or IP. After `./install.sh --skill live-ops-guard --global`, also
run the Grok runtime installer (or let `install.sh` do it) so the hook
and agent land under `~/.grok/hooks` and `~/.grok/agents`.

## Before any live write

1. Stop. Do not call `teamcity__teamcity_rest_post`,
   `teamcity__teamcity_rest_put`, or `teamcity__teamcity_rest_delete` in
   the same turn you first invent the change.
2. Do not run `ssh`, `scp`, `rsync`, `sftp`, or `sshfs` toward a live
   host in the same turn you first invent the command.
3. If any decision is missing (project, build config, branch, personal
   vs team-visible, create vs edit, SSH host, whether to write or
   delete), ask the operator. Do not pick a default.
4. Spawn `live-ops-guard` with the exact proposed call (tool, path,
   redacted body, SSH command, why). That child cannot execute the write
   or SSH.
5. After the guard returns, show the verdict, findings, and questions.
   Wait for an explicit yes.
6. Only then make the call. Prefer `"personal": true` on
   `/app/rest/buildQueue` unless the operator asked for a team-visible
   build. Prefer read-only remote commands (`uptime`, `journalctl`,
   `tail`) over a login shell.

## Never

- Put API keys, tokens, passwords, private keys, or SSH private key
  material in tool arguments. Use `${ENV_VAR}` names and `-i $KEY_PATH`
  only.
- Delete a project, buildType, VCS root, or agent unless the operator
  named that object and said delete.
- Queue a non-personal build, edit production steps, or change
  parameters because it is "probably fine".
- Run `rm`, `systemctl stop/restart`, `docker rm`, `reboot`, or edit
  TeamCity data dirs over SSH unless the operator named that command.
- Open an interactive SSH shell on a live host unless the operator asked
  for a shell.
- Echo a secret from a tool result. If the hook redacted it, keep it
  redacted.
- Commit `live-hosts.txt` with real IPs, aliases, or key paths. The
  public copy is `hooks/live-hosts.example.txt` only.

## After a hook ask

If the client prompts because of `live-ops-guard`, treat a reject as
final for that call. Change the call or ask the operator; do not
immediately retry the same payload.
