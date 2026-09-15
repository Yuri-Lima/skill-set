#!/usr/bin/env python3
"""Live-ops guard: ask before TeamCity writes, leaked secrets, or irreversible calls.

Reads one hook event JSON from stdin. Prints a decision JSON to stdout.
Never logs raw payloads. Fail-open (defer) on parse/runtime errors.
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
}

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

        if binary == "ssh":
            remote = extra.strip()
            if not remote:
                if live:
                    findings.append(
                        f"interactive SSH to {label} {host_from_target(dest) or dest or '(unknown)'} "
                        "(full shell; cannot see later commands)"
                    )
                continue
            if DESTRUCTIVE_REMOTE.search(remote) or TEAMCITY_DATA_PATH.search(remote):
                findings.append(
                    f"destructive SSH on {label} {host_from_target(dest) or dest}: {remote[:160]}"
                )
            continue

        # scp / rsync / sftp / sshfs — ask when writing to a listed live host,
        # or when the destination path is TeamCity data (even before hosts are listed).
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
        shown = remote_shown or host_from_target(dest) or dest or "(path in command)"
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


def classify(event: dict[str, Any]) -> list[str]:
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

    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or "")
    if command:
        if SUSPICIOUS_SHELL.search(command):
            findings.append("suspicious shell command")
        findings.extend(remote_access_findings(command, load_live_hosts()))

    return findings


def pre_decision(event: dict[str, Any]) -> dict[str, Any]:
    findings = classify(event)
    if not findings:
        return {"decision": "allow"}
    reason = (
        "live-ops-guard needs your OK before this call.\n"
        + "\n".join(f"- {item}" for item in findings)
        + "\nApprove only if you intended this on the live server."
    )
    return {"decision": "ask", "reason": reason}


def post_decision(event: dict[str, Any]) -> dict[str, Any]:
    result = event.get("toolResult")
    if result is None:
        result = event.get("tool_result")
    text = flatten_text(result)
    secrets = find_secrets(text)
    if not secrets:
        return {}
    redacted = redact_text(text)
    name = tool_name_of(event)
    out: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "live-ops-guard redacted secret-like values in the tool result "
                f"({', '.join(secrets)}). Do not echo or reuse the original values."
            ),
        }
    }
    if "__" in name:
        out["hookSpecificOutput"]["updatedToolOutput"] = redacted
    elif isinstance(result, dict):
        rewritten = json.loads(redact_text(json.dumps(result)))
        out["hookSpecificOutput"]["updatedToolOutput"] = rewritten
    return out


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"decision": "defer"}))
        return 0

    event_name = str(
        event.get("hook_event_name") or event.get("hookEventName") or ""
    ).lower()
    argv_event = ""
    if "--event" in sys.argv:
        idx = sys.argv.index("--event")
        if idx + 1 < len(sys.argv):
            argv_event = sys.argv[idx + 1].lower()

    try:
        if argv_event == "post" or "post_tool_use" in event_name or event_name == "posttooluse":
            print(json.dumps(post_decision(event)))
        else:
            print(json.dumps(pre_decision(event)))
    except Exception as exc:  # noqa: BLE001 — fail open
        print(json.dumps({"decision": "defer"}))
        print(f"live-ops-guard error: {type(exc).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
