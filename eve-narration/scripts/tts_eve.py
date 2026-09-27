#!/usr/bin/env python3
"""Synthesize one Eve wav per cue. Pace and voice live here."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

VOICE = "eve"
LANGUAGE = "pt-BR"
SPEED = 0.96
API = "https://api.x.ai/v1/tts"


def token() -> str:
    import os

    env = os.environ.get("XAI_API_KEY", "").strip()
    if env:
        return env
    auth = json.loads(Path.home().joinpath(".grok/auth.json").read_text())
    return str(next(iter(auth.values()))["key"])


def synthesize(text: str, dest: Path, bearer: str) -> None:
    body = json.dumps(
        {
            "text": text,
            "voice_id": VOICE,
            "language": LANGUAGE,
            "speed": SPEED,
            "text_normalization": True,
            "output_format": {"codec": "wav", "sample_rate": 44100},
        }
    ).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = dest.with_suffix(".part.wav")
                raw.write_bytes(resp.read())
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
    else:
        raise SystemExit(f"tts failed for {dest.name}: {last_error}")
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    raw.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cues", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    cues = json.loads(args.cues.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    bearer = token()
    for i, cue in enumerate(cues):
        dest = args.out_dir / f"{i:02d}.wav"
        synthesize(str(cue["spoken"]), dest, bearer)
        print(f"{i:02d} {dest.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
