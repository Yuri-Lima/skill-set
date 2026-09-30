#!/usr/bin/env python3
"""Self-test for live-ops-guard classify/pre/post/start/stop/review.

No network. No secrets printed. Runs against a throwaway LIVE_OPS_GUARD_HOME so
the real ledger and marker are never touched."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="live-ops-guard-test-")
os.environ["LIVE_OPS_GUARD_HOME"] = HOME
os.environ.pop("LIVE_OPS_GUARD_OPERATOR", None)

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("live_ops_guard", ROOT / "guard.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FAKE_PAT = "ghp_" + "A" * 30  # synthetic shape, not a real token
FAKE_GLPAT = "glpat-" + "B" * 24

# label, event, expect_ask
CASES: list[tuple[str, dict, bool]] = [
    ("read list", {"toolName": "gitlab__list_merge_requests", "toolInput": {"project_id": "788"}}, False),
    (
        "read get via use_tool",
        {
            "toolName": "use_tool",
            "toolInput": {
                "tool_name": "gitlab__get_merge_request",
                "tool_input": {"project_id": "788", "merge_request_iid": "470"},
            },
        },
        False,
    ),
    ("read notes", {"toolName": "gitlab__get_merge_request_notes", "toolInput": {"project_id": "788", "merge_request_iid": "1"}}, False),
    ("read discussions", {"toolName": "gitlab__mr_discussions", "toolInput": {"project_id": "788", "merge_request_iid": "1"}}, False),
    ("read whoami", {"toolName": "gitlab__whoami", "toolInput": {}}, False),
    (
        "write create note",
        {
            "toolName": "use_tool",
            "toolInput": {
                "tool_name": "gitlab__create_note",
                "tool_input": {"project_id": "788", "noteable_type": "merge_request", "noteable_iid": "470", "body": "hi"},
            },
        },
        True,
    ),
    ("merge", {"toolName": "gitlab__merge_merge_request", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    ("approve", {"toolName": "gitlab__approve_merge_request", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    (
        "update close",
        {"toolName": "gitlab__update_merge_request", "toolInput": {"project_id": "788", "merge_request_iid": "470", "state_event": "close"}},
        True,
    ),
    ("delete issue", {"toolName": "gitlab__delete_issue", "toolInput": {"project_id": "788", "issue_iid": "1"}}, True),
    ("bulk publish", {"toolName": "gitlab__bulk_publish_draft_notes", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    (
        "dry_run patch",
        {
            "toolName": "gitlab__update_issue_description_patch",
            "toolInput": {"project_id": "788", "issue_iid": "1", "patch_type": "search_replace", "patch": "a", "dry_run": True},
        },
        False,
    ),
    ("teamcity post", {"toolName": "teamcity__teamcity_rest_post", "toolInput": {"path": "/app/rest/buildQueue", "body": "{}"}}, True),
    ("glab merge", {"toolName": "run_terminal_command", "toolInput": {"command": "glab mr merge 470"}}, True),
    (
        "curl get gitlab (generic gitlab. host)",
        {"toolName": "run_terminal_command", "toolInput": {"command": "curl -sS https://gitlab.example.com/api/v4/projects/788"}},
        False,
    ),
    (
        "curl post gitlab (generic gitlab. host)",
        {"toolName": "run_terminal_command", "toolInput": {"command": "curl -X POST https://gitlab.example.com/api/v4/projects/788/merge_requests/470/notes -d body=hi"}},
        True,
    ),
    (
        "curl post to a host listed in gitlab-hosts.txt",
        {"toolName": "run_terminal_command", "toolInput": {"command": "curl -X POST https://code.internal.test/api/v4/projects/1/issues -d title=x"}},
        True,
    ),
    (
        "curl post to an unlisted non-gitlab host is not a gitlab write",
        {"toolName": "run_terminal_command", "toolInput": {"command": "curl -X POST https://api.example.org/v1/things -d a=b"}},
        False,
    ),
    (
        "cursor teamcity post",
        {"hook_event_name": "beforeMCPExecution", "cursor_version": "1.0.0", "mcp_server_name": "teamcity", "tool_name": "teamcity_rest_post", "tool_input": '{"path":"/app/rest/buildQueue","body":"{}"}'},
        True,
    ),
    (
        "cursor teamcity get",
        {"hook_event_name": "beforeMCPExecution", "cursor_version": "1.0.0", "mcp_server_name": "teamcity", "tool_name": "teamcity_rest_get", "tool_input": '{"path":"/app/rest/builds"}'},
        False,
    ),
    (
        "cursor youtrack create_issue not gitlab",
        {"hook_event_name": "beforeMCPExecution", "cursor_version": "1.0.0", "mcp_server_name": "youtrack PHX", "tool_name": "create_issue", "tool_input": '{"summary":"x"}'},
        False,
    ),
    (
        "cursor gitlab create_note",
        {"hook_event_name": "beforeMCPExecution", "cursor_version": "1.0.0", "mcp_server_name": "gitlab", "tool_name": "create_note", "tool_input": '{"project_id":"788","noteable_iid":"470","body":"hi"}'},
        True,
    ),
    (
        "cursor CallDynamicTool teamcity post",
        {
            "hook_event_name": "preToolUse",
            "cursor_version": "1.0.0",
            "tool_name": "CallDynamicTool",
            "tool_input": {"namespace": "user-teamcity", "toolName": "teamcity_rest_post", "arguments": {"path": "/app/rest/buildQueue", "body": "{}"}},
        },
        True,
    ),
    ("cursor glab merge shell", {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0.0", "command": "glab mr merge 470"}, True),
    (
        "cursor mcp launch command is not shell",
        {"hook_event_name": "beforeMCPExecution", "cursor_version": "1.0.0", "mcp_server_name": "context7", "tool_name": "query-docs", "tool_input": '{"library":"x"}', "command": "npx ssh rm -rf /"},
        False,
    ),
    ("cursor ssh live host", {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0.0", "command": "ssh teamcity 'systemctl restart teamcity'"}, True),
    ("ssh unknown host uptime still asks", {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0.0", "command": "ssh other-box uptime"}, True),
    ("interactive ssh any host asks", {"toolName": "run_terminal_command", "toolInput": {"command": "ssh jump.example"}}, True),
    ("live host read-only ssh still asks", {"toolName": "run_terminal_command", "toolInput": {"command": "ssh teamcity uptime"}}, True),
    ("scp any host asks", {"hook_event_name": "beforeShellExecution", "cursor_version": "1.0.0", "command": "scp file.txt jump.example:/tmp/"}, True),
    ("rsync local only does not ask", {"toolName": "run_terminal_command", "toolInput": {"command": "rsync -av ./src/ ./dst/"}}, False),
    # --- Claude Code shapes ---
    (
        "claude Bash ssh asks",
        {"session_id": "s-claude-1", "transcript_path": "/tmp/t.jsonl", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ssh box uptime"}},
        True,
    ),
    (
        "claude mcp__gitlab__create_note asks",
        {"session_id": "s-claude-1", "transcript_path": "/tmp/t.jsonl", "hook_event_name": "PreToolUse", "tool_name": "mcp__gitlab__create_note", "tool_input": {"project_id": "1", "noteable_iid": "2", "body": "x"}},
        True,
    ),
    (
        "claude mcp__gitlab__list_issues allows",
        {"session_id": "s-claude-1", "transcript_path": "/tmp/t.jsonl", "hook_event_name": "PreToolUse", "tool_name": "mcp__gitlab__list_issues", "tool_input": {"project_id": "1"}},
        False,
    ),
    (
        "claude mcp__youtrack-phx__create_issue is not gitlab",
        {"session_id": "s-claude-1", "transcript_path": "/tmp/t.jsonl", "hook_event_name": "PreToolUse", "tool_name": "mcp__youtrack-phx__create_issue", "tool_input": {"summary": "x"}},
        False,
    ),
    # --- secret-store reads (item 6) ---
    ("secret-read cat .env", {"toolName": "run_terminal_command", "toolInput": {"command": "cat .env"}}, True),
    ("secret-read cat .env.local", {"toolName": "run_terminal_command", "toolInput": {"command": "cat .env.local"}}, True),
    ("secret-read cat .env.example is fine", {"toolName": "run_terminal_command", "toolInput": {"command": "cat .env.example"}}, False),
    ("secret-read ssh private key", {"toolName": "run_terminal_command", "toolInput": {"command": "cat ~/.ssh/id_ed25519"}}, True),
    ("secret-read ssh public key is fine", {"toolName": "run_terminal_command", "toolInput": {"command": "cat ~/.ssh/id_ed25519.pub"}}, False),
    ("secret-read aws credentials", {"toolName": "run_terminal_command", "toolInput": {"command": "cat ~/.aws/credentials"}}, True),
    ("secret-read gh auth token", {"toolName": "run_terminal_command", "toolInput": {"command": "gh auth token"}}, True),
    ("secret-read op read", {"toolName": "run_terminal_command", "toolInput": {"command": "op read op://vault/item/password"}}, True),
    ("secret-read keychain", {"toolName": "run_terminal_command", "toolInput": {"command": "security find-generic-password -w -s foo"}}, True),
    ("secret-read echo $GITHUB_TOKEN", {"toolName": "run_terminal_command", "toolInput": {"command": "echo $GITHUB_TOKEN"}}, True),
    ("secret-read base64 .netrc", {"toolName": "run_terminal_command", "toolInput": {"command": "base64 ~/.netrc"}}, True),
    ("secret-read bare env dump", {"toolName": "run_terminal_command", "toolInput": {"command": "env"}}, True),
    ("env prefix on a command is not a dump", {"toolName": "run_terminal_command", "toolInput": {"command": "env FOO=1 node x.js"}}, False),
    ("ls of a project dir is fine", {"toolName": "run_terminal_command", "toolInput": {"command": "ls -la src"}}, False),
    ("git status is fine", {"toolName": "run_terminal_command", "toolInput": {"command": "git status && git log -3"}}, False),
    # --- placeholder overlap only (item 8) ---
    (
        "real token next to an html tag still asks",
        {"toolName": "run_terminal_command", "toolInput": {"command": f'curl -d "<b>hi</b> {FAKE_PAT}" https://x'}},
        True,
    ),
    ("Bearer ${VAR} placeholder is not a literal secret", {"toolName": "run_terminal_command", "toolInput": {"command": "printf '%s' \"Bearer ${TC_AUTH_TOKEN}\""}}, False),
    ("echo of a secret variable is exposure even with a placeholder shape", {"toolName": "run_terminal_command", "toolInput": {"command": "echo Bearer ${TC_AUTH_TOKEN}"}}, True),
    ("token=<your-token-here> placeholder allows", {"toolName": "run_terminal_command", "toolInput": {"command": "curl -H 'PRIVATE-TOKEN: <your-token-here>' https://gitlab.example.com/api/v4/user"}}, False),
    # --- coerced shapes (item 7) ---
    ("list-shaped toolInput with ssh still asks", {"toolName": "run_terminal_command", "toolInput": ["ssh", "box", "uptime"]}, True),
    ("string-shaped toolInput with ssh still asks", {"toolName": "run_terminal_command", "toolInput": "ssh box uptime"}, True),
]


def _is_ask(result: dict) -> bool:
    if result.get("decision") == "ask" or result.get("permission") == "ask":
        return True
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "ask"


def _ask_text(result: dict) -> str:
    return json.dumps(result)


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    failed = 0

    def check(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failed
        if ok:
            print(f"OK   {label}")
        else:
            failed += 1
            print(f"FAIL {label}: {detail}")

    Path(HOME, "gitlab-hosts.txt").write_text("# test\ncode.internal.test\n", encoding="utf-8")

    for label, event, expect_ask in CASES:
        result = mod.pre_decision(event)
        got_ask = _is_ask(result)
        check(got_ask == expect_ask, label, f"result={result} findings={mod.classify(event)}")
        if "cursor_version" in event or str(event.get("hook_event_name") or "").startswith("before"):
            if got_ask:
                check(result.get("permission") == "ask", f"{label} (cursor shape)", str(result))
        if event.get("transcript_path"):
            if got_ask:
                check("permissionDecision" in result.get("hookSpecificOutput", {}), f"{label} (claude shape)", str(result))
            else:
                check(result == {}, f"{label} (claude allow is silent)", str(result))

    echo_findings = mod.classify({"toolName": "run_terminal_command", "toolInput": {"command": "echo Bearer ${TC_AUTH_TOKEN}"}})
    check(not any(f.startswith("secret(") for f in echo_findings) and any(f.startswith("secret-read") for f in echo_findings), "placeholder value is a read, not a literal secret", str(echo_findings))

    # --- item 5: nothing leaving the guard carries the secret ---
    ev = {"toolName": "run_terminal_command", "toolInput": {"command": f'ssh box "echo {FAKE_PAT} | tee /etc/app.token"'}}
    res = mod.pre_decision(ev)
    check(_is_ask(res) and "ghp_AAAA" not in _ask_text(res), "ask reason never echoes the secret", _ask_text(res))
    check("***REDACTED:github-pat***" in _ask_text(res), "ask reason shows the redaction marker", _ask_text(res))

    # --- item 5: shell (string) results get updatedToolOutput too ---
    post = mod.post_decision({"toolName": "run_terminal_command", "toolInput": {"command": "cat notes.txt"}, "toolResult": f"token {FAKE_GLPAT} end"})
    hso = post.get("hookSpecificOutput", {})
    check("additionalContext" in hso, "post redaction context")
    check("updatedToolOutput" in hso and "glpat-BBBB" not in json.dumps(post), "post string result redacted", json.dumps(post))
    check("STILL in the transcript" in hso.get("additionalContext", ""), "post note is honest about runtime support")

    cursor_post = mod.post_decision({"hook_event_name": "postToolUse", "cursor_version": "1.0.0", "mcp_server_name": "gitlab", "tool_name": "list_merge_requests", "tool_output": f"prefix {FAKE_GLPAT} suffix"})
    check("additional_context" in cursor_post and "glpat-BBBB" not in json.dumps(cursor_post), "cursor post redaction")

    # --- item 6: a secret-store read is exposure even when the output matches no pattern ---
    before = len(_lines(Path(HOME, "NEEDS_TRACE_REVIEW")))
    post_read = mod.post_decision({"session_id": "s-read", "transcript_path": "/tmp/t.jsonl", "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "cat .env"}, "tool_response": "DB_HOST=localhost\nDB_PASS=short\n"})
    check(bool(post_read), "secret-store read produces a post note even with no pattern hit", str(post_read))
    marks = _lines(Path(HOME, "NEEDS_TRACE_REVIEW"))
    check(len(marks) == before + 1 and marks[-1]["reason"] == "secret-store-read", "secret-store read writes the marker", str(marks[-1:]))

    # --- item 1: ledger has kinds and never the payload ---
    ledger = _lines(Path(HOME, "ledger.jsonl"))
    check(bool(ledger), "ledger written")
    raw = Path(HOME, "ledger.jsonl").read_text(encoding="utf-8") + Path(HOME, "NEEDS_TRACE_REVIEW").read_text(encoding="utf-8")
    check("ghp_AAAA" not in raw and "glpat-BBBB" not in raw and "DB_PASS" not in raw, "ledger and marker never contain payloads")
    ssh_rows = [r for r in ledger if "ssh" in r.get("kinds", []) or "ssh-destructive" in r.get("kinds", [])]
    check(bool(ssh_rows), "ledger tags ssh kinds")
    check(any(r.get("shape") == "coerced" for r in ledger), "ledger records coerced payload shapes")

    # --- item 7: fail-open is loud and leaves a trail ---
    fo = mod._fail_open({"session_id": "s-fail", "transcript_path": "/tmp/t.jsonl"}, "unit test")
    check("could NOT evaluate" in json.dumps(fo), "fail-open message is loud", json.dumps(fo))
    check(fo.get("hookSpecificOutput", {}).get("permissionDecision") is None, "fail-open still allows")
    marks = _lines(Path(HOME, "NEEDS_TRACE_REVIEW"))
    check(any(m["session"] == "s-fail" and m["reason"] == "guard-fail-open" for m in marks), "fail-open writes the marker")
    check(any(r["session"] == "s-fail" and r["decision"] == "fail-open" for r in _lines(Path(HOME, "ledger.jsonl"))), "fail-open writes the ledger")
    fo_grok = mod._fail_open({"sessionId": "s-fail-grok"}, "unit test")
    check(fo_grok.get("decision") == "allow" and "could NOT evaluate" in fo_grok.get("reason", ""), "grok fail-open shape")
    fo_cursor = mod._fail_open({"cursor_version": "1.0.0", "conversation_id": "c1"}, "unit test")
    check(fo_cursor.get("permission") == "allow" and "could NOT evaluate" in fo_cursor.get("user_message", ""), "cursor fail-open shape")

    # main() with unreadable stdin is the same loud path
    sys.stdin = io.StringIO("{not json")
    sys.argv = ["guard.py", "--event", "pre"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    out = json.loads(buf.getvalue())
    check(out.get("decision") == "allow" and "could NOT evaluate" in out.get("reason", ""), "unreadable payload is loud fail-open", buf.getvalue())
    sys.stdin = sys.__stdin__

    # --- item 2: stop summary counts match the ledger ---
    sid = "s-summary"
    base = {"session_id": sid, "transcript_path": "/tmp/s.jsonl", "hook_event_name": "PreToolUse", "tool_name": "Bash"}
    mod.pre_decision({**base, "tool_input": {"command": "ssh box uptime"}})
    mod.pre_decision({**base, "tool_input": {"command": "ssh box2 uptime"}})
    mod.pre_decision({**base, "tool_input": {"command": "cat .env"}})
    mod.post_decision({**base, "hook_event_name": "PostToolUse", "tool_input": {"command": "cat .env"}, "tool_response": "X=1"})
    mod.post_decision({**base, "hook_event_name": "PostToolUse", "tool_input": {"command": "cat log.txt"}, "tool_response": f"k {FAKE_PAT}"})
    mod._fail_open({**base}, "unit")
    stop = mod.stop_decision({**base, "hook_event_name": "Stop"})
    text = stop.get("systemMessage", "")
    rows = mod.ledger_for_session(sid)
    counts = mod.session_counts(rows)
    check(counts == {"asked": 3, "redactions": 1, "secret_reads": 2, "fail_opens": 1, "coerced": 0}, "session counts", str(counts))
    check(f"guarded calls asked: {counts['asked']}" in text and f"secret-like values redacted: {counts['redactions']}" in text, "stop summary matches ledger", text)
    check("Trace review required: YES" in text and f"review {sid}" in text, "stop summary points to review", text)
    clean = mod.stop_decision({"session_id": "s-clean", "transcript_path": "/tmp/c.jsonl", "hook_event_name": "Stop"})
    check(clean == {}, "clean session stop is silent", str(clean))

    # --- item 3: session start surfaces the marker ---
    start = mod.start_decision({"session_id": "s-new", "transcript_path": "/tmp/n.jsonl", "hook_event_name": "SessionStart"})
    check("need a trace review" in start.get("systemMessage", "") and sid in start.get("systemMessage", ""), "session start nags about the marker", str(start))
    check(start.get("hookSpecificOutput", {}).get("hookEventName") == "SessionStart", "session start claude shape")
    start_cursor = mod.start_decision({"cursor_version": "1.0.0", "hook_event_name": "sessionStart"})
    check("additional_context" in start_cursor, "session start cursor shape")

    # --- item 4: review prints the hand-off and --ack clears only that session ---
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = mod.review_cli([sid])
    text = buf.getvalue()
    check(code == 0 and "/trace-analysis /tmp/s.jsonl" in text and f"/trace-watch {sid}" in text, "review hands off to trace analysis", text)
    check("ghp_AAAA" not in text, "review output never shows the secret")
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.review_cli([sid, "--ack"])
    marks = _lines(Path(HOME, "NEEDS_TRACE_REVIEW"))
    check(not any(m["session"] == sid for m in marks), "--ack removes the session from the marker")
    check(any(m["session"] == "s-fail" for m in marks), "--ack leaves other sessions in the marker")
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.review_cli([])
    check("s-fail" in buf.getvalue(), "review without a session lists what is pending")

    # --- item 2 (user request): no hard-coded host or person in the guard ---
    src = (ROOT / "guard.py").read_text(encoding="utf-8")
    banned = ("nova." + "teachx", "yu" + "ri")  # spelled apart so this file is not itself a hit
    check(not any(b in src.lower() for b in banned), "guard.py carries no hard-coded host or name")
    check(mod.OPERATOR == "Dear Lazy User", "default operator salutation")

    print(f"failed={failed}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
