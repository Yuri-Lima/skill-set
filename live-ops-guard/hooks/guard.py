#!/usr/bin/env python3
"""Live-ops guard: ask before live writes, leaked secrets, or irreversible calls.

Covers TeamCity REST writes, GitLab MCP / API mutations, leaked secrets,
destructive SSH to listed hosts, and suspicious shell.

Speaks both Grok PreToolUse/PostToolUse and Cursor
beforeMCPExecution / beforeShellExecution / postToolUse.

Reads one hook event JSON from stdin. Prints a decision JSON to stdout.
Never logs raw payloads. Fail-open (defer/allow) on parse/runtime errors.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

PLACEHOLDER_RE = re.compile(
    r"\$\{[^}]+\}|<[^>]{0,40}>|\b(YOUR_TOKEN|CHANGEME|REDACTED|xxx+|TODO|FIXME)\b",
    re.IGNORECASE,
)

# (kind, compiled pattern) — value-like matches only, not the word "token" alone.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----")),
    ("gitlab-pat", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("github-pat", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("github-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("xai-key", re.compile(r"\bxai-[A-Za-z0-9]{20,}")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+(?!\$\{)([A-Za-z0-9._\-+/=]{24,})"),
    ),
    (
        "assignment-secret",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|private[_-]?key)"
            r"\s*[:=]\s*['\"]?(?!\$\{)([^\s'\"\\]{16,})"
        ),
    ),
    (
        "db-url-password",
        re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:]+:[^/\s@]{8,}@"),
    ),
]

TEAMCITY_WRITE_TOOLS = {
    "teamcity__teamcity_rest_post",
    "teamcity__teamcity_rest_put",
    "teamcity__teamcity_rest_delete",
    "teamcity_rest_post",
    "teamcity_rest_put",
    "teamcity_rest_delete",
}

TEAMCITY_WRITE_BARE = {
    "teamcity_rest_post": "teamcity__teamcity_rest_post",
    "teamcity_rest_put": "teamcity__teamcity_rest_put",
    "teamcity_rest_delete": "teamcity__teamcity_rest_delete",
}

CURSOR_PRE_EVENTS = {
    "pretooluse",
    "beforeshellexecution",
    "beforemcpexecution",
}
CURSOR_POST_EVENTS = {
    "posttooluse",
    "aftershellexecution",
    "aftermcpexecution",
    "posttoolusefailure",
}

# GitLab MCP (nova.teachx.ai and any gitlab__* server). Reads stay allow;
# mutations ask Yuri — same policy as TeamCity live writes.
GITLAB_TOOL_PREFIXES = ("gitlab__",)

# Tool-name tokens that mean a side-effecting GitLab call.
GITLAB_WRITE_TOKENS = (
    "create",
    "update",
    "delete",
    "merge",
    "approve",
    "unapprove",
    "publish",
    "upload",
    "award",
    "invite",
    "revoke",
    "cancel",
    "retry",
    "play",
    "promote",
    "protect",
    "unprotect",
    "transfer",
    "move",
    "fork",
    "rebase",
    "cherry_pick",
    "cherry-pick",
    "revert",
    "subscribe",
    "unsubscribe",
    "set_",
    "add_",
    "remove_",
    "edit_",
    "patch",
    "bulk_",
    "accept",
    "reject",
    "ban",
    "block",
    "unblock",
    "share",
    "unshare",
    "start_",
    "stop_",
    "trigger",
    "export",  # can create/export jobs with side effects
    "import",
)

# Explicit high-risk GitLab actions (always irreversible-ish).
GITLAB_IRREVERSIBLE_TOKENS = (
    "merge_merge_request",
    "merge_mr",
    "delete_issue",
    "delete_merge_request",
    "delete_project",
    "delete_group",
    "delete_user",
    "delete_pipeline",
    "delete_branch",
    "delete_tag",
    "delete_repository",
    "delete_file",
    "remove_project",
    "remove_group",
)

# Shell: glab / curl hitting GitLab hosts with mutating verbs.
GITLAB_HOST_RE = re.compile(
    r"(?i)(nova\.teachx\.ai|gitlab\.com|gitlab\.)"
)
GITLAB_HTTP_MUTATION_RE = re.compile(
    r"(?i)\b(curl|http|https|wget)\b[^\n]*\b(-X|--request)\s*(POST|PUT|PATCH|DELETE)\b"
)
GITLAB_GLAB_MUTATION_RE = re.compile(
    r"(?i)\bglab\b[^\n]*\b("
    r"mr\s+(merge|create|close|reopen|approve|revoke|update|note|todo)|"
    r"issue\s+(create|close|reopen|update|note|delete)|"
    r"api\s+(-X\s*)?(POST|PUT|PATCH|DELETE)|"
    r"ci\s+(run|retry|cancel|delete)|"
    r"variable\s+(set|delete)|"
    r"repo\s+(create|delete)|"
    r"label\s+(create|delete)|"
    r"release\s+(create|delete)|"
    r"schedule\s+(create|delete|update)"
    r")"
)

# Paths that cannot be undone, or change live CI shape.
IRREVERSIBLE_PATH = re.compile(
    r"(?i)(/app/rest/(projects|buildTypes|vcs-roots|agents|users|groups|cloud)"
    r"|/steps(?:/|$)|/features(?:/|$)|unregister|delete)",
)

SUSPICIOUS_SHELL = re.compile(
    r"(?i)("
    r"rm\s+-rf\s+(/|~|\$HOME|\.)"
    r"|drop\s+(database|schema|table)"
    r"|kubectl\s+delete"
    r"|git\s+push\s+.*--force"
    r"|curl\s+[^\n]*(Authorization|api[_-]?key|token=)"
    r"|printenv|env\s*\|"
    r"|history\s*\|"
    r")"
)

HOSTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live-hosts.txt")

REMOTE_ACCESS_CMDS = ("ssh", "scp", "rsync", "sftp", "sshfs")

# Destructive on a remote box (or a copy that overwrites remote files).
DESTRUCTIVE_REMOTE = re.compile(
    r"(?i)("
    r"\brm\s+(-[a-zA-Z]*f|-rf|-fr|--recursive)\b"
    r"|\bshred\b|\bmkfs\b|\bwipefs\b"
    r"|\bdd\s+[^\n]*\bof=/dev/"
    r"|\b(reboot|shutdown|halt|poweroff)\b"
    r"|\bsystemctl\s+(stop|restart|disable|mask|isolate|rescue|emergency)\b"
    r"|\bservice\s+\S+\s+(stop|restart)\b"
    r"|\bdocker\s+(rm|rmi|system\s+prune|compose\s+down)\b"
    r"|\bpodman\s+(rm|rmi|system\s+prune)\b"
    r"|\b(userdel|passwd|visudo|crontab\s+-)\b"
    r"|\b(iptables\s+-F|ufw\s+disable)\b"
    r"|\b(apt(-get)?|yum|dnf|zypper)\s+(remove|purge|erase)\b"
    r"|\bkill\s+(-9\s+)?-?1\b"
    r"|\bdrop\s+(database|schema|table)\b"
    r"|>(>?)\s*/(etc|opt|data|var)/"
    r"|tee\s+(-a\s+)?/(etc|opt|data|var)/"
    r"|sed\s+-i\b"
    r")"
)

TEAMCITY_DATA_PATH = re.compile(
    r"(?i)("
    r"/opt/teamcity"
    r"|/data/teamcity"
    r"|/\.BuildServer"
    r"|/var/lib/teamcity"
    r"|internal\.properties"
    r"|buildAgent"
    r"|TeamCity/data"
    r")"
)

READ_ONLY_REMOTE = re.compile(
    r"(?i)^("
    r"true|false|echo|printf|date|uptime|hostname|uname|whoami|id|pwd"
    r"|df|du|free|ps|top\s+-b\s+-n\s*1"
    r"|ls|stat|file|wc|head|tail|cat|less|more|find|locate"
    r"|journalctl|dmesg"
    r"|systemctl\s+(status|is-active|is-enabled|show|list-units|cat)"
    r"|docker\s+(ps|logs|inspect|images|info)"
    r"|ip(\s+addr)?|ss|netstat"
    r"|git\s+(status|log|diff|show|rev-parse|branch)"
    r")(\s|$)"
)

SSH_OPTION_TAKES_VALUE = {
    "b", "c", "D", "E", "e", "F", "I", "i", "J", "L", "l", "m", "O", "o",
    "p", "Q", "R", "S", "W", "w",
}

SCP_OPTION_TAKES_VALUE = {
    "c", "F", "i", "J", "l", "o", "P", "S",
}


def load_live_hosts() -> set[str]:
    hosts: set[str] = set()
    try:
        with open(HOSTS_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                hosts.add(line.lower())
                # user@host and host:port collapse to host for matching
                if "@" in line:
                    hosts.add(line.split("@", 1)[1].lower())
                if ":" in line and not line.count(":") > 1:
                    hosts.add(line.rsplit(":", 1)[0].lower())
    except OSError:
        pass
    return hosts


def split_shell_words(command: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and i + 1 < len(command):
                current.append(command[i + 1])
                i += 2
                continue
            else:
                current.append(ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch.isspace():
            if current:
                words.append("".join(current))
                current = []
        elif ch == "\\" and i + 1 < len(command):
            current.append(command[i + 1])
            i += 2
            continue
        else:
            current.append(ch)
        i += 1
    if current:
        words.append("".join(current))
    return words


def command_segments(command: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"\s*(?:&&|\|\||;|\n)\s*", command)
        if part.strip()
    ]


def first_binary(words: list[str]) -> str:
    skip_prefixes = {"sudo", "command", "env", "nice", "nohup", "time"}
    i = 0
    while i < len(words) and words[i] in skip_prefixes:
        i += 1
        if i and words[i - 1] == "env":
            while i < len(words) and "=" in words[i]:
                i += 1
    if i >= len(words):
        return ""
    return words[i].rsplit("/", 1)[-1]


def host_from_target(target: str) -> str:
    value = target.strip()
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")].lower()
    if value.startswith("rsync://"):
        value = value[len("rsync://") :]
    if "://" in value:
        value = value.split("://", 1)[1]
    if "@" in value:
        value = value.split("@", 1)[1]
    if ":" in value and not re.match(r"^\[[0-9a-fA-F:]+\]$", f"[{value}]"):
        # host:path or host:port — path usually has /, port is digits
        host, rest = value.split(":", 1)
        if rest.isdigit() or rest.startswith("/") or rest == "" or "/" in rest:
            value = host
    return value.lower().rstrip("/")


def is_live_host(target: str, live_hosts: set[str]) -> bool:
    if not live_hosts or not target:
        return False
    host = host_from_target(target)
    if host in live_hosts:
        return True
    return any(host == item or host.endswith("." + item) for item in live_hosts)


def parse_ssh_style(words: list[str]) -> tuple[str, str, str]:
    """Return (binary, destination, remote_command_or_path)."""
    if not words:
        return "", "", ""
    binary = first_binary(words)
    takes = SSH_OPTION_TAKES_VALUE if binary == "ssh" else SCP_OPTION_TAKES_VALUE
    i = 0
    while i < len(words) and first_binary(words[i:]) != binary:
        i += 1
    i += 1
    dests: list[str] = []
    remote_parts: list[str] = []
    while i < len(words):
        token = words[i]
        if token == "--":
            remote_parts.extend(words[i + 1 :])
            break
        if token.startswith("-") and token != "-":
            flags = token[1:]
            if binary == "ssh" and len(token) > 2 and flags[0] not in takes:
                i += 1
                continue
            opt = flags[-1] if binary == "ssh" else flags
            if opt in takes or (binary == "ssh" and flags[0] in takes and len(flags) == 1):
                i += 2
                continue
            i += 1
            continue
        dests.append(token)
        i += 1
        if binary == "ssh":
            remote_parts.extend(words[i:])
            break
    dest = dests[0] if dests else ""
    extra = " ".join(remote_parts if binary == "ssh" else dests[1:])
    if binary in {"scp", "rsync", "sftp", "sshfs"}:
        extra = " ".join(dests)
    return binary, dest, extra


def remote_access_findings(command: str, live_hosts: set[str]) -> list[str]:
    findings: list[str] = []
    for segment in command_segments(command):
        words = split_shell_words(segment)
        binary = first_binary(words)
        if binary not in REMOTE_ACCESS_CMDS:
            continue
        _bin, dest, extra = parse_ssh_style(words)
        live = is_live_host(dest, live_hosts) or any(
            is_live_host(word, live_hosts) for word in words
        )
        label = "live TeamCity host" if live else "remote host"

        host = host_from_target(dest) or dest or "(unknown)"

        if binary == "ssh":
            remote = extra.strip()
            # Always ask. Any ssh is a watcher trigger — including uptime on an
            # unknown box. Live/destructive are extra findings, not a filter.
            findings.append(f"SSH to {label} {host}")
            if not remote:
                findings.append(
                    f"interactive SSH to {label} {host} "
                    "(full shell; cannot see later commands)"
                )
            elif DESTRUCTIVE_REMOTE.search(remote) or TEAMCITY_DATA_PATH.search(remote):
                findings.append(
                    f"destructive SSH on {label} {host}: {remote[:160]}"
                )
            continue

        if binary == "rsync":
            remote_like = any(
                ":" in word and not word.startswith("-") and not re.match(r"^[A-Za-z]:\\", word)
                for word in words
            )
            uses_ssh = bool(re.search(r"(?i)(-e|--rsh)\s*.*ssh|\bssh\b", segment))
            if not remote_like and not uses_ssh:
                continue

        # scp / rsync / sftp / sshfs — always ask; extra when writing live/TeamCity data.
        writing_remote = False
        remote_shown = ""
        remote_targets = [
            word
            for word in words
            if ":" in word and not word.startswith("-") and not re.match(r"^[A-Za-z]:\\", word)
        ]
        saw_local = False
        for word in words:
            if word.startswith("-") or word == binary or word.rsplit("/", 1)[-1] == binary:
                continue
            if ":" in word and not re.match(r"^[A-Za-z]:\\", word):
                host_part, _, path_part = word.partition(":")
                target_live = is_live_host(host_part, live_hosts)
                if saw_local or target_live or TEAMCITY_DATA_PATH.search(path_part or word):
                    writing_remote = True
                    remote_shown = word
                if target_live and binary in {"sftp", "sshfs"}:
                    ro = bool(re.search(r"(?i)(^|\s)-o\s*ro\b|[-,]ro\b", segment))
                    if not ro:
                        writing_remote = True
                        remote_shown = word
            else:
                saw_local = True
        shown = remote_shown or host or "(path in command)"
        findings.append(f"{binary} toward {label} {shown}")
        if writing_remote:
            findings.append(f"{binary} write toward {label} {shown}")
        elif live and binary in {"sftp", "sshfs"} and not re.search(
            r"(?i)(^|\s)-o\s*ro\b", segment
        ):
            findings.append(f"{binary} session on {label} {shown}")
    return findings


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def hook_event_name(event: dict[str, Any]) -> str:
    return str(event.get("hook_event_name") or event.get("hookEventName") or "").lower()


def is_cursor_payload(event: dict[str, Any]) -> bool:
    """Cursor events carry cursor_version, MCP server fields, or Cursor-only event names."""
    if "--runtime" in sys.argv:
        idx = sys.argv.index("--runtime")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].lower() == "cursor":
            return True
    if event.get("cursor_version"):
        return True
    if event.get("workspace_roots") is not None:
        return True
    if event.get("mcp_server_name") or event.get("mcp_server_url"):
        return True
    name = hook_event_name(event)
    return name in {
        "beforeshellexecution",
        "beforemcpexecution",
        "aftershellexecution",
        "aftermcpexecution",
    }


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value
    return value


def looks_like_teamcity(server: str, url: str, name: str) -> bool:
    blob = f"{server} {url} {name}".lower()
    return "teamcity" in blob


def looks_like_gitlab(server: str, url: str, name: str) -> bool:
    blob = f"{server} {url} {name}".lower()
    return (
        "gitlab" in blob
        or "nova.teachx.ai" in blob
        or name.lower().startswith("gitlab")
    )


def canonical_tool_name(name: str, server: str = "", url: str = "") -> str:
    """Map Cursor MCP names onto Grok-style prefixes used by classify()."""
    raw = (name or "").strip()
    lower = raw.lower()
    if not lower:
        return raw
    if lower in TEAMCITY_WRITE_BARE:
        return TEAMCITY_WRITE_BARE[lower]
    if lower.startswith("teamcity__") or lower.startswith("gitlab__"):
        return lower
    if lower.startswith("gitlab_"):
        return "gitlab__" + lower[len("gitlab_") :]
    if looks_like_teamcity(server, url, lower) and lower.startswith("teamcity_rest_"):
        mapped = TEAMCITY_WRITE_BARE.get(lower)
        return mapped or f"teamcity__{lower}"
    if looks_like_gitlab(server, url, lower) and not lower.startswith("gitlab"):
        return f"gitlab__{lower}"
    return lower


def unwrap_call_dynamic(name: str, tool_input: Any) -> tuple[str, Any, str]:
    """Cursor CallDynamicTool → (inner tool, args, namespace)."""
    compact = name.lower().replace("-", "").replace("_", "")
    if compact != "calldynamictool":
        return name, tool_input, ""
    if not isinstance(tool_input, dict):
        return name, tool_input, ""
    inner = str(tool_input.get("toolName") or tool_input.get("tool_name") or "")
    namespace = str(tool_input.get("namespace") or "")
    args = tool_input.get("arguments")
    if not inner:
        return name, tool_input, namespace
    if isinstance(args, dict):
        return inner, args, namespace
    parsed = parse_jsonish(args)
    if isinstance(parsed, dict):
        return inner, parsed, namespace
    return inner, tool_input, namespace


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Fold Cursor and Grok payloads into toolName + toolInput classify() expects."""
    name = str(event.get("toolName") or event.get("tool_name") or "")
    tool_input = parse_jsonish(event.get("toolInput") or event.get("tool_input") or {})
    server = str(event.get("mcp_server_name") or event.get("mcpServerName") or "")
    event_name = hook_event_name(event)
    if event_name in {"beforemcpexecution", "aftermcpexecution"}:
        url = str(
            event.get("mcp_server_url")
            or event.get("mcpServerUrl")
            or event.get("url")
            or ""
        )
    else:
        url = str(event.get("mcp_server_url") or event.get("mcpServerUrl") or "")

    if isinstance(tool_input, dict):
        name, tool_input, namespace = unwrap_call_dynamic(name, tool_input)
        if namespace and not server:
            server = namespace

    # beforeShellExecution: command is the user shell. beforeMCPExecution: command is
    # the MCP server launch string — never treat that as a user shell command.
    if event_name in {"beforeshellexecution", "aftershellexecution"}:
        command = str(event.get("command") or "")
        if command:
            if not isinstance(tool_input, dict):
                tool_input = {"command": command}
            elif not str(tool_input.get("command") or "").strip():
                tool_input = {**tool_input, "command": command}
        if not name:
            name = "Shell"

    name = canonical_tool_name(name, server, url)
    out = dict(event)
    out["toolName"] = name
    out["tool_name"] = name
    out["toolInput"] = tool_input if tool_input is not None else {}
    out["mcp_server_name"] = server
    return out


def findings_reason(findings: list[str]) -> str:
    return (
        "live-ops-guard needs your OK before this call.\n"
        + "\n".join(f"- {item}" for item in findings)
        + "\nApprove only if you intended this on the live server / GitLab."
    )


def ignore_span(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 24) : min(len(text), end + 24)]
    return bool(PLACEHOLDER_RE.search(window))


def find_secrets(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for kind, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if ignore_span(text, match.start(), match.end()):
                continue
            if kind not in seen:
                seen.add(kind)
                found.append(kind)
    return found


def redact_text(text: str) -> str:
    redacted = text
    for kind, pattern in SECRET_PATTERNS:
        def repl(match: re.Match[str], kind: str = kind) -> str:
            if ignore_span(match.string, match.start(), match.end()):
                return match.group(0)
            return f"***REDACTED:{kind}***"

        redacted = pattern.sub(repl, redacted)
    return redacted


def tool_name_of(event: dict[str, Any]) -> str:
    name = str(event.get("toolName") or event.get("tool_name") or "")
    tool_input = event.get("toolInput") or event.get("tool_input") or {}
    if isinstance(tool_input, dict):
        inner = tool_input.get("tool_name") or tool_input.get("toolName")
        if inner:
            name = str(inner)
    return name


def teamcity_path_and_body(tool_input: Any) -> tuple[str, str]:
    if not isinstance(tool_input, dict):
        return "", flatten_text(tool_input)
    # use_tool wraps MCP args
    args = tool_input.get("tool_input") if "tool_input" in tool_input else tool_input
    if not isinstance(args, dict):
        return "", flatten_text(tool_input)
    path = str(args.get("path") or "")
    body = flatten_text(args.get("body") or "")
    return path, body



def normalize_mcp_tool_name(name: str) -> str:
    """Strip server prefix variants: gitlab__foo, gitlab_foo, foo."""
    raw = (name or "").strip()
    lower = raw.lower()
    for prefix in ("gitlab__", "gitlab_"):
        if lower.startswith(prefix):
            return lower
    return lower


def is_gitlab_tool(name: str) -> bool:
    lower = normalize_mcp_tool_name(name)
    return lower.startswith("gitlab__") or lower.startswith("gitlab_")


def gitlab_tool_action(name: str) -> str:
    """Return short action id after gitlab__ prefix."""
    lower = normalize_mcp_tool_name(name)
    if lower.startswith("gitlab__"):
        return lower[len("gitlab__") :]
    if lower.startswith("gitlab_"):
        return lower[len("gitlab_") :]
    return lower


def classify_gitlab_tool(name: str, tool_input: Any) -> list[str]:
    """Flag GitLab MCP mutations. Reads (get_/list_/search_/whoami/...) stay quiet."""
    if not is_gitlab_tool(name):
        return []
    action = gitlab_tool_action(name)
    findings: list[str] = []

    # dry_run on patch tools is read-only preview
    args = tool_input
    if isinstance(tool_input, dict) and "tool_input" in tool_input:
        inner = tool_input.get("tool_input")
        if isinstance(inner, dict):
            args = inner
    if isinstance(args, dict) and args.get("dry_run") is True:
        return []

    # Read-only tools: first path segment is a reader verb.
    # Important: do NOT substring-match "merge" — list_merge_requests is a read.
    parts = [p for p in action.replace("-", "_").split("_") if p]
    head = parts[0] if parts else ""
    read_heads = {
        "get",
        "list",
        "search",
        "my",
        "whoami",
        "download",
        "compare",
        "validate",
        "view",
        "show",
        "fetch",
        "read",
        "mr",  # mr_discussions etc. are reads unless a later write verb leads
        "discussions",
    }
    # mr_discussions / discussions: read. Leading write verb always wins.
    write_heads = {
        "create",
        "update",
        "delete",
        "merge",
        "approve",
        "unapprove",
        "publish",
        "upload",
        "award",
        "invite",
        "revoke",
        "cancel",
        "retry",
        "play",
        "promote",
        "protect",
        "unprotect",
        "transfer",
        "move",
        "fork",
        "rebase",
        "revert",
        "subscribe",
        "unsubscribe",
        "set",
        "add",
        "remove",
        "edit",
        "patch",
        "bulk",
        "accept",
        "reject",
        "ban",
        "block",
        "unblock",
        "share",
        "unshare",
        "start",
        "stop",
        "trigger",
        "export",
        "import",
        "post",
        "put",
        "put",
    }

    if head in read_heads and head not in write_heads:
        return []

    irreversible = False
    for tok in GITLAB_IRREVERSIBLE_TOKENS:
        # token match on full action or as underscore-bounded segment sequence
        if action == tok or action.startswith(tok + "_") or action.endswith("_" + tok) or f"_{tok}_" in f"_{action}_":
            irreversible = True
            break
    # Dedicated merge tool (merge / merge_merge_request / *_merge_request when head is merge)
    if head == "merge" or action in {"merge", "merge_merge_request"} or action.startswith("merge_"):
        irreversible = True
    if head == "delete" or action.startswith("delete_"):
        irreversible = True

    write = irreversible or head in write_heads
    if not write:
        # e.g. bulk_publish_draft_notes → head bulk
        write = any(
            action.startswith(tok) or f"_{tok}" in f"_{action}"
            for tok in (
                "create_",
                "update_",
                "delete_",
                "merge_",
                "approve_",
                "unapprove_",
                "publish_",
                "upload_",
                "bulk_",
            )
        )

    if not write:
        return []

    label = f"GitLab MCP {action or name}"
    if irreversible:
        findings.append(f"irreversible {label}")
    findings.append(f"live GitLab write {label}")

    # Surface target MR/issue when present (no secrets).
    if isinstance(args, dict):
        bits: list[str] = []
        for key in (
            "project_id",
            "merge_request_iid",
            "issue_iid",
            "noteable_iid",
            "pipeline_id",
            "branch",
            "source_branch",
            "target_branch",
        ):
            val = args.get(key)
            if val is not None and str(val).strip():
                bits.append(f"{key}={val}")
        if bits:
            findings.append("GitLab target " + ", ".join(bits[:6]))
        # state_event close/reopen/merge-ish
        state_event = str(args.get("state_event") or "").lower()
        if state_event in {"close", "reopen"}:
            findings.append(f"GitLab state_event={state_event}")
        if args.get("should_remove_source_branch") is True:
            findings.append("GitLab will remove source branch")
        if args.get("squash") is True:
            findings.append("GitLab squash on merge")
    return findings


def classify_gitlab_shell(command: str) -> list[str]:
    """Flag glab mutations and curl/http writes toward GitLab hosts."""
    if not command.strip():
        return []
    findings: list[str] = []
    if GITLAB_GLAB_MUTATION_RE.search(command):
        findings.append("live GitLab write via glab CLI")
    # curl -X POST ... nova.teachx.ai
    if GITLAB_HOST_RE.search(command) and (
        GITLAB_HTTP_MUTATION_RE.search(command)
        or re.search(r"(?i)\bcurl\b[^\n]*\b-d\b", command)
        or re.search(r"(?i)\bcurl\b[^\n]*\b--data\b", command)
        or re.search(r"(?i)\bcurl\b[^\n]*\b-F\b", command)
        or re.search(r"(?i)\b(POST|PUT|PATCH|DELETE)\b", command)
    ):
        # Avoid flagging pure GET curl to gitlab
        if re.search(r"(?i)(-X|--request)\s*GET\b", command):
            return findings
        if re.search(r"(?i)\bmethod\s*[:=]\s*['\"]?GET\b", command):
            return findings
        # python urllib/requests POST to gitlab
        findings.append("live GitLab HTTP mutation toward GitLab host")
    # python scripts that hit api/v4 with write methods
    if re.search(r"(?i)(api/v4|nova\.teachx\.ai)", command) and re.search(
        r"(?i)(method\s*=\s*['\"]?(PUT|POST|PATCH|DELETE)|Request\([^\n]*(PUT|POST|PATCH|DELETE))",
        command,
    ):
        findings.append("live GitLab HTTP mutation (scripted API write)")
    return findings


def classify(event: dict[str, Any]) -> list[str]:
    event = normalize_event(event)
    findings: list[str] = []
    name = tool_name_of(event)
    tool_input = event.get("toolInput") or event.get("tool_input") or {}
    blob = flatten_text({"tool": name, "input": tool_input})

    secrets = find_secrets(blob)
    if secrets:
        findings.append("secret(" + ", ".join(secrets) + ")")

    if name in TEAMCITY_WRITE_TOOLS:
        path, body = teamcity_path_and_body(tool_input)
        method = name.rsplit("_", 1)[-1].upper()
        if method == "DELETE" or IRREVERSIBLE_PATH.search(path):
            findings.append(f"irreversible TeamCity {method} {path or '(no path)'}")
        elif method == "POST" and "/buildQueue" in path and '"personal":true' not in body.replace(
            " ", ""
        ).replace("'", '"').lower().replace("true", "true"):
            compact = re.sub(r"\s+", "", body).lower()
            if "personal" not in compact or "personal:true" not in compact.replace('"', ""):
                findings.append("team-visible TeamCity build (not personal)")
        findings.append(f"live TeamCity write {method} {path or '(no path)'}")

    # GitLab MCP (direct tool or use_tool wrapper — name already unwrapped).
    findings.extend(classify_gitlab_tool(name, tool_input))

    command = ""
    event_name = hook_event_name(event)
    if event_name not in {"beforemcpexecution", "aftermcpexecution"}:
        if isinstance(tool_input, dict):
            command = str(tool_input.get("command") or "")
    if isinstance(tool_input, dict) and not is_gitlab_tool(name):
        nested = str(tool_input.get("tool_name") or tool_input.get("toolName") or "")
        if is_gitlab_tool(nested):
            findings.extend(classify_gitlab_tool(nested, tool_input))
    if command:
        if SUSPICIOUS_SHELL.search(command):
            findings.append("suspicious shell command")
        findings.extend(remote_access_findings(command, load_live_hosts()))
        findings.extend(classify_gitlab_shell(command))

    return findings


def pre_decision(event: dict[str, Any]) -> dict[str, Any]:
    findings = classify(event)
    if is_cursor_payload(event):
        if not findings:
            return {"permission": "allow"}
        reason = findings_reason(findings)
        return {
            "permission": "ask",
            "user_message": reason,
            "agent_message": (
                "live-ops-guard needs the operator's OK. Do not retry this call. "
                "Treat a reject as final.\n" + reason
            ),
        }
    if not findings:
        return {"decision": "allow"}
    return {"decision": "ask", "reason": findings_reason(findings)}


def _result_blob(event: dict[str, Any]) -> Any:
    for key in (
        "toolResult",
        "tool_result",
        "tool_output",
        "result_json",
        "output",
    ):
        if event.get(key) is not None:
            return event.get(key)
    return None


def post_decision(event: dict[str, Any]) -> dict[str, Any]:
    result = _result_blob(event)
    text = flatten_text(result)
    secrets = find_secrets(text)
    if not secrets:
        return {}
    redacted = redact_text(text)
    name = tool_name_of(normalize_event(event))
    note = (
        "live-ops-guard redacted secret-like values in the tool result "
        f"({', '.join(secrets)}). Do not echo or reuse the original values."
    )
    if is_cursor_payload(event):
        out: dict[str, Any] = {"additional_context": note}
        if event.get("mcp_server_name") or "gitlab__" in name or "teamcity__" in name:
            try:
                out["updated_mcp_tool_output"] = json.loads(redacted)
            except json.JSONDecodeError:
                out["updated_mcp_tool_output"] = {"redacted": redacted}
        return out
    hook_out: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": note,
        }
    }
    if "__" in name:
        hook_out["hookSpecificOutput"]["updatedToolOutput"] = redacted
    elif isinstance(result, dict):
        rewritten = json.loads(redact_text(json.dumps(result)))
        hook_out["hookSpecificOutput"]["updatedToolOutput"] = rewritten
    return hook_out


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Hybrid: Grok reads decision, Cursor reads permission.
        print(json.dumps({"decision": "defer", "permission": "allow"}))
        return 0

    event_name = hook_event_name(event)
    argv_event = ""
    if "--event" in sys.argv:
        idx = sys.argv.index("--event")
        if idx + 1 < len(sys.argv):
            argv_event = sys.argv[idx + 1].lower()

    is_post = (
        argv_event in {"post", "cursor-post"}
        or "post_tool_use" in event_name
        or event_name in CURSOR_POST_EVENTS
    )

    try:
        if is_post:
            print(json.dumps(post_decision(event)))
        else:
            print(json.dumps(pre_decision(event)))
    except Exception as exc:  # noqa: BLE001 — fail open
        print(json.dumps(_fail_open(event)))
        print(f"live-ops-guard error: {type(exc).__name__}", file=sys.stderr)
    return 0


def _fail_open(event: dict[str, Any] | None) -> dict[str, Any]:
    if event and is_cursor_payload(event):
        return {"permission": "allow"}
    return {"decision": "defer", "permission": "allow"}


if __name__ == "__main__":
    raise SystemExit(main())
