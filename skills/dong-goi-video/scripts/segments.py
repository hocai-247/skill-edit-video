"""Build the output-timeline segment list + a 10 ms RMS envelope of the cut audio.

Two input modes:
  --edl edl.json          video-use EDL (sources + ranges). Best: compose renders straight from
                          the sources, and each range is a segment (zoom can change per range).
  --video cut.mp4         an already-cut file. Jump cuts are detected from frame differences
                          (or given with --cuts t1,t2,...) and become segment boundaries.

Every boundary is snapped to the output frame grid (--fps, default 30) so audio and video of each
segment have identical length (frames * sr / fps samples).

Writes into --edit-dir:
  segments.json  {"fps", "total", "segments": [{"src","start","end","out_start","out_end","label"}]}
  rms_out.npy    10 ms RMS in dBFS on the OUTPUT timeline (for caption timing / voiced pieces)

Usage:
  python segments.py --edit-dir DIR --edl DIR/edl.json [--tail-end 364.55]
  python segments.py --edit-dir DIR --video cut.mp4 [--cuts auto | --cuts 3.2,7.9]
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

FF = "ffmpeg"


def probe_duration(path: str) -> float:
    """VIDEO stream duration. The container duration follows the audio and was 3 frames longer
    than the picture on an iPhone file, which made every later step one frame short."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout.strip()
    if not out or out == "N/A":
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def detect_cuts(video: str, fps: int) -> list[float]:
    """Jump cuts = isolated spikes in mean abs frame difference (talking head: hard cuts only)."""
    raw = subprocess.run([FF, "-v", "error", "-i", video, "-vf", f"fps={fps},scale=160:90,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean((1, 2))
    med = float(np.median(d))
    thr = max(2.0, med * 3.0)
    cuts, near = [], []
    for i in range(1, len(d) - 1):
        # a cut is one big jump between two quieter neighbours (a real cut measured only 2.6x its
        # neighbours, so 2.5x missed it; 2.0x + a printed near-miss list is safer)
        ratio = d[i] / max(d[i - 1], d[i + 1], med)
        if d[i] > thr and ratio > 2.0:
            cuts.append((i + 1) / fps)
        elif d[i] > 0.6 * thr and ratio > 1.4:
            near.append(f"{(i + 1) / fps:.2f} (diff {d[i]:.1f}, x{ratio:.1f})")
    print(f"frame-diff median {med:.2f}, threshold {thr:.2f}, {len(cuts)} cuts: {[round(c, 2) for c in cuts]}")
    if near:
        print("near misses — check these frames, pass --cuts by hand if any is a cut:", ", ".join(near[:12]))
    return cuts


def rms_envelope(segs: list[dict], out: Path) -> None:
    """Concatenate the segments' audio exactly as compose does, then 10 ms RMS (dBFS)."""
    inputs, fc, cat = [], [], ""
    srcs = sorted({s["src"] for s in segs})
    for s in srcs:
        inputs += ["-i", s]
    for i, s in enumerate(segs):
        k = srcs.index(s["src"])
        fc.append(f"[{k}:a]atrim=start={s['start']:.6f}:end={s['end']:.6f},asetpts=PTS-STARTPTS[a{i}]")
        cat += f"[a{i}]"
    fc.append(f"{cat}concat=n={len(segs)}:v=0:a=1,aresample=16000,aformat=channel_layouts=mono[o]")
    raw = subprocess.run([FF, "-v", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[o]",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    h = 160
    n = len(x) // h
    db = 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(1) + 1e-12))
    np.save(out, db)
    print(f"rms_out.npy: {n / 100:.2f}s, noise floor p10 {np.percentile(db, 10):.1f} dB, speech p90 {np.percentile(db, 90):.1f} dB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", required=True)
    ap.add_argument("--edl")
    ap.add_argument("--video")
    ap.add_argument("--cuts", default="auto", help="'auto', 'none' or comma-separated seconds (video mode)")
    ap.add_argument("--tail-end", type=float, help="EDL mode: extend the LAST range to this source time")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--total-frames", type=int, help="video mode: force the output length (frames)")
    a = ap.parse_args()
    edit = Path(a.edit_dir).resolve()
    fps = a.fps
    snap = lambda t: round(t * fps) / fps  # noqa: E731

    ranges = []
    if a.edl:
        edl = json.loads(Path(a.edl).read_text())
        base = Path(a.edl).resolve().parent
        for i, r in enumerate(edl["ranges"]):
            src = edl["sources"][r["source"]]
            src = str((base / src).resolve()) if not Path(src).is_absolute() else src
            end = a.tail_end if (a.tail_end and i == len(edl["ranges"]) - 1) else r["end"]
            ranges.append((src, snap(r["start"]), snap(end), r.get("quote", "")))
    elif a.video:
        v = str(Path(a.video).resolve())
        dur = a.total_frames / fps if a.total_frames else snap(probe_duration(v))
        cuts = [] if a.cuts == "none" else detect_cuts(v, fps) if a.cuts == "auto" else [float(c) for c in a.cuts.split(",")]
        edges = [0.0] + [snap(c) for c in cuts if 0.2 < c < dur - 0.2] + [dur]
        ranges = [(v, s, e, "") for s, e in zip(edges, edges[1:]) if e - s >= 1 / fps]
    else:
        ap.error("give --edl or --video")

    segs, off = [], 0.0
    for src, s, e, label in ranges:
        d = round((e - s) * fps) / fps
        segs.append({"src": src, "start": s, "end": s + d, "out_start": round(off, 4), "out_end": round(off + d, 4), "label": label})
        off += d
    (edit / "segments.json").write_text(json.dumps({"fps": fps, "total": round(off, 4), "segments": segs}, ensure_ascii=False, indent=1))
    for i, s in enumerate(segs):
        print(f"{i:2d} out {s['out_start']:7.2f}-{s['out_end']:7.2f}  src {s['start']:7.2f}  {s['label'][:60]}")
    print(f"total {off:.3f}s = {round(off * fps)} frames")
    rms_envelope(segs, edit / "rms_out.npy")


if __name__ == "__main__":
    main()
