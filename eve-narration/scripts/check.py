#!/usr/bin/env python3
"""Numeric pass for the Eve narration render."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def ffprobe_audio(path: Path) -> tuple[float, str]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        raise SystemExit("FAIL no audio stream")
    return float(data["format"]["duration"]), str(streams[0]["codec_name"])


def levels(path: Path, start: float, length: float) -> tuple[float, float]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    mean = maxv = None
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].replace("dB", "").strip())
        if "max_volume:" in line:
            maxv = float(line.split("max_volume:")[1].replace("dB", "").strip())
    if mean is None or maxv is None:
        raise SystemExit("FAIL could not read loudness")
    return mean, maxv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.timeline.read_text())
    spoken = [r for r in rows if float(r["speech"]) > 0.05]
    if not spoken:
        raise SystemExit("FAIL no spoken cues")
    video_dur, codec = ffprobe_audio(args.video)
    failures: list[str] = []
    for i, row in enumerate(spoken):
        end = float(row["out_start"]) + float(row["speech"])
        if end > video_dur + 0.05:
            failures.append(f"cue {row['i']} runs past the video")
        if i + 1 < len(spoken):
            gap = float(spoken[i + 1]["out_start"]) - end
            if gap < 0.25:
                failures.append(f"cue {row['i']} gap {gap:.3f}s")
    sample = spoken[0]
    length = min(3.0, max(0.8, float(sample["speech"]) - 0.4))
    mean, peak = levels(args.video, float(sample["out_start"]) + 0.3, length)
    print(f"codec={codec} duration={video_dur:.2f} mean={mean:.1f} peak={peak:.1f}")
    if not (-24.0 <= mean <= -12.0):
        failures.append(f"mean volume {mean:.1f} dB")
    if not (-10.0 <= peak <= -1.0):
        failures.append(f"peak volume {peak:.1f} dB")
    if failures:
        raise SystemExit("FAIL " + "; ".join(failures))
    print("PASS")


if __name__ == "__main__":
    main()
