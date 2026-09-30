#!/usr/bin/env python3
"""Detection-quality eval for live-ops-guard.

Scores guard.py's secret and secret-store-read detectors against a labelled
corpus (evals/detection/cases.jsonl). Reports precision / recall per tier and
per kind, lists every miss and false alarm, and exits 1 if any `must` case
fails. `stretch` cases are reported only.

  python3 scripts/eval-detection.py            # full report
  python3 scripts/eval-detection.py --quiet    # one line per failure + totals
  python3 scripts/eval-detection.py --only tp- # filter by id prefix

Add a case when a real session shows a miss or a false alarm: the corpus is
the memory of what bit us. No real secrets in it, ever."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("LIVE_OPS_GUARD_HOME", tempfile.mkdtemp(prefix="live-ops-guard-eval-"))
spec = importlib.util.spec_from_file_location("live_ops_guard", ROOT / "hooks" / "guard.py")
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


TEMPLATE_RE = re.compile(r"\{\{(?:lit:([^}]*)|([^*}]+)\*(\d+))\}\}")


def expand(text: str) -> str:
    """The corpus never holds a matchable token at rest (push protection, secret scanners,
    grep). `{{A*36}}` → 36 As; `{{Ab1*20}}` → 'Ab1' twenty times; `{{lit:xyz}}` → xyz.
    Prefixes and documented example values are split into two lit: parts."""
    return TEMPLATE_RE.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2) * int(m.group(3)), text)


def detect(case: dict) -> list[str]:
    kind = case["kind"]
    text = expand(case["text"])
    if kind == "secret":
        return guard.find_secrets(text)
    if kind == "read":
        return [f[len("secret-read(") : -1] for f in guard.secret_read_findings(text)]
    if kind == "shell":
        return guard.finding_kinds(guard.classify({"toolName": "run_terminal_command", "toolInput": {"command": text}}))
    raise ValueError(kind)


def main() -> int:
    quiet = "--quiet" in sys.argv
    only = ""
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    cases = [json.loads(l) for l in (ROOT / "evals" / "detection" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if only:
        cases = [c for c in cases if c["id"].startswith(only)]

    per_tier: dict[str, Counter] = defaultdict(Counter)
    per_kind_tp: Counter = Counter()
    per_kind_fp: Counter = Counter()
    per_kind_fn: Counter = Counter()
    failures: list[str] = []
    must_failed = 0

    for case in cases:
        got = set(detect(case))
        want = set(case["expect"])
        ok = got == want
        per_tier[case["tier"]]["total"] += 1
        per_tier[case["tier"]]["pass" if ok else "fail"] += 1
        for k in got & want:
            per_kind_tp[k] += 1
        for k in got - want:
            per_kind_fp[k] += 1
        for k in want - got:
            per_kind_fn[k] += 1
        if not ok:
            if case["tier"] == "must":
                must_failed += 1
            miss = sorted(want - got)
            extra = sorted(got - want)
            what = []
            if miss:
                what.append("MISSED " + ",".join(miss))
            if extra:
                what.append("FALSE-ALARM " + ",".join(extra))
            note = f"  ({case['note']})" if case.get("note") else ""
            failures.append(f"{'MUST ' if case['tier']=='must' else 'stretch'} {case['id']:<22} {'; '.join(what)}{note}")

    if not quiet:
        print("live-ops-guard detection eval")
        print(f"  corpus: {len(cases)} cases")
    for tier in ("must", "stretch"):
        c = per_tier.get(tier)
        if not c:
            continue
        print(f"  {tier:<8} {c['pass']}/{c['total']} pass")
    kinds = sorted(set(per_kind_tp) | set(per_kind_fp) | set(per_kind_fn))
    if not quiet and kinds:
        print("\n  per kind        tp  fp  fn  precision  recall")
        for k in kinds:
            tp, fp, fn = per_kind_tp[k], per_kind_fp[k], per_kind_fn[k]
            prec = tp / (tp + fp) if tp + fp else 1.0
            rec = tp / (tp + fn) if tp + fn else 1.0
            flag = "" if fp == 0 and fn == 0 else "   <--"
            print(f"  {k:<22} {tp:>3} {fp:>3} {fn:>3}   {prec:>6.2f}    {rec:>5.2f}{flag}")
    if failures:
        print("\n  failures:")
        for f in failures:
            print("   ", f)
    print(f"\n  must failures: {must_failed}")
    return 1 if must_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
