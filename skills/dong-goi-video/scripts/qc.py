"""Self-eval of a packaged render. Run on the OUTPUT, never on the sources.

Checks:
  1. Stream lengths: video and audio durations match the expected total.
  2. Card motion: frame-to-frame diff inside the card box for the 12 frames after each overlay
     start. A ~0 diff between moving frames = a repeated frame (judder). Expect "smooth".
  3. Loudness: momentary LUFS at each SFX hit vs the speech p90. An effect louder than speech is a bug.
  4. Contact sheet of the given times (or one per overlay + start/end) → verify/qc_sheet.png. LOOK at it.

Usage: python qc.py package.json VIDEO.mp4 [--box 1180,100,680,600] [--times 2.6,13.3,...]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("video")
    ap.add_argument("--box", help="x,y,w,h of the card area (default: package.json safe_box)")
    ap.add_argument("--times")
    a = ap.parse_args()
    cfgp = Path(a.config).resolve(); here = cfgp.parent
    cfg = json.loads(cfgp.read_text())
    seg = json.loads((here / cfg.get("segments", "segments.json")).read_text())
    fps, total = seg["fps"], seg["total"]
    video = str(Path(a.video).resolve())

    # 1. durations
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", video],
                         capture_output=True, text=True).stdout.split()
    print("streams:", out, f"expected {total:.3f}s")

    # 2. card motion smoothness
    x, y, w, h = map(int, a.box.split(",")) if a.box else cfg.get("safe_box", [1180, 100, 680, 600])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"crop={w}:{h}:{x}:{y},scale={w // 4}:{h // 4},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h // 4, w // 4).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean((1, 2))
    for ov in cfg.get("overlays", []):
        f, t = ov[0], ov[1]
        if len(ov) > 2 and ov[2].get("full_frame"):
            print(f"card {Path(f).parent.name:16s} @{t:6.2f}  (full-frame, not measured in the card box — check frames by eye)")
            continue
        k = round(t * fps)
        win = d[k:k + 12]
        moving = win[1:9]   # frame 0 of an entrance barely moves (a fade-in starting) — not a repeat
        # a repeated frame is ~0 diff between moving neighbours; a slow settle (0.3) followed by
        # the next word popping in is legitimate motion, not judder
        stalls = int(((moving < 0.08) & (np.r_[moving[1:], 0] > 1.0)).sum())
        print(f"card {Path(f).parent.name:16s} @{t:6.2f}  {'smooth' if stalls == 0 else f'JUDDER x{stalls}'}  {np.round(win, 1)}")

    # 3. loudness at SFX hits
    mom = here / "_compose" / "qc_mom.txt"
    mom.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-af",
                    f"ebur128=metadata=1,ametadata=print:key=lavfi.r128.M:file={mom}", "-f", "null", "-"],
                   capture_output=True)
    txt = mom.read_text()
    ts = np.array([float(v) for v in re.findall(r"pts_time:([\d.]+)", txt)])
    ms = np.array([float(v) for v in re.findall(r"lavfi.r128.M=(-?[\d.inf]+)", txt)])
    sp = ms[ms > -70]
    p90 = np.percentile(sp, 90)
    print(f"momentary LUFS p50 {np.percentile(sp, 50):.1f}  p90 {p90:.1f}  max {ms.max():.1f} @ {ts[ms.argmax()]:.2f}")
    if cfg.get("sfx_cues"):
        for name, hit, gain in json.loads((here / cfg["sfx_cues"]).read_text()):
            win = (ts > hit - 0.05) & (ts < hit + 0.5)
            # momentary includes the voice under the effect; flag only clear outliers
            if win.any() and ms[win].max() > p90 + 2.0:
                print(f"  LOUD SFX {name} @{hit:.2f}: {ms[win].max():.1f} LUFS > speech p90 {p90:.1f} + 2")
    # 4. contact sheet
    times = [float(t) for t in a.times.split(",")] if a.times else \
        [0.5] + sorted({round(ov[1] + 2.0, 1) for ov in cfg.get("overlays", [])}) + [max(0, total - 0.4)]
    times = [min(max(0.0, t), total - 0.1) for t in times]   # a hook near the end + 2 s ran past the last frame
    vdir = here / "verify"; vdir.mkdir(exist_ok=True)
    tiles = []
    for i, t in enumerate(times):
        p = vdir / f"qc_{i:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-vf",
                        f"scale=640:-1,drawtext=text='{t:.2f}':x=8:y=8:fontsize=28:fontcolor=red:box=1:boxcolor=white", str(p)])
        if p.exists():
            tiles.append(p)
    cols = 4
    while len(tiles) % cols:
        tiles.append(tiles[-1])
    ins = sum((["-i", str(p)] for p in tiles), [])
    rows = [f"{''.join(f'[{r * cols + c}]' for c in range(cols))}hstack={cols}[r{r}]" for r in range(len(tiles) // cols)]
    graph = ";".join(rows) + (f";{''.join(f'[r{r}]' for r in range(len(rows)))}vstack={len(rows)}" if len(rows) > 1 else "")
    if len(rows) == 1:
        graph = graph.replace("[r0]", "")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, str(vdir / "qc_sheet.png")])
    print("contact sheet:", vdir / "qc_sheet.png")


if __name__ == "__main__":
    main()
