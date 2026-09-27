#!/usr/bin/env python3
"""Cut holds, mix Eve, burn one caption line at a time."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


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


def video_size(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ],
        text=True,
    )
    w, h = out.strip().split("x")
    return int(w), int(h)


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def lines_of(text: str, width: int = 54) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = (cur + " " + word).strip()
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def ass_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def srt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def escape_ass(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def make_intra(src: Path, dest: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-g",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--clips-dir", type=Path, required=True)
    parser.add_argument("--bounds", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    args = parser.parse_args()
    bounds = json.loads(args.bounds.read_text())
    args.work.mkdir(parents=True, exist_ok=True)
    video_dur = duration(args.video)
    intra = args.work / "intra.mp4"
    if video_dur <= 900:
        make_intra(args.video, intra)
        source = intra
        accurate = False
    else:
        source = args.video
        accurate = True

    seg_dir = args.work / "segs"
    seg_dir.mkdir(exist_ok=True)
    procs: list[tuple[int, subprocess.Popen[bytes]]] = []

    def wait(group: list[tuple[int, subprocess.Popen[bytes]]]) -> None:
        for idx, proc in group:
            err = proc.stderr.read() if proc.stderr else b""
            if proc.wait() != 0:
                (args.work / f"seg-{idx}.log").write_bytes(err)
                raise SystemExit(f"segment {idx} failed")

    for n, block in enumerate(bounds):
        out = seg_dir / f"{n:02d}.mp4"
        vf = "null"
        if float(block["pad"]) > 0.01:
            vf = f"tpad=stop_mode=clone:stop_duration={float(block['pad']):.3f}"
        cmd = ["ffmpeg", "-y"]
        if not accurate:
            cmd += ["-ss", f"{float(block['a']):.3f}", "-t", f"{float(block['gap']):.3f}", "-i", str(source)]
        else:
            cmd += ["-i", str(source), "-ss", f"{float(block['a']):.3f}", "-t", f"{float(block['gap']):.3f}"]
        cmd += [
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
        procs.append((n, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)))
        if len(procs) >= 4:
            wait(procs)
            procs = []
    wait(procs)

    acc = 0.0
    for n, block in enumerate(bounds):
        actual = duration(seg_dir / f"{n:02d}.mp4")
        block["out_start"] = acc
        block["actual"] = actual
        acc += actual

    concat = args.work / "concat.txt"
    concat.write_text("".join(f"file '{seg_dir / f'{n:02d}.mp4'}'\n" for n in range(len(bounds))))
    silent = args.work / "picture.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])

    spoken = [b for b in bounds if float(b["speech"]) > 0.05 and b["wav"]]
    parts: list[str] = []
    labels: list[str] = []
    for k, block in enumerate(spoken):
        ms = int(round(float(block["out_start"]) * 1000))
        fade_out = max(0.08, float(block["speech"]) - 0.08)
        parts.append(
            f"[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out:.3f}:d=0.06,"
            f"adelay={ms}|{ms}[a{k}]"
        )
        labels.append(f"[a{k}]")
    mix = (
        ";".join(parts)
        + ";"
        + "".join(labels)
        + f"amix=inputs={len(spoken)}:duration=longest:dropout_transition=0:normalize=0,"
        + "loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    )
    voiced = args.work / "voiced.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(silent)]
    for block in spoken:
        cmd += ["-i", str(block["wav"])]
    cmd += [
        "-filter_complex",
        mix,
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        str(voiced),
    ]
    subprocess.check_call(cmd)

    width, height = video_size(args.video)
    font = max(16, round(height * 20 / 800))
    margin_v = max(12, round(height * 18 / 800))
    events: list[tuple[float, float, str]] = []
    for block in spoken:
        parts_txt = lines_of(str(block["caption"]))
        weights = [max(1, len(p)) for p in parts_txt]
        total = sum(weights)
        t = float(block["out_start"])
        end_all = t + float(block["speech"])
        for i, (line, weight) in enumerate(zip(parts_txt, weights)):
            t2 = end_all if i == len(parts_txt) - 1 else min(end_all, t + float(block["speech"]) * weight / total)
            events.append((t, t2, line))
            t = t2

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,48,48,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = [
        f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{escape_ass(text)}"
        for a, b, text in events
    ]
    ass = args.work / "subs.ass"
    ass.write_text(header + "\n".join(dialogues) + "\n", encoding="utf-8")
    srt_blocks = [
        f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n"
        for n, (a, b, text) in enumerate(events, 1)
    ]
    args.srt.write_text("\n".join(srt_blocks), encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voiced),
            "-vf",
            f"ass={ass}",
            "-map",
            "0:v",
            "-map",
            "0:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(args.out),
        ]
    )
    (args.work / "timeline.json").write_text(
        json.dumps(
            [
                {
                    "i": b["i"],
                    "out_start": b["out_start"],
                    "speech": b["speech"],
                    "caption": b["caption"],
                }
                for b in bounds
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
