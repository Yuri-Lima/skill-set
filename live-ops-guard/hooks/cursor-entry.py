#!/usr/bin/env python3
"""Cursor hook entry: run the shared live-ops-guard script."""
from __future__ import annotations

import runpy
from pathlib import Path

GUARD = Path.home() / ".grok" / "hooks" / "live-ops-guard" / "guard.py"
runpy.run_path(str(GUARD), run_name="__main__")
