#!/usr/bin/env python3
"""Decide picture holds. Audio speed stays untouched."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

TAIL = 0.45


def duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--cues", type=Path, required=True)
    parser.add_argument("--clips-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cues = json.loads(args.cues.read_text())
    if not cues:
        raise SystemExit("cues.json is empty")
    video_end = duration(args.video)
    starts = [float(c["start"]) for c in cues]
    if starts != sorted(starts):
        raise SystemExit("cues must be ordered by start")
    if starts[-1] >= video_end:
        raise SystemExit("last cue starts after the video ends")

    bounds: list[dict[str, object]] = []
    if starts[0] >= 1.0:
        bounds.append(
            {
                "i": -1,
                "a": 0.0,
                "gap": starts[0],
                "speech": 0.0,
                "pad": 0.0,
                "caption": "",
                "wav": "",
            }
        )
    for i, cue in enumerate(cues):
        wav = args.clips_dir / f"{i:02d}.wav"
        if not wav.is_file():
            raise SystemExit(f"missing {wav}")
        a = 0.0 if i == 0 and starts[0] < 1.0 else starts[i]
        b = starts[i + 1] if i + 1 < len(cues) else video_end
        speech = duration(wav)
        gap = b - a
        if gap <= 0:
            raise SystemExit(f"cue {i} has no picture window")
        pad = max(0.0, speech + TAIL - gap)
        bounds.append(
            {
                "i": i,
                "a": a,
                "gap": gap,
                "speech": speech,
                "pad": pad,
                "caption": str(cue["caption"]),
                "wav": str(wav),
            }
        )
        mark = " PAD" if pad > 0.05 else ""
        print(f"{i:02d} gap={gap:6.2f} speech={speech:6.2f} pad={pad:5.2f}{mark}")
    args.out.write_text(json.dumps(bounds, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
