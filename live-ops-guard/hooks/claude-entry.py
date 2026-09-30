#!/usr/bin/env python3
"""Claude Code hook entry: run the shared live-ops-guard script.

The canonical copy (and the ledger, marker and host files next to it) lives
under ~/.grok/hooks/live-ops-guard/ so every runtime shares one trail."""
from __future__ import annotations

import runpy
from pathlib import Path

GUARD = Path.home() / ".grok" / "hooks" / "live-ops-guard" / "guard.py"
runpy.run_path(str(GUARD), run_name="__main__")
