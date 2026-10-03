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
agent-side procedure; the hooks are the trail and the interruption.
The guard addresses the person at the keyboard as **Dear Lazy User** unless
`LIVE_OPS_GUARD_OPERATOR` says otherwise; no real name or host is baked in.

## Modes

| Mode | Before a live call | On a real exposure |
|------|--------------------|--------------------|
| **`hybrid`** (default) | Like `notify`, except three things are still **held** with a permission ask: ssh/scp/sftp/sshfs/rsync to a host in `live-hosts.txt`, an irreversible GitLab action (merge, delete), an irreversible TeamCity action (delete, steps, VCS roots, agents). Everything else runs and is noted. | The guard **interrupts** with an exposure notice and four options — Proceed / Stop / Recommended / Evidence. |
| `notify` | The call **runs**. Findings (ssh, GitLab/TeamCity write, secret-store read) go to the ledger and the agent gets a one-line note. No question is asked. | Same notice and options. |
| `gate` | The call is **held** with a permission "ask" (the original behaviour). | Same notice and options. |

Set with `--mode notify|gate` on the hook command, or `LIVE_OPS_GUARD_MODE=…`.
Why hybrid: in the first two days of `notify` an agent merged a GitLab MR and ssh'd into
the live-listed TeamCity host with nothing but a note to itself. Those two classes are the
ones a note does not cover; a `.env` read or an ssh to a build agent is.

A "real exposure" is one of: a secret-like value in a tool **result**, a
secret store **read** (`cat .env`, `gh auth token`, …), a secret literal in a
tool **input** (the agent typed it), or the guard **failing open**. Each one
writes the ledger and `NEEDS_TRACE_REVIEW`, and produces this, not a yes/no:

```
EXPOSURE — Dear Lazy User, a secret-like value came back in a tool RESULT (`bash`): github-pat.
Session <id> (claude) is now marked NEEDS_TRACE_REVIEW; the guard will not clear it.
Evidence (redacted):
  1 match(es) in a result of 2 chars
  line 1 [github-pat]: deploy token: ***REDACTED:github-pat***

Options:
  1. Proceed — keep working; review the trace at the end: python3 …/guard.py review <id>
  2. Stop — end here; rotate the exposed credential now.
  3. Recommended — Proceed. Claude Code applied the redaction before the value reached
     the model (verified for Bash and MCP results); still run the trace review at the end.
  4. Evidence — export the exposed paragraphs of this session (redacted) to a file you can
     read: python3 …/guard.py review <id> --export
```

"Exposed" without evidence is not actionable, so every notice carries the
tool, the match count and a redacted one-line snippet per hit, and option 4
writes `exports/<session>-exposure.md`: the ledger rows, then for each flagged
tool call its input (redacted), why it was flagged, and the paragraphs around
each match (line before, matched line, line after, all redacted). Claude Code
`.jsonl` and Grok `updates.jsonl` transcripts are both understood. A secret
store's contents are never copied into the export. The file ends with a line
for the operator's verdict: real value (rotate) or false positive.

The recommendation depends on what happened: a redacted result on Claude Code
says proceed; a redacted result on a runtime whose redaction support is not
verified says check the transcript first; a secret-store read or a secret in
the input says stop and rotate, because those values cannot be pattern-redacted
or are already written.

**Agent procedure on an exposure notice (`immediate` interrupt only):** stop the task, show the
notice verbatim, ask the operator to pick 1, 2, 3 or 4 (with the ask-the-user tool
when there is one), and wait. If they pick 4, run the `--export` command and give
them the file path; do not paste the file into the chat. Do not retry, do not quote the value, never `--ack`.
In Claude Code and Grok the post hook returns `decision: block`, so the agent is
stopped by the runtime as well; in Cursor it arrives as context + user message.

**Agent procedure in `hybrid`/`notify` mode before a live call:** run it (in `hybrid`, a live-listed host or an irreversible action will be held by the hook — treat a reject as final). Say in one
line what you are about to do on the live host. The watcher agent below is for
`gate` mode, or for when the operator asks for a review before a specific write.

`$SKILL_DIR` is the folder that contains this `SKILL.md`.

| Runtime | Events | Config | What the runtime honours (verified / per its docs) |
|---------|--------|--------|------------------------------------------------------|
| **Grok** | `SessionStart` / `PreToolUse` / `PostToolUse` / `Stop` | `~/.grok/hooks/live-ops-guard.json` | pre: `decision` + `additionalContext`; post: `decision: block` + `additionalContext` + `updatedToolOutput` (must keep the tool's tagged shape; replaces the **model's** copy only, the session record keeps the original); `SessionStart` stdout ignored → the pending-review nag rides the first tool call; `Stop`: `additionalContext` keeps the agent one round to relay the summary, only when a review is due |
| **Claude Code** | `SessionStart` / `PreToolUse` / `PostToolUse` / `Stop` | `~/.claude/settings.json` (merged from `hooks/claude-code.json`) | pre: `permissionDecision` + `additionalContext` + `systemMessage`; post: `decision: block` + `additionalContext` + `updatedToolOutput` (verified: the transcript holds the redacted copy); `SessionStart`/`Stop`: `systemMessage` to the operator |
| **Cursor** | `sessionStart` / `beforeMCPExecution` / `beforeShellExecution` / `postToolUse` / `stop` | `~/.cursor/hooks.json` | before*: `permission` + `user_message` + `agent_message`; `postToolUse`: `additional_context` + `updated_mcp_tool_output` (**MCP only — a shell result cannot be redacted**, the notice says so); `sessionStart`: `additional_context`; `stop`: `followup_message` |

The **payload** decides which runtime an event came from, not the `--runtime` flag:
Grok loads `~/.claude/settings.json` and `~/.cursor/hooks.json` as well as its own
config, so one tool call can reach this script through two or three entries. The
guard dedupes by session + tool-use id (`dedupe.txt`), so the operator gets one
notice, one ledger row, and one summary per event whichever entry delivered it.

Same script for all three: `~/.grok/hooks/live-ops-guard/guard.py` (Claude Code
and Cursor get a one-line entry file that runs it). It flags:

- TeamCity writes
- **GitLab MCP writes** (`gitlab__*` in Grok, `mcp__gitlab__*` in Claude Code, Cursor MCP `create_*` / `merge_*` / … when the server is GitLab) and shell bypasses (`glab`, `curl` mutations to GitLab hosts)
- secret-like payloads (tokens, keys, JWTs, DB URLs with passwords)
- **secret-store reads**: `cat .env`, `~/.ssh/id_*`, `~/.aws/credentials`, `.netrc`, `gh auth token`, `op read`, `security find-*-password`, `vault kv get`, `kubectl get secret`, `echo $SOME_TOKEN`, bare `env` / `printenv`
- **every `ssh` / `scp` / `sftp` / `sshfs`** (any host). `rsync` when it is remote or uses ssh. Live-listed hosts and destructive remotes are extra findings, not a filter.

**Cursor gate:** `permission: ask` is enforced on `beforeMCPExecution` and `beforeShellExecution` only. Cursor `preToolUse` accepts `ask` but does not hold — do not treat it as the gate.

After `./install.sh --skill live-ops-guard --global`, the installer writes the Grok hook + agent, merges the Claude Code hook entries into `~/.claude/settings.json`, and merges the Cursor hook entries. Paste live SSH Host aliases into `~/.grok/hooks/live-ops-guard/live-hosts.txt` and self-hosted GitLab hostnames into `gitlab-hosts.txt` next to it (`gitlab.com` and any `gitlab.*` host are recognised without it). Do not invent a hostname, alias, or IP. Do not commit the filled files.

## When the operator hears about it

| `LIVE_OPS_GUARD_INTERRUPT` | Per event | End of turn |
|----------------------------|-----------|-------------|
| **`end-of-turn`** (default) | The exposure is recorded, redacted and noted to the **agent** only ("recorded; reported at the end of the turn; do not quote the value"). Nothing interrupts the operator. | The Stop hook asks the agent to **append one turn report** to its final reply: every event the guard saw since the last report (held / noted / redacted / exposure, with the redacted evidence line), whether the session is marked, and the four options. Once per turn, only when something new happened, never while the agent is already continuing. |
| `immediate` | The agent is **stopped** at each exposure and must present the notice and the options before continuing. | The classic session summary. |

The hybrid holds (live-listed host, irreversible GitLab/TeamCity) are permission asks in
both settings — those are the questions worth asking at the moment they happen.

**Agent procedure on a turn report (end-of-turn):** append it verbatim as the last section
of the reply and stop. Do not run `--ack`. If the operator answers with an option, act on
that option: 1 means carry on, 2 means stop and name what to rotate (kinds, never the value),
3 is the guard's recommendation, 4 means run the `--export` command and give the file path.

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
looking at the trace. An acknowledgement is remembered (`acked.jsonl`): the session's own
stop summary will not re-mark it unless a NEW exposure lands in its ledger.

```bash
python3 ~/.grok/hooks/live-ops-guard/guard.py review            # what is pending
python3 ~/.grok/hooks/live-ops-guard/guard.py review --last     # most recent flagged session
python3 ~/.grok/hooks/live-ops-guard/guard.py review <session>  # ledger + hand-off
python3 ~/.grok/hooks/live-ops-guard/guard.py review <session> --export [--out DIR]   # redacted paragraphs
python3 ~/.grok/hooks/live-ops-guard/guard.py review <session> --ack
```

`review <session>` prints the ledger rows, the transcript path if known, and
the exact next step: `/trace-analysis <transcript>` (or `/trace-watch <session>`
while it is still running). Rotate whatever the ledger says was exposed, then
`--ack`. `/live-ops-guard review` in a session means: run that command and
report the output; do not `--ack` on the operator's behalf.

### Why redact at all, if the value is already exposed

Redaction does not undo the exposure: the value hit the disk when the tool
ran, and on Grok the session record keeps it. Redaction is **containment**. An
unredacted value in the model's context gets copied onward — into commit
messages, PR bodies, files the agent writes, sub-agents, and MCP servers that
may belong to someone else. Replacing the model's copy stops that
amplification; on Claude Code the transcript holds the redacted copy too, so a
resume or an export does not carry it. The costs are that the model cannot
see a value it legitimately needed (use `${VAR}` instead), and that a false
positive corrupts what it reads — which is why the detectors have an eval
corpus (below). `LIVE_OPS_GUARD_REDACT=off` turns replacement off; the
notice then says so and recommends rotation, and the ledger and marker are
written exactly as before.

### Detection quality is measured

`evals/detection/cases.jsonl` is a labelled corpus (true positives, false
positives, near-misses, secret-store reads) and `scripts/eval-detection.py`
scores the detectors against it: precision and recall per kind, a `must`
tier that fails the test suite, a `stretch` tier that only reports. A miss or
a false alarm seen in a real session becomes a case first, then a fix. See
`evals/detection/README.md`.

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

## SSH — in `gate` mode, always trigger the watcher

(In `notify` mode the ssh runs and is recorded; skip to the next section.)
`ssh` is never "just a read". As soon as the command is `ssh` / `scp` / `sftp` / `sshfs` (or `rsync` over ssh):

1. **Stop.** Do not run Shell / `run_terminal_command` / `Bash` in the same turn you first invent the SSH.
2. **Spawn `live-ops-guard`** with the exact command (host, remote argv, why). Grok: `mcpInheritance` none. Cursor / Claude Code: child must not get Shell / Bash.
3. Show the operator the verdict. Wait for an explicit yes.
4. Only then run SSH. The hook will also ask — treat a reject as final.

This includes `ssh host uptime`, `ssh -N -L …`, interactive `ssh host`, and hosts **not** in `live-hosts.txt`.

## Secret reads

`cat .env`, `gh auth token`, `op read …`, `echo $API_KEY` and friends put a
secret into the transcript. In `gate` mode the hook asks first; in `notify`
mode the read runs and the post hook raises the exposure notice, because the
value is now in the trace either way. Prefer `${VAR}` references,
`-i $KEY_PATH`, and tools that consume a secret without printing it.

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

## Before any live write (`gate` mode)

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

## After a hook ask (`gate` mode)

If the runtime prompts because of `live-ops-guard`, treat a reject as final for that call. Change the call or ask the operator; do not immediately retry the same payload.

## Files

- Agent: `~/.grok/agents/live-ops-guard.md`
- Grok hook config: `~/.grok/hooks/live-ops-guard.json`
- Claude Code hook fragment: `$SKILL_DIR/hooks/claude-code.json` → merged into `~/.claude/settings.json`; entry `~/.claude/hooks/live-ops-guard.py`
- Cursor hook config: `~/.cursor/hooks.json`; entry `~/.cursor/hooks/live-ops-guard.py`
- Hook script: `~/.grok/hooks/live-ops-guard/guard.py`
- Live hosts: `~/.grok/hooks/live-ops-guard/live-hosts.txt`; GitLab hosts: `gitlab-hosts.txt`
- Ledger / marker / acks / reports / exports: `~/.grok/hooks/live-ops-guard/ledger.jsonl`, `NEEDS_TRACE_REVIEW`, `acked.jsonl`, `reported.jsonl`, `exports/<session>-exposure.md`
- Self-test: `bash $SKILL_DIR/scripts/test-guard.sh` (runs `hooks/test_guard.py` in a throwaway home)
