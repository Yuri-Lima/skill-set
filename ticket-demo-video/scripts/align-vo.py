#!/usr/bin/env python3
"""Lock picture to a finished voice take (radio-edit).

Professionals transcribe first, then cut B-roll onto the word — never the
other way around. This script is that lock:

1. Prefer a Whisper (or compatible) word-timestamp JSON
2. Else map sentences onto ffmpeg silencedetect speech islands, and place
   keywords by character offset inside their sentence

Writes:
  --out-json     full dump (duration, sentences, keywords)
  --out-studio   [{at_ms, action}] for record-studio.mjs
  --out-ui       {preroll, beats:[{id, word, at, go}]} for the live recorder

`at` is when she says the word (studio cards change here).
`go` is at minus --preroll (cursor starts moving so the click lands on the word).

Usage:
  python3 align-vo.py --audio eve.mp4 --script script.txt \\
    --whisper-json words.json \\
    --map "kicker=Ticket,cards=Annual rate,missing=no method,twr=TWR" \\
    --point "cards,twr" --point-hold 2.0 \\
    --out-json align.json --out-studio studio-beats.json --out-ui ui-clock.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def probe_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            path,
        ],
        text=True,
    )
    return float(out.strip())


def speech_islands(
    path: str, noise: str = "-30dB", min_d: float = 0.22
) -> list[tuple[float, float]]:
    """Return (speech_start, speech_end) islands from silencedetect."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-i",
            path,
            "-af",
            f"silencedetect=noise={noise}:d={min_d}",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    starts: list[float] = []
    ends: list[float] = []
    for line in (proc.stderr or "").splitlines():
        if "silence_start:" in line:
            try:
                starts.append(float(line.split("silence_start:")[1].split("|")[0]))
            except (IndexError, ValueError):
                pass
        elif "silence_end:" in line:
            try:
                ends.append(float(line.split("silence_end:")[1].split("|")[0]))
            except (IndexError, ValueError):
                pass
    dur = probe_duration(path)
    islands: list[tuple[float, float]] = []
    # Audio may begin in speech (no leading silence_end) or in silence.
    cursor = 0.0
    events: list[tuple[float, str]] = []
    for t in starts:
        events.append((t, "start"))
    for t in ends:
        events.append((t, "end"))
    events.sort()
    speaking = True  # assume speech until first silence_start, unless we start silent
    if events and events[0][1] == "end":
        speaking = False
        cursor = 0.0
    for t, kind in events:
        if kind == "start" and speaking:
            if t > cursor:
                islands.append((cursor, t))
            speaking = False
        elif kind == "end" and not speaking:
            cursor = t
            speaking = True
    if speaking and dur > cursor:
        islands.append((cursor, dur))
    return islands


def load_whisper_words(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text())
    words: list[dict[str, object]] = []
    if isinstance(data, dict) and "segments" in data:
        for seg in data["segments"]:
            for w in seg.get("words") or []:
                words.append(w)
    elif isinstance(data, list):
        words = data
    return words


def norm_tok(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def tokens(text: str) -> list[str]:
    return [t for t in (norm_tok(p) for p in re.findall(r"[A-Za-z0-9]+", text)) if t]


def find_keyword(
    words: list[dict[str, object]], needle: str, after: float = -1.0
) -> float | None:
    want = tokens(needle)
    if not want:
        return None
    hay = [
        {
            "t": norm_tok(str(w.get("word") or w.get("text") or "")),
            "start": float(w.get("start") or 0),
        }
        for w in words
    ]
    for i in range(len(hay)):
        if hay[i]["start"] < after:
            continue
        got = [hay[j]["t"] for j in range(i, min(i + len(want), len(hay)))]
        if got == want:
            return hay[i]["start"]
    if len(want) == 1:
        for h in hay:
            if h["start"] >= after and want[0] and want[0] in h["t"]:
                return h["start"]
    return None


def place_in_island(
    sentence: str, needle: str, start: float, end: float
) -> float | None:
    sent_toks = tokens(sentence)
    need = tokens(needle)
    if not sent_toks or not need:
        return None
    # find needle token span inside the sentence, then lerp by char weight
    joined = " ".join(sent_toks)
    needle_s = " ".join(need)
    idx = joined.find(needle_s)
    if idx < 0:
        # first token only
        idx = joined.find(need[0])
        if idx < 0:
            return start
        span = len(need[0])
    else:
        span = len(needle_s)
    frac = idx / max(len(joined), 1)
    return start + (end - start) * frac


def parse_map(raw: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not raw.strip():
        return pairs
    for part in raw.split(","):
        if "=" not in part:
            continue
        action, word = part.split("=", 1)
        action, word = action.strip(), word.strip()
        if action and word:
            pairs.append((action, word))
    return pairs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--audio", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--whisper-json")
    p.add_argument("--keywords", default="", help="comma keywords (legacy)")
    p.add_argument(
        "--map",
        default="",
        help='studio/UI action map: "kicker=Ticket,cards=Annual rate,twr=TWR"',
    )
    p.add_argument("--preroll", type=float, default=0.7)
    p.add_argument(
        "--point",
        default="",
        help="comma action ids that should raise Eve's pointing arm",
    )
    p.add_argument("--point-hold", type=float, default=2.0)
    p.add_argument("--out-json")
    p.add_argument("--out-studio")
    p.add_argument("--out-ui")
    args = p.parse_args()

    script = Path(args.script).read_text().strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script) if s.strip()]
    dur = probe_duration(args.audio)
    keys = [k.strip() for k in args.keywords.split(",") if k.strip()]
    mapped = parse_map(args.map)

    out: dict[str, object] = {
        "duration": dur,
        "sentences": [],
        "keywords": {},
        "map": {},
    }

    words: list[dict[str, object]] = []
    if args.whisper_json and Path(args.whisper_json).exists():
        words = load_whisper_words(Path(args.whisper_json))

    if words:
        after = -1.0
        for s in sentences:
            t = find_keyword(words, s.split()[0] if s else "", after=after)
            out["sentences"].append({"text": s, "start": t})
            if t is not None:
                after = t
        after = -1.0
        for k in keys:
            t = find_keyword(words, k, after=after)
            out["keywords"][k] = t
            if t is not None:
                after = t
        after = -1.0
        mapped_times: dict[str, float | None] = {}
        for action, needle in mapped:
            t = find_keyword(words, needle, after=after)
            mapped_times[action] = t
            out["map"][action] = {"word": needle, "at": t}
            if t is not None:
                after = t
    else:
        islands = speech_islands(args.audio)
        for i, s in enumerate(sentences):
            if i < len(islands):
                start, end = islands[i]
            elif islands:
                start, end = islands[-1][1], dur
            else:
                start, end = 0.0, dur
            out["sentences"].append({"text": s, "start": start, "end": end})
        mapped_times = {}
        # Place each mapped keyword inside the sentence that contains it.
        for action, needle in mapped:
            hit: float | None = None
            for sent in out["sentences"]:
                if tokens(needle) and all(
                    tok in tokens(str(sent["text"])) for tok in tokens(needle)[:1]
                ):
                    hit = place_in_island(
                        str(sent["text"]),
                        needle,
                        float(sent["start"] or 0),
                        float(sent.get("end") or (float(sent["start"] or 0) + 2)),
                    )
                    break
            mapped_times[action] = hit
            out["map"][action] = {"word": needle, "at": hit}
        for i, k in enumerate(keys):
            idx = min(i, max(len(out["sentences"]) - 1, 0))
            sent = out["sentences"][idx] if out["sentences"] else {"start": 0.0}
            out["keywords"][k] = sent.get("start")

    point_ids = {p.strip() for p in args.point.split(",") if p.strip()}
    studio = []
    ui_beats = []
    for action, needle in mapped:
        at = mapped_times.get(action)
        if at is None:
            continue
        studio.append({"at": int(round(at * 1000)), "action": action})
        go = max(0.0, at - args.preroll)
        beat: dict[str, object] = {
            "id": action,
            "word": needle,
            "at": round(at, 3),
            "go": round(go, 3),
        }
        if action in point_ids:
            beat["point"] = True
            beat["hold"] = args.point_hold
        ui_beats.append(beat)

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(out, indent=2) + "\n")
    if args.out_studio:
        Path(args.out_studio).write_text(json.dumps(studio, indent=2) + "\n")
    if args.out_ui:
        Path(args.out_ui).write_text(
            json.dumps(
                {"duration": dur, "preroll": args.preroll, "beats": ui_beats},
                indent=2,
            )
            + "\n"
        )

    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
