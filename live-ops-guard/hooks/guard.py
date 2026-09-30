#!/usr/bin/env python3
"""Live-ops guard: ask before live writes, leaked secrets, or irreversible calls.

Covers TeamCity REST writes, GitLab MCP / API mutations, leaked secrets,
reads of secret stores, destructive SSH, and suspicious shell.

Speaks Grok PreToolUse/PostToolUse, Claude Code PreToolUse/PostToolUse/
SessionStart/Stop, and Cursor beforeMCPExecution / beforeShellExecution /
postToolUse / sessionStart / stop.

Reads one hook event JSON from stdin. Prints a decision JSON to stdout.
Never logs raw payloads. Fail-open (allow) on parse/runtime errors, but
LOUD: the operator is told, and the ledger + NEEDS_TRACE_REVIEW marker
record that the guard did not evaluate the call.

Awareness files (all next to this script, or under $LIVE_OPS_GUARD_HOME):

  ledger.jsonl        one line per guarded / redacted / fail-open event
                      (timestamp, session, runtime, tool, finding kinds,
                      decision — never the payload)
  NEEDS_TRACE_REVIEW  sessions whose trace must be reviewed by a person
                      (a secret-like value was exposed, a secret store was
                      read, or the guard failed open). Not cleared by the
                      guard itself: `guard.py review <session> --ack`.

Modes (--mode, or $LIVE_OPS_GUARD_MODE; default "notify"):

  notify  Commands run. The guard records every finding in the ledger and,
          when a REAL exposure happens (secret-like value in a tool result,
          secret store read, secret literal in a tool input, fail-open), it
          interrupts with an exposure notice and options — proceed / stop /
          recommended — instead of a yes/no question.
  gate    The original behaviour: every live write, ssh and secret read is
          held with a permission "ask" before it runs. Exposure notices are
          the same as in notify mode.

CLI:
  guard.py --event pre|post|start|stop [--runtime grok|cursor|claude] [--mode notify|gate]
  guard.py review [SESSION|--last] [--ack]
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Home, files, operator
# ---------------------------------------------------------------------------

GUARD_HOME = os.environ.get("LIVE_OPS_GUARD_HOME") or os.path.dirname(os.path.abspath(__file__))
HOSTS_FILE = os.path.join(GUARD_HOME, "live-hosts.txt")
GITLAB_HOSTS_FILE = os.path.join(GUARD_HOME, "gitlab-hosts.txt")
LEDGER_FILE = os.path.join(GUARD_HOME, "ledger.jsonl")
MARKER_FILE = os.path.join(GUARD_HOME, "NEEDS_TRACE_REVIEW")

# How the guard addresses the person at the keyboard. Generic on purpose:
# no real name or host belongs in this public file.
OPERATOR = os.environ.get("LIVE_OPS_GUARD_OPERATOR") or "Dear Lazy User"

MODES = ("notify", "gate")


def mode_of() -> str:
    """notify (default) or gate. --mode wins over $LIVE_OPS_GUARD_MODE."""
    forced = argv_value("--mode")
    if forced in MODES:
        return forced
    env = (os.environ.get("LIVE_OPS_GUARD_MODE") or "").lower()
    return env if env in MODES else "notify"

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Secret-store reads (pre-time). Reading a secret is exposure even when the
# post hook cannot redact the result.
# ---------------------------------------------------------------------------

# A read verb must lead the segment for FILE patterns to count.
SECRET_READ_VERB_RE = re.compile(
    r"(?i)^(?:sudo\s+)?(?:cat|less|more|head|tail|bat|grep|rg|ag|source|\.|base64|xxd|od|"
    r"strings|awk|sed|nl|tac|paste|cut|tr|cp|scp|rsync|open|code|vim|vi|nano|emacs)\s"
)

SECRET_READ_FILE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("env-file", re.compile(r"(?<![\w/.-])\.env(?:\.(?!example|sample|template|dist)[\w-]+)?(?![\w.-])")),
    ("ssh-private-key", re.compile(r"\.ssh/(?:id_[A-Za-z0-9_]+|[^\s/]*_key|[^\s/]*\.pem)(?!\.pub)(?![\w.-])")),
    ("aws-credentials", re.compile(r"\.aws/credentials\b")),
    ("netrc", re.compile(r"(?<![\w-])_?\.netrc\b")),
    ("docker-config", re.compile(r"\.docker/config\.json\b")),
    ("kube-config", re.compile(r"\.kube/config\b")),
    ("npmrc", re.compile(r"(?<![\w-])\.npmrc\b")),
    ("pypirc", re.compile(r"(?<![\w-])\.pypirc\b")),
    ("git-credentials", re.compile(r"\.git-credentials\b")),
    ("etc-shadow", re.compile(r"/etc/shadow\b")),
    ("pem-file", re.compile(r"(?<![\w-])[\w./-]+\.(?:pem|p12|pfx|key)(?![\w.-])")),
]

SECRET_READ_COMMAND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gh-auth-token", re.compile(r"(?i)\bgh\s+auth\s+token\b")),
    ("glab-show-token", re.compile(r"(?i)\bglab\s+auth\s+status\b[^\n]*--show-token")),
    ("1password-read", re.compile(r"(?i)\bop\s+(?:read|item\s+get)\b")),
    ("keychain-read", re.compile(r"(?i)\bsecurity\s+find-(?:generic|internet)-password\b")),
    ("vault-read", re.compile(r"(?i)\bvault\s+(?:kv\s+get|read)\b")),
    ("k8s-secret", re.compile(r"(?i)\bkubectl\s+[^\n]*\bget\s+secrets?\b")),
    (
        "aws-secret-read",
        re.compile(
            r"(?i)\baws\s+(?:configure\s+get\s+aws_secret_access_key|secretsmanager\s+get-secret-value"
            r"|ssm\s+get-parameters?\b[^\n]*--with-decryption)"
        ),
    ),
    (
        "echo-secret-var",
        re.compile(
            r"(?i)\becho\s+[^\n]*\$\{?[A-Za-z_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_KEY|_PAT|_KEY)\b"
        ),
    ),
    ("env-dump", re.compile(r"(?:^|[\s;|&(])(?:printenv|env|set|export\s+-p)\s*(?:$|[|;&>)])")),
    ("history-dump", re.compile(r"(?i)\bhistory\s*(?:$|\|)")),
]

# ---------------------------------------------------------------------------
# TeamCity / GitLab / shell classification tables
# ---------------------------------------------------------------------------

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

CURSOR_PRE_EVENTS = {"pretooluse", "beforeshellexecution", "beforemcpexecution"}
CURSOR_POST_EVENTS = {"posttooluse", "aftershellexecution", "aftermcpexecution", "posttoolusefailure"}
START_EVENTS = {"sessionstart"}
STOP_EVENTS = {"stop", "sessionend"}

# GitLab MCP (gitlab.com, any gitlab__* server, and the hosts the operator
# lists in gitlab-hosts.txt). Reads stay allow; mutations ask the operator —
# same policy as TeamCity live writes.
GITLAB_TOOL_PREFIXES = ("gitlab__",)

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

GITLAB_HOST_GENERIC_RE = re.compile(r"(?i)\bgitlab\.")
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

REMOTE_ACCESS_CMDS = ("ssh", "scp", "rsync", "sftp", "sshfs")

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

SSH_OPTION_TAKES_VALUE = {
    "b", "c", "D", "E", "e", "F", "I", "i", "J", "L", "l", "m", "O", "o",
    "p", "Q", "R", "S", "W", "w",
}

SCP_OPTION_TAKES_VALUE = {"c", "F", "i", "J", "l", "o", "P", "S"}


# ---------------------------------------------------------------------------
# Host lists
# ---------------------------------------------------------------------------

def _read_host_file(path: str) -> set[str]:
    hosts: set[str] = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                hosts.add(line.lower())
                if "@" in line:
                    hosts.add(line.split("@", 1)[1].lower())
                if ":" in line and not line.count(":") > 1:
                    hosts.add(line.rsplit(":", 1)[0].lower())
    except OSError:
        pass
    return hosts


def load_live_hosts() -> set[str]:
    return _read_host_file(HOSTS_FILE)


def load_gitlab_hosts() -> set[str]:
    hosts = _read_host_file(GITLAB_HOSTS_FILE)
    hosts.add("gitlab.com")
    return hosts


def mentions_gitlab_host(text: str) -> bool:
    if GITLAB_HOST_GENERIC_RE.search(text):
        return True
    lower = text.lower()
    return any(host in lower for host in load_gitlab_hosts())


# ---------------------------------------------------------------------------
# Shell parsing
# ---------------------------------------------------------------------------

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


HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n.*?\n\s*\2[ \t]*(?=\n|$)", re.DOTALL)


def strip_heredocs(command: str) -> str:
    """A heredoc body is data being written, not a command being run.

    `cat > test.py <<'PY' ... gh auth token ... PY` must not read as a secret read."""
    return HEREDOC_RE.sub("<<HEREDOC_BODY_STRIPPED", command)


def command_segments(command: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"\s*(?:&&|\|\||;|\n)\s*", strip_heredocs(command))
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
            findings.append(f"SSH to {label} {host}")
            if not remote:
                findings.append(
                    f"interactive SSH to {label} {host} "
                    "(full shell; cannot see later commands)"
                )
            elif DESTRUCTIVE_REMOTE.search(remote) or TEAMCITY_DATA_PATH.search(remote):
                # redact_text: the remote command may carry a secret and this
                # string ends up in the operator prompt and the agent context.
                findings.append(
                    f"destructive SSH on {label} {host}: {redact_text(remote[:160])}"
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

        writing_remote = False
        remote_shown = ""
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
        shown = redact_text(remote_shown or host or "(path in command)")
        findings.append(f"{binary} toward {label} {shown}")
        if writing_remote:
            findings.append(f"{binary} write toward {label} {shown}")
        elif live and binary in {"sftp", "sshfs"} and not re.search(
            r"(?i)(^|\s)-o\s*ro\b", segment
        ):
            findings.append(f"{binary} session on {label} {shown}")
    return findings


def secret_read_findings(command: str) -> list[str]:
    """Reads of secret stores. The result of these is exposure by definition."""
    findings: list[str] = []
    seen: set[str] = set()
    for segment in command_segments(command):
        body = segment
        # strip sudo/env prefixes so the verb check sees the real command
        words = split_shell_words(segment)
        binary = first_binary(words)
        if binary and binary in segment:
            body = segment[segment.index(binary) :]
        has_read_verb = bool(SECRET_READ_VERB_RE.match(body))
        if has_read_verb:
            for kind, pattern in SECRET_READ_FILE_PATTERNS:
                if kind not in seen and pattern.search(body):
                    seen.add(kind)
                    findings.append(f"secret-read({kind})")
        for kind, pattern in SECRET_READ_COMMAND_PATTERNS:
            if kind not in seen and pattern.search(body):
                seen.add(kind)
                findings.append(f"secret-read({kind})")
    return findings


# ---------------------------------------------------------------------------
# Event normalisation
# ---------------------------------------------------------------------------

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


def argv_value(flag: str) -> str:
    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1].lower()
    return ""


def is_cursor_payload(event: dict[str, Any]) -> bool:
    """Cursor events carry cursor_version, MCP server fields, or Cursor-only event names."""
    if argv_value("--runtime") == "cursor":
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


def runtime_of(event: dict[str, Any] | None) -> str:
    """grok | cursor | claude. Grok is the default (its payloads are camelCase)."""
    forced = argv_value("--runtime")
    if forced in {"grok", "cursor", "claude"}:
        return forced
    if not event:
        return "grok"
    if is_cursor_payload(event):
        return "cursor"
    if event.get("transcript_path") is not None:
        return "claude"
    return "grok"


def session_id_of(event: dict[str, Any] | None) -> str:
    event = event or {}
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        value = event.get(key)
        if value:
            return str(value)
    env = os.environ.get("LIVE_OPS_GUARD_SESSION")
    if env:
        return env
    # The hook is spawned by the runtime process; its pid is stable for the session.
    return f"ppid-{os.getppid()}"


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
    return "gitlab" in blob or name.lower().startswith("gitlab") or mentions_gitlab_host(blob)


def canonical_tool_name(name: str, server: str = "", url: str = "") -> str:
    """Map Cursor / Claude Code MCP names onto Grok-style prefixes used by classify()."""
    raw = (name or "").strip()
    lower = raw.lower()
    if not lower:
        return raw
    if lower.startswith("mcp__"):
        # Claude Code: mcp__<server>__<tool>
        lower = lower[len("mcp__") :]
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


def coerce_tool_input(tool_input: Any) -> tuple[Any, bool]:
    """Non-dict inputs are flattened into {"command": ...} so they are still scanned.

    Returns (input, coerced). A coerced shape is recorded in the ledger."""
    if tool_input is None:
        return {}, False
    if isinstance(tool_input, dict):
        return tool_input, False
    if isinstance(tool_input, list) and all(isinstance(item, str) for item in tool_input):
        return {"command": " ".join(tool_input)}, True
    if isinstance(tool_input, str):
        return {"command": tool_input}, True
    return {"command": flatten_text(tool_input)}, True


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Fold Cursor, Claude Code and Grok payloads into toolName + toolInput classify() expects."""
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

    tool_input, coerced = coerce_tool_input(tool_input)

    # beforeShellExecution: command is the user shell. beforeMCPExecution: command is
    # the MCP server launch string — never treat that as a user shell command.
    if event_name in {"beforeshellexecution", "aftershellexecution"}:
        command = str(event.get("command") or "")
        if command and not str(tool_input.get("command") or "").strip():
            tool_input = {**tool_input, "command": command}
        if not name:
            name = "Shell"

    name = canonical_tool_name(name, server, url)
    out = dict(event)
    out["toolName"] = name
    out["tool_name"] = name
    out["toolInput"] = tool_input
    out["mcp_server_name"] = server
    out["_coerced_shape"] = coerced
    return out


# ---------------------------------------------------------------------------
# Secrets: find / redact
# ---------------------------------------------------------------------------

def ignore_span(text: str, start: int, end: int) -> bool:
    """Only a placeholder that OVERLAPS the match exempts it.

    Anything merely nearby (an HTML tag, a ${VAR} a few chars away) must not
    hide a real token."""
    for match in PLACEHOLDER_RE.finditer(text):
        if match.start() < end and match.end() > start:
            return True
        if match.start() >= end:
            break
    return False


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


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

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
    args = tool_input.get("tool_input") if "tool_input" in tool_input else tool_input
    if not isinstance(args, dict):
        return "", flatten_text(tool_input)
    path = str(args.get("path") or "")
    body = flatten_text(args.get("body") or "")
    return path, body


def normalize_mcp_tool_name(name: str) -> str:
    return (name or "").strip().lower()


def is_gitlab_tool(name: str) -> bool:
    lower = normalize_mcp_tool_name(name)
    return lower.startswith("gitlab__") or lower.startswith("gitlab_")


def gitlab_tool_action(name: str) -> str:
    lower = normalize_mcp_tool_name(name)
    if lower.startswith("gitlab__"):
        return lower[len("gitlab__") :]
    if lower.startswith("gitlab_"):
        return lower[len("gitlab_") :]
    return lower


GITLAB_READ_HEADS = {
    "get", "list", "search", "my", "whoami", "download", "compare", "validate",
    "view", "show", "fetch", "read", "mr", "discussions",
}
GITLAB_WRITE_HEADS = {
    "create", "update", "delete", "merge", "approve", "unapprove", "publish", "upload",
    "award", "invite", "revoke", "cancel", "retry", "play", "promote", "protect",
    "unprotect", "transfer", "move", "fork", "rebase", "revert", "subscribe",
    "unsubscribe", "set", "add", "remove", "edit", "patch", "bulk", "accept", "reject",
    "ban", "block", "unblock", "share", "unshare", "start", "stop", "trigger", "export",
    "import", "post", "put",
}


def classify_gitlab_tool(name: str, tool_input: Any) -> list[str]:
    """Flag GitLab MCP mutations. Reads (get_/list_/search_/whoami/...) stay quiet."""
    if not is_gitlab_tool(name):
        return []
    action = gitlab_tool_action(name)
    findings: list[str] = []

    args = tool_input
    if isinstance(tool_input, dict) and "tool_input" in tool_input:
        inner = tool_input.get("tool_input")
        if isinstance(inner, dict):
            args = inner
    if isinstance(args, dict) and args.get("dry_run") is True:
        return []

    parts = [p for p in action.replace("-", "_").split("_") if p]
    head = parts[0] if parts else ""
    if head in GITLAB_READ_HEADS and head not in GITLAB_WRITE_HEADS:
        return []

    irreversible = False
    for tok in GITLAB_IRREVERSIBLE_TOKENS:
        if action == tok or action.startswith(tok + "_") or action.endswith("_" + tok) or f"_{tok}_" in f"_{action}_":
            irreversible = True
            break
    if head == "merge" or action in {"merge", "merge_merge_request"} or action.startswith("merge_"):
        irreversible = True
    if head == "delete" or action.startswith("delete_"):
        irreversible = True

    write = irreversible or head in GITLAB_WRITE_HEADS
    if not write:
        write = any(
            action.startswith(tok) or f"_{tok}" in f"_{action}"
            for tok in (
                "create_", "update_", "delete_", "merge_", "approve_", "unapprove_",
                "publish_", "upload_", "bulk_",
            )
        )
    if not write:
        return []

    label = f"GitLab MCP {action or name}"
    if irreversible:
        findings.append(f"irreversible {label}")
    findings.append(f"live GitLab write {label}")

    if isinstance(args, dict):
        bits: list[str] = []
        for key in (
            "project_id", "merge_request_iid", "issue_iid", "noteable_iid",
            "pipeline_id", "branch", "source_branch", "target_branch",
        ):
            val = args.get(key)
            if val is not None and str(val).strip():
                bits.append(f"{key}={redact_text(str(val))[:80]}")
        if bits:
            findings.append("GitLab target " + ", ".join(bits[:6]))
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
    gitlab_host = mentions_gitlab_host(command)
    if gitlab_host and (
        GITLAB_HTTP_MUTATION_RE.search(command)
        or re.search(r"(?i)\bcurl\b[^\n]*\s-d\b", command)
        or re.search(r"(?i)\bcurl\b[^\n]*\b--data\b", command)
        or re.search(r"(?i)\bcurl\b[^\n]*\s-F\b", command)
        or re.search(r"(?i)\b(POST|PUT|PATCH|DELETE)\b", command)
    ):
        if re.search(r"(?i)(-X|--request)\s*GET\b", command):
            return findings
        if re.search(r"(?i)\bmethod\s*[:=]\s*['\"]?GET\b", command):
            return findings
        findings.append("live GitLab HTTP mutation toward GitLab host")
    if (re.search(r"(?i)api/v4", command) or gitlab_host) and re.search(
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
        elif method == "POST" and "/buildQueue" in path:
            compact = re.sub(r"\s+", "", body).lower()
            if "personal" not in compact or "personal:true" not in compact.replace('"', ""):
                findings.append("team-visible TeamCity build (not personal)")
        findings.append(f"live TeamCity write {method} {path or '(no path)'}")

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
        if SUSPICIOUS_SHELL.search(strip_heredocs(command)):
            findings.append("suspicious shell command")
        findings.extend(secret_read_findings(command))
        findings.extend(remote_access_findings(command, load_live_hosts()))
        findings.extend(classify_gitlab_shell(command))

    # Belt and braces: nothing that leaves the guard carries a literal secret.
    return [redact_text(item) for item in findings]


def finding_kinds(findings: list[str]) -> list[str]:
    """Short, payload-free tags for the ledger."""
    kinds: list[str] = []

    def add(kind: str) -> None:
        if kind not in kinds:
            kinds.append(kind)

    for item in findings:
        if item.startswith("secret("):
            for part in item[len("secret(") : -1].split(","):
                add("secret:" + part.strip())
        elif item.startswith("secret-read("):
            add("secret-read:" + item[len("secret-read(") : -1])
        elif item.startswith("interactive SSH"):
            add("ssh-interactive")
        elif item.startswith("destructive SSH"):
            add("ssh-destructive")
        elif item.startswith("SSH to"):
            add("ssh")
        elif " write toward " in item:
            add("remote-write")
        elif " toward " in item or " session on " in item:
            add("remote-copy")
        elif item.startswith("irreversible TeamCity"):
            add("teamcity-irreversible")
        elif item.startswith("team-visible TeamCity"):
            add("teamcity-team-build")
        elif item.startswith("live TeamCity write"):
            add("teamcity-write")
        elif item.startswith("irreversible GitLab"):
            add("gitlab-irreversible")
        elif item.startswith("live GitLab"):
            add("gitlab-write")
        elif item.startswith("suspicious shell"):
            add("suspicious")
        elif item.startswith("guard could not evaluate"):
            add("fail-open")
    return kinds


# ---------------------------------------------------------------------------
# Ledger + marker (the awareness layer)
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: str, entry: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def ledger_write(
    event: dict[str, Any] | None,
    *,
    stage: str,
    decision: str,
    tool: str = "",
    kinds: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """One line, never the payload."""
    event = event or {}
    entry: dict[str, Any] = {
        "ts": _now(),
        "session": session_id_of(event),
        "runtime": runtime_of(event),
        "event": hook_event_name(event) or stage,
        "stage": stage,
        "tool": tool[:120],
        "kinds": kinds or [],
        "decision": decision,
    }
    transcript = event.get("transcript_path")
    if transcript:
        entry["transcript"] = str(transcript)
    if event.get("_coerced_shape"):
        entry["shape"] = "coerced"
    if note:
        entry["note"] = redact_text(note)[:200]
    _append_jsonl(LEDGER_FILE, entry)
    return entry


def marker_add(event: dict[str, Any] | None, reason: str, kinds: list[str] | None = None) -> None:
    event = event or {}
    entry = {
        "ts": _now(),
        "session": session_id_of(event),
        "runtime": runtime_of(event),
        "reason": reason,
        "kinds": kinds or [],
    }
    transcript = event.get("transcript_path")
    if transcript:
        entry["transcript"] = str(transcript)
    _append_jsonl(MARKER_FILE, entry)


def marker_entries() -> list[dict[str, Any]]:
    return _read_jsonl(MARKER_FILE)


def marker_ack(session: str) -> int:
    rows = marker_entries()
    keep = [row for row in rows if str(row.get("session")) != session]
    removed = len(rows) - len(keep)
    try:
        if keep:
            with open(MARKER_FILE, "w", encoding="utf-8") as handle:
                for row in keep:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        elif os.path.exists(MARKER_FILE):
            os.remove(MARKER_FILE)
    except OSError:
        pass
    return removed


def ledger_for_session(session: str) -> list[dict[str, Any]]:
    return [row for row in _read_jsonl(LEDGER_FILE) if str(row.get("session")) == session]


def session_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"asked": 0, "noted": 0, "redactions": 0, "secret_reads": 0, "fail_opens": 0, "coerced": 0}
    for row in rows:
        decision = str(row.get("decision") or "")
        kinds = [str(k) for k in row.get("kinds") or []]
        if decision == "ask":
            counts["asked"] += 1
        if decision == "allow-noted":
            counts["noted"] += 1
        if decision == "exposure" and str(row.get("stage")) == "pre":
            counts["redactions"] += 1  # secret literal in input: exposed, not redactable
        if decision == "redacted":
            counts["redactions"] += 1
        if str(row.get("stage")) == "post" and any(k.startswith("secret-read") for k in kinds):
            counts["secret_reads"] += 1
        if decision == "fail-open":
            counts["fail_opens"] += 1
        if row.get("shape") == "coerced":
            counts["coerced"] += 1
    return counts


def review_command(session: str) -> str:
    script = os.path.abspath(__file__)
    return f"python3 {script} review {session}"


def needs_review(counts: dict[str, int]) -> bool:
    return bool(counts["redactions"] or counts["secret_reads"] or counts["fail_opens"])


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def findings_reason(findings: list[str]) -> str:
    return (
        f"{OPERATOR}, live-ops-guard needs your OK before this call.\n"
        + "\n".join(f"- {item}" for item in findings)
        + "\nApprove only if you intended this on the live server / GitLab."
    )


def fail_open_message(event: dict[str, Any] | None, why: str) -> str:
    session = session_id_of(event)
    head = (
        f"{OPERATOR}, live-ops-guard could NOT evaluate this call ({why}) and let it through. "
        "Treat it as unguarded."
    )
    return head + "\n" + exposure_notice("guard-fail-open", [why], session, runtime_of(event))


def exposure_note(kinds: list[str], session: str, runtime: str, redaction_applied: bool) -> str:
    base = (
        f"{OPERATOR}, live-ops-guard found secret-like values in a tool result "
        f"({', '.join(kinds)}). Do not echo or reuse them."
    )
    if redaction_applied:
        base += (
            " Redaction was requested via the hook output; if this runtime ignores "
            "updated tool output the original values are STILL in the transcript."
        )
    else:
        base += " The original values are in the transcript."
    base += f" Session {session} ({runtime}) is marked for trace review: `{review_command(session)}`."
    return base


# What happened → (one-line what, recommended option). Kept short: this is read
# in a permission-style interruption, not a report.
EXPOSURE_WHERE = {
    "secret-in-tool-result": "a secret-like value came back in a tool RESULT",
    "secret-store-read": "a secret store was READ (its contents are now in the transcript)",
    "secret-in-tool-input": "the agent put a secret-like value in a tool INPUT (it is already in the transcript)",
    "guard-fail-open": "the guard could not evaluate a call and let it through unguarded",
}


def recommended_for(where: str, kinds: list[str], runtime: str, redaction_applied: bool) -> str:
    if where == "secret-in-tool-result" and redaction_applied and runtime == "claude":
        return (
            "Proceed. Claude Code applied the redaction before the value reached the model "
            "(verified for Bash and MCP results); still run the trace review at the end."
        )
    if where == "secret-in-tool-result" and redaction_applied:
        return (
            "Stop and confirm in the transcript whether the value was actually replaced; "
            "if it is still there, rotate it before proceeding."
        )
    if where == "secret-store-read":
        return "Stop and rotate what that store held, then proceed. Values from a secret store are not pattern-redacted."
    if where == "secret-in-tool-input":
        return "Stop: rotate the value now (it cannot be unwritten from the transcript), then re-run with a ${VAR} reference."
    if where == "guard-fail-open":
        return "Proceed, but read the ledger row for this call and re-run it in gate mode if it touched a live host."
    return "Stop and review the trace before doing anything else on a live host."


def exposure_notice(
    where: str,
    kinds: list[str],
    session: str,
    runtime: str,
    tool: str = "",
    redaction_applied: bool = False,
) -> str:
    """The interruption the operator sees: what was exposed, and three ways forward.

    Not a yes/no question. The agent is told to present these options and wait."""
    what = EXPOSURE_WHERE.get(where, where)
    shown_tool = f" (`{tool}`)" if tool else ""
    lines = [
        f"EXPOSURE — {OPERATOR}, {what}{shown_tool}: {', '.join(kinds) or 'unknown kind'}.",
        f"Session {session} ({runtime}) is now marked NEEDS_TRACE_REVIEW; the guard will not clear it.",
        "",
        "Options:",
        f"  1. Proceed — keep working; review the trace at the end: {review_command(session)}",
        "  2. Stop — end here; rotate the exposed credential now.",
        f"  3. Recommended — {recommended_for(where, kinds, runtime, redaction_applied)}",
    ]
    return "\n".join(lines)


def exposure_agent_instruction(notice: str) -> str:
    return (
        "live-ops-guard EXPOSURE. Stop the current task. Show the operator this notice verbatim "
        "and ask them to pick option 1, 2 or 3 (use your ask-the-user tool if you have one). "
        "Do not continue, retry, or quote the exposed value until they choose. Never run `--ack` for them.\n\n"
        + notice
    )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def _pre_output(runtime: str, decision: str, reason: str = "", loud: str = "") -> dict[str, Any]:
    """Shape the pre decision for the runtime. `loud` is a fail-open message."""
    if runtime == "cursor":
        if decision == "ask":
            return {
                "permission": "ask",
                "user_message": reason,
                "agent_message": (
                    "live-ops-guard needs the operator's OK. Do not retry this call. "
                    "Treat a reject as final.\n" + reason
                ),
            }
        out: dict[str, Any] = {"permission": "allow"}
        if loud:
            out["user_message"] = loud
            out["agent_message"] = loud
        return out
    if runtime == "claude":
        if decision == "ask":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        out = {}
        if loud:
            out = {
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": loud},
                "systemMessage": loud,
            }
        return out
    # grok
    if decision == "ask":
        return {"decision": "ask", "reason": reason}
    out = {"decision": "allow"}
    if loud:
        out["reason"] = loud
        out["systemMessage"] = loud
    return out


def _pre_notify_output(runtime: str, agent_note: str, user_note: str = "") -> dict[str, Any]:
    """Allow, with context for the agent and (optionally) a notice for the operator."""
    if runtime == "cursor":
        out: dict[str, Any] = {"permission": "allow", "agent_message": agent_note}
        if user_note:
            out["user_message"] = user_note
        return out
    if runtime == "claude":
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": agent_note}}
        if user_note:
            out["systemMessage"] = user_note
        return out
    out = {"decision": "allow", "reason": agent_note}
    if user_note:
        out["systemMessage"] = user_note
    return out


def pre_decision(event: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_event(event)
    findings = classify(event)
    runtime = runtime_of(event)
    tool = tool_name_of(normalized)
    kinds = finding_kinds(findings)
    if not findings:
        if normalized.get("_coerced_shape"):
            ledger_write(normalized, stage="pre", decision="allow", tool=tool, kinds=kinds)
        return _pre_output(runtime, "allow")

    if mode_of() == "gate":
        ledger_write(normalized, stage="pre", decision="ask", tool=tool, kinds=kinds)
        return _pre_output(runtime, "ask", findings_reason(findings))

    # notify mode: the call runs. A secret literal in the INPUT is already an exposure.
    secret_kinds = [k for k in kinds if k.startswith("secret:")]
    if secret_kinds:
        session = session_id_of(normalized)
        ledger_write(normalized, stage="pre", decision="exposure", tool=tool, kinds=kinds)
        marker_add(normalized, "secret-in-tool-input", secret_kinds)
        notice = exposure_notice(
            "secret-in-tool-input",
            [k.split(":", 1)[1] for k in secret_kinds],
            session,
            runtime,
            tool=tool,
        )
        return _pre_notify_output(runtime, exposure_agent_instruction(notice), notice)

    ledger_write(normalized, stage="pre", decision="allow-noted", tool=tool, kinds=kinds)
    agent_note = (
        "live-ops-guard (notify mode) let this call run and recorded it in the ledger: "
        + "; ".join(findings)
        + ". If it is a live write or ssh the operator did not ask for, stop and say so."
    )
    return _pre_notify_output(runtime, agent_note)


def _result_blob(event: dict[str, Any]) -> Any:
    for key in (
        "toolResult",
        "tool_result",
        "tool_response",
        "tool_output",
        "result_json",
        "output",
    ):
        if event.get(key) is not None:
            return event.get(key)
    return None


def post_decision(event: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_event(event)
    runtime = runtime_of(event)
    session = session_id_of(event)
    name = tool_name_of(normalized)

    # Exposure by construction: the INPUT read a secret store, whatever the output looks like.
    input_findings = classify(event)
    read_kinds = [k for k in finding_kinds(input_findings) if k.startswith("secret-read")]

    result = _result_blob(event)
    text = flatten_text(result)
    secrets = find_secrets(text)

    if not secrets and not read_kinds:
        return {}

    kinds = ["secret:" + s for s in secrets] + read_kinds
    if secrets:
        ledger_write(normalized, stage="post", decision="redacted", tool=name, kinds=kinds)
        marker_add(normalized, "secret-in-tool-result", kinds)
    else:
        ledger_write(normalized, stage="post", decision="exposure", tool=name, kinds=kinds)
        marker_add(normalized, "secret-store-read", kinds)

    shown_kinds = secrets + [k.split(":", 1)[1] + " (read)" for k in read_kinds]
    where = "secret-in-tool-result" if secrets else "secret-store-read"
    notice = exposure_notice(where, shown_kinds, session, runtime, tool=name, redaction_applied=bool(secrets))
    instruction = exposure_agent_instruction(notice)

    if runtime == "cursor":
        out: dict[str, Any] = {"additional_context": instruction, "user_message": notice}
        if secrets:
            redacted = redact_text(text)
            if event.get("mcp_server_name") or "gitlab__" in name or "teamcity__" in name:
                try:
                    out["updated_mcp_tool_output"] = json.loads(redacted)
                except json.JSONDecodeError:
                    out["updated_mcp_tool_output"] = {"redacted": redacted}
        return out

    # decision=block does not undo the call (it already ran); it stops the agent and
    # hands it the notice, so the operator gets the options instead of a silent continue.
    hook_out: dict[str, Any] = {
        "decision": "block",
        "reason": instruction,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": instruction,
        },
        "systemMessage": notice,
    }
    if secrets:
        # Always request redaction, for MCP and shell results alike. Whether the
        # runtime honours it is stated in the note; the ledger records exposure either way.
        if isinstance(result, dict):
            try:
                hook_out["hookSpecificOutput"]["updatedToolOutput"] = json.loads(
                    redact_text(json.dumps(result, ensure_ascii=False))
                )
            except json.JSONDecodeError:
                hook_out["hookSpecificOutput"]["updatedToolOutput"] = redact_text(text)
        else:
            hook_out["hookSpecificOutput"]["updatedToolOutput"] = redact_text(text)
    return hook_out


def start_decision(event: dict[str, Any]) -> dict[str, Any]:
    """Session start: nag about sessions still waiting for a trace review."""
    runtime = runtime_of(event)
    rows = marker_entries()
    if not rows:
        return {}
    by_session: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(str(row.get("session")), []).append(row)
    lines = [
        f"{OPERATOR}, {len(by_session)} earlier session(s) exposed secret-like data or ran unguarded "
        "and still need a trace review:"
    ]
    for session, items in list(by_session.items())[:10]:
        reasons = sorted({str(i.get("reason")) for i in items})
        lines.append(f"- {session} ({items[0].get('runtime', '?')}): {', '.join(reasons)} x{len(items)}")
    lines.append(f"Run `{review_command('--last')}` (or `/live-ops-guard review`). The marker is not cleared until you --ack it.")
    text = "\n".join(lines)
    if runtime == "cursor":
        return {"additional_context": text, "user_message": text}
    return {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
        "systemMessage": text,
    }


def stop_summary(session: str) -> str:
    rows = ledger_for_session(session)
    counts = session_counts(rows)
    if not rows:
        return ""
    lines = [
        f"live-ops-guard — session {session} summary for {OPERATOR}",
        f"  guarded calls asked: {counts['asked']}",
        f"  live calls allowed and noted (notify mode): {counts['noted']}",
        f"  secret-like values redacted: {counts['redactions']}",
        f"  secret-store reads: {counts['secret_reads']}",
        f"  guard fail-opens: {counts['fail_opens']}",
    ]
    if counts["coerced"]:
        lines.append(f"  calls with an unexpected payload shape (scanned anyway): {counts['coerced']}")
    if needs_review(counts):
        lines.append(f"  Trace review required: YES -> {review_command(session)}")
    else:
        lines.append("  Trace review required: no")
    return "\n".join(lines)


def stop_decision(event: dict[str, Any]) -> dict[str, Any]:
    session = session_id_of(event)
    rows = ledger_for_session(session)
    counts = session_counts(rows)
    if rows and needs_review(counts) and not any(
        str(r.get("session")) == session for r in marker_entries()
    ):
        marker_add(event, "session-summary", [])
    text = stop_summary(session)
    if not text:
        return {}
    return {"systemMessage": text, "user_message": text, "additional_context": text}


def _fail_open(event: dict[str, Any] | None, why: str) -> dict[str, Any]:
    """Allow, but loudly, and leave a trail."""
    runtime = runtime_of(event)
    try:
        ledger_write(event, stage="pre", decision="fail-open", tool="", kinds=["fail-open"], note=why)
        marker_add(event, "guard-fail-open", ["fail-open"])
    except Exception:  # noqa: BLE001 — never let the trail break the allow
        pass
    loud = fail_open_message(event, why)
    if runtime == "grok":
        return {"decision": "allow", "reason": loud, "systemMessage": loud}
    return _pre_output(runtime, "allow", loud=loud)


# ---------------------------------------------------------------------------
# review CLI
# ---------------------------------------------------------------------------

def review_cli(args: list[str]) -> int:
    ack = "--ack" in args
    positional = [a for a in args if not a.startswith("--")]
    session = positional[0] if positional else ""
    rows_marker = marker_entries()
    if "--last" in args or session == "--last":
        session = str(rows_marker[-1].get("session")) if rows_marker else ""
        if not session:
            print("live-ops-guard: nothing is waiting for review.")
            return 0

    if not session:
        if not rows_marker:
            print("live-ops-guard: nothing is waiting for review.")
            return 0
        by_session: dict[str, list[dict[str, Any]]] = {}
        for row in rows_marker:
            by_session.setdefault(str(row.get("session")), []).append(row)
        print(f"{OPERATOR}, these sessions still need a trace review:")
        for sid, items in by_session.items():
            reasons = sorted({str(i.get("reason")) for i in items})
            transcript = next((i.get("transcript") for i in items if i.get("transcript")), "")
            print(f"  {sid}  [{items[0].get('runtime', '?')}]  {', '.join(reasons)}  x{len(items)}")
            if transcript:
                print(f"      transcript: {transcript}")
        print(f"\nNext: {review_command('<session>')}")
        return 0

    rows = ledger_for_session(session)
    marks = [r for r in rows_marker if str(r.get("session")) == session]
    if not rows and not marks:
        print(f"live-ops-guard: no ledger or marker entries for session {session}.")
        return 1
    print(stop_summary(session) or f"live-ops-guard — session {session}: no ledger rows")
    print("\nLedger:")
    for row in rows:
        kinds = ",".join(str(k) for k in row.get("kinds") or []) or "-"
        print(f"  {row.get('ts')}  {row.get('stage'):4}  {row.get('decision'):9}  {row.get('tool') or '-'}  {kinds}")
    transcript = next((r.get("transcript") for r in rows + marks if r.get("transcript")), "")
    print("\nNext: analyse the trace.")
    if transcript:
        print(f"  /trace-analysis {transcript}")
    else:
        print(f"  /trace-analysis <transcript of session {session}>")
    print(f"  /trace-watch {session}        (if the session is still running)")
    print("Rotate any credential the ledger says was exposed. Then:")
    print(f"  {review_command(session)} --ack")
    if ack:
        removed = marker_ack(session)
        print(f"\nacknowledged: removed {removed} marker entr{'y' if removed == 1 else 'ies'} for {session}")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "review":
        return review_cli(sys.argv[2:])

    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(_fail_open(None, f"unreadable hook payload: {type(exc).__name__}")))
        return 0

    event_name = hook_event_name(event)
    argv_event = argv_value("--event")

    is_post = argv_event in {"post", "cursor-post"} or "post_tool_use" in event_name or event_name in CURSOR_POST_EVENTS
    is_start = argv_event == "start" or event_name in START_EVENTS
    is_stop = argv_event == "stop" or event_name in STOP_EVENTS

    try:
        if is_start:
            print(json.dumps(start_decision(event)))
        elif is_stop:
            print(json.dumps(stop_decision(event)))
        elif is_post:
            print(json.dumps(post_decision(event)))
        else:
            print(json.dumps(pre_decision(event)))
    except Exception as exc:  # noqa: BLE001 — fail open, loudly
        print(json.dumps(_fail_open(event, f"guard error {type(exc).__name__}")))
        print(f"live-ops-guard error: {type(exc).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
