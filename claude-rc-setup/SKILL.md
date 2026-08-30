---
name: claude-rc-setup
description: >-
  Make Claude Code Remote Control a permanent systemd service so
  claude.ai/code and the phone app can connect without an open SSH
  terminal. Discovers the box, writes /etc/systemd/system/claude-rc.service,
  enables it, and verifies. Also status, restart, stop, or undo the unit.
  Use when the user runs /claude-rc-setup, or says "remote control
  permanente", "claude rc service", "systemd claude", "acesso remoto
  permanente", "permanent remote control", or "set up claude remote-control
  as a service".
---

# Claude Code Remote Control as a service

Leave `claude remote-control` running across SSH logout and reboot so
the session shows up at claude.ai/code and in the phone app.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

Linux + systemd only. This is not launchd / Windows / a user-unit
helper. Modes: **setup** (default), **status**, **restart**, **stop**,
**undo**. Pick from the user text; if they only ran `/claude-rc-setup`,
do setup.

Show the output of every check before the next step. If a precondition
fails, **stop** and say what is missing. Do not work around it.

## Setup

### 1. Probe

```bash
bash "$SKILL_DIR/scripts/probe.sh"
```

Print the whole block. `precondition=ok` is required to continue.

| `fail=` | Stop and tell them |
| --- | --- |
| `no-systemd` | PID 1 is not systemd |
| `no-claude` | `claude` missing or `--version` failed |
| `no-auth` | no `$HOME/.claude` for this user — they must run `claude` interactively and `/login` first. A unit cannot finish login. |

If `stray_pids` is non-empty, warn: a manual `remote-control` is
already up. After the unit is healthy, stop those PIDs so two servers
do not share `WORKDIR`.

If `blocking_env` is non-empty, tell them those variables disable
Remote Control eligibility (`ANTHROPIC_BASE_URL` other than
api.anthropic.com, `DISABLE_TELEMETRY`, `DO_NOT_TRACK`,
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_GROWTHBOOK`).
The unit file does not inherit the SSH shell, so they do not block
the service unless copied into it. Do not copy them in.

### 2. Parameters

Confirm, then keep:

| Key | Default | Rule |
| --- | --- | --- |
| `WORKDIR` | `pwd` | Absolute path. **Not** `$HOME` and not `/`. Official workspace-trust never saves for the home directory. |
| `NAME` | `hostname` | Unique per machine. Two boxes with the same name are indistinguishable at claude.ai/code. |
| `RUNUSER` / `HOMEDIR` | probe `user` / `home` | Same user that already logged in. `User=root` ⇒ `HOME=/root`. |

If `WORKDIR` is `$HOME` or `/`, stop and ask for a project directory.

If they have never run `claude` (and then `claude remote-control`)
**interactively in `WORKDIR`**, stop. First-run trust + Remote Control
consent need stdin. A unit hangs or crash-loops on those prompts.
They run, then re-invoke this skill:

```bash
cd WORKDIR
claude                          # accept workspace trust
claude remote-control --name NAME --spawn same-dir
# wait until the session URL / QR appears, then Ctrl-C
```

If `existing_unit` is not `none`, print the file. Replace only when
the user wants a rewrite or the params differ; otherwise skip to
verify.

### 3. Write the unit

Render, show it, then install (needs sudo):

```bash
bash "$SKILL_DIR/scripts/write-unit.sh" --print \
  --name "$NAME" --user "$RUNUSER" --home "$HOMEDIR" \
  --workdir "$WORKDIR" --bin "$CLAUDE_BIN"

bash "$SKILL_DIR/scripts/write-unit.sh" --install \
  --name "$NAME" --user "$RUNUSER" --home "$HOMEDIR" \
  --workdir "$WORKDIR" --bin "$CLAUDE_BIN"
```

`CLAUDE_BIN` is the absolute path from probe (`claude_bin=`). systemd
does not search `PATH` in `ExecStart`. If sudo is refused, leave the
printed unit and stop.

Do not hand-edit a second copy of the unit. The template is
`references/claude-rc.service.tmpl`.

### 4. Enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now claude-rc
```

### 5. Verify

```bash
bash "$SKILL_DIR/scripts/verify.sh"
```

Success: `verdict=ok` (`active` + `enabled` + stable `NRestarts` + a
`remote-control` process + no credential error in the journal).

If `verdict=crash-loop` or `auth-error`: do **not** call it done.
Usual cause: login or first-run consent was skipped. Stop the unit
and send them back to the interactive commands in §2.

If `verdict=ok` and `stray_pids` was set, stop those manual PIDs.

### 6. Report

- passed every success check, or which one failed
- the `NAME` that will appear at claude.ai/code
- whether a stray `claude rc` was running, and whether it was stopped

Do not reboot the machine unless the user asks.

## Status / restart / stop

```bash
sudo systemctl status claude-rc --no-pager
sudo journalctl -u claude-rc -n 50 --no-pager
sudo systemctl restart claude-rc
sudo systemctl stop claude-rc
```

`status` is inspect-only. `restart` / `stop` only when they asked.

## Undo

```bash
sudo systemctl disable --now claude-rc
sudo rm -f /etc/systemd/system/claude-rc.service
sudo systemctl daemon-reload
```

Confirm before deleting the unit.

## Do not

- Activate a unit for a user who has not logged in as that user
- Use `$HOME` or `/` as `WORKDIR`
- Put a relative path in `ExecStart` (fails `status=203/EXEC`)
- Reuse a `NAME` already used by another machine
- Leave the unit and a manual `claude remote-control` on the same dir
- Copy blocking env vars into the unit
- Reboot as a test
- Invent launchd / Windows / `systemd --user` paths
