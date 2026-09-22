#!/usr/bin/env python3
"""Self-test for live-ops-guard classify/pre/post. No network. No secrets printed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("live_ops_guard", ROOT / "guard.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

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
                "tool_input": {
                    "project_id": "788",
                    "noteable_type": "merge_request",
                    "noteable_iid": "470",
                    "body": "hi",
                },
            },
        },
        True,
    ),
    ("merge", {"toolName": "gitlab__merge_merge_request", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    ("approve", {"toolName": "gitlab__approve_merge_request", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    (
        "update close",
        {
            "toolName": "gitlab__update_merge_request",
            "toolInput": {"project_id": "788", "merge_request_iid": "470", "state_event": "close"},
        },
        True,
    ),
    ("delete issue", {"toolName": "gitlab__delete_issue", "toolInput": {"project_id": "788", "issue_iid": "1"}}, True),
    ("bulk publish", {"toolName": "gitlab__bulk_publish_draft_notes", "toolInput": {"project_id": "788", "merge_request_iid": "470"}}, True),
    (
        "dry_run patch",
        {
            "toolName": "gitlab__update_issue_description_patch",
            "toolInput": {
                "project_id": "788",
                "issue_iid": "1",
                "patch_type": "search_replace",
                "patch": "a",
                "dry_run": True,
            },
        },
        False,
    ),
    (
        "teamcity post",
        {"toolName": "teamcity__teamcity_rest_post", "toolInput": {"path": "/app/rest/buildQueue", "body": "{}"}},
        True,
    ),
    ("glab merge", {"toolName": "run_terminal_command", "toolInput": {"command": "glab mr merge 470"}}, True),
    (
        "curl get gitlab",
        {"toolName": "run_terminal_command", "toolInput": {"command": "curl -sS https://nova.teachx.ai/api/v4/projects/788"}},
        False,
    ),
    (
        "curl post gitlab",
        {
            "toolName": "run_terminal_command",
            "toolInput": {
                "command": "curl -X POST https://nova.teachx.ai/api/v4/projects/788/merge_requests/470/notes -d body=hi"
            },
        },
        True,
    ),
    (
        "cursor teamcity post",
        {
            "hook_event_name": "beforeMCPExecution",
            "cursor_version": "1.0.0",
            "mcp_server_name": "teamcity",
            "tool_name": "teamcity_rest_post",
            "tool_input": '{"path":"/app/rest/buildQueue","body":"{}"}',
        },
        True,
    ),
    (
        "cursor teamcity get",
        {
            "hook_event_name": "beforeMCPExecution",
            "cursor_version": "1.0.0",
            "mcp_server_name": "teamcity",
            "tool_name": "teamcity_rest_get",
            "tool_input": '{"path":"/app/rest/builds"}',
        },
        False,
    ),
    (
        "cursor youtrack create_issue not gitlab",
        {
            "hook_event_name": "beforeMCPExecution",
            "cursor_version": "1.0.0",
            "mcp_server_name": "youtrack PHX",
            "tool_name": "create_issue",
            "tool_input": '{"summary":"x"}',
        },
        False,
    ),
    (
        "cursor gitlab create_note",
        {
            "hook_event_name": "beforeMCPExecution",
            "cursor_version": "1.0.0",
            "mcp_server_name": "gitlab",
            "tool_name": "create_note",
            "tool_input": '{"project_id":"788","noteable_iid":"470","body":"hi"}',
        },
        True,
    ),
    (
        "cursor CallDynamicTool teamcity post",
        {
            "hook_event_name": "preToolUse",
            "cursor_version": "1.0.0",
            "tool_name": "CallDynamicTool",
            "tool_input": {
                "namespace": "user-teamcity",
                "toolName": "teamcity_rest_post",
                "arguments": {"path": "/app/rest/buildQueue", "body": "{}"},
            },
        },
        True,
    ),
    (
        "cursor glab merge shell",
        {
            "hook_event_name": "beforeShellExecution",
            "cursor_version": "1.0.0",
            "command": "glab mr merge 470",
        },
        True,
    ),
    (
        "cursor mcp launch command is not shell",
        {
            "hook_event_name": "beforeMCPExecution",
            "cursor_version": "1.0.0",
            "mcp_server_name": "context7",
            "tool_name": "query-docs",
            "tool_input": '{"library":"x"}',
            "command": "npx ssh rm -rf /",
        },
        False,
    ),
    (
        "cursor ssh live host",
        {
            "hook_event_name": "beforeShellExecution",
            "cursor_version": "1.0.0",
            "command": "ssh teamcity 'systemctl restart teamcity'",
        },
        True,
    ),
    (
        "ssh unknown host uptime still asks",
        {
            "hook_event_name": "beforeShellExecution",
            "cursor_version": "1.0.0",
            "command": "ssh other-box uptime",
        },
        True,
    ),
    (
        "interactive ssh any host asks",
        {"toolName": "run_terminal_command", "toolInput": {"command": "ssh jump.example"}},
        True,
    ),
    (
        "live host read-only ssh still asks",
        {"toolName": "run_terminal_command", "toolInput": {"command": "ssh teamcity uptime"}},
        True,
    ),
    (
        "scp any host asks",
        {
            "hook_event_name": "beforeShellExecution",
            "cursor_version": "1.0.0",
            "command": "scp file.txt jump.example:/tmp/",
        },
        True,
    ),
    (
        "rsync local only does not ask",
        {"toolName": "run_terminal_command", "toolInput": {"command": "rsync -av ./src/ ./dst/"}},
        False,
    ),
]


def _is_ask(result: dict) -> bool:
    return result.get("decision") == "ask" or result.get("permission") == "ask"


def main() -> int:
    failed = 0
    for label, event, expect_ask in CASES:
        result = mod.pre_decision(event)
        got_ask = _is_ask(result)
        ok = got_ask == expect_ask
        if not ok:
            failed += 1
            print(f"FAIL {label}: result={result} findings={mod.classify(event)}")
        else:
            print(f"OK   {label}")
        if "cursor_version" in event or str(event.get("hook_event_name") or "").startswith("before"):
            if got_ask and result.get("permission") != "ask":
                failed += 1
                print(f"FAIL {label}: Cursor payload must return permission=ask, got {result}")
    # post redaction smoke (synthetic pat shape only)
    fake = "prefix " + "glpat-" + ("A" * 24) + " suffix"
    post = mod.post_decision({"toolName": "gitlab__list_merge_requests", "toolResult": fake})
    if "additionalContext" not in post.get("hookSpecificOutput", {}):
        print("FAIL post redaction missing context")
        failed += 1
    else:
        print("OK   post redaction")
    cursor_post = mod.post_decision(
        {
            "hook_event_name": "postToolUse",
            "cursor_version": "1.0.0",
            "mcp_server_name": "gitlab",
            "tool_name": "list_merge_requests",
            "tool_output": fake,
        }
    )
    if "additional_context" not in cursor_post:
        print("FAIL cursor post redaction missing additional_context")
        failed += 1
    else:
        print("OK   cursor post redaction")
    print(f"failed={failed}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
