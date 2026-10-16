"""Find where cards can live: draw a candidate box on frames sampled across the cut, and save one
clean reference frame (bg_ref.png) for the card agents' check frames.

Look at verify/safe_box.png: the box must stay clear of the face, hair and raised hands in EVERY
tile (punch-in zooms push the person outward, so leave margin). Re-run with another --box if not.

Usage: python safe_box.py --edit-dir DIR --video CUT_OR_PREVIEW.mp4 [--box 1180,100,680,600] [--n 14]
"""
import argparse, subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--edit-dir", required=True)
ap.add_argument("--video", required=True)
ap.add_argument("--box", default="1180,100,680,600")
ap.add_argument("--n", type=int, default=14)
ap.add_argument("--ref-time", type=float, help="time for bg_ref.png: pick a WIDE, typical take (default: mid-clip)")
a = ap.parse_args()
x, y, w, h = map(int, a.box.split(","))
vdir = Path(a.edit_dir) / "verify"; vdir.mkdir(parents=True, exist_ok=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.video],
                           capture_output=True, text=True).stdout)
times = [dur * (i + 0.5) / a.n for i in range(a.n)]
s = 1 / 3
tiles = []
for i, t in enumerate(times):
    p = vdir / f"sb_{i:02d}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", a.video, "-frames:v", "1", "-vf",
                    f"scale=640:-1,drawbox=x={x*s:.0f}:y={y*s:.0f}:w={w*s:.0f}:h={h*s:.0f}:color=yellow@0.9:t=2", str(p)])
    tiles.append(p)
cols = 7
while len(tiles) % cols:
    tiles.append(tiles[-1])
ins = sum((["-i", str(p)] for p in tiles), [])
rows = [f"{''.join(f'[{r*cols+c}]' for c in range(cols))}hstack={cols}[r{r}]" for r in range(len(tiles) // cols)]
g = ";".join(rows) + f";{''.join(f'[r{r}]' for r in range(len(rows)))}vstack={len(rows)}" if len(rows) > 1 else rows[0].replace("[r0]", "")
subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", g, str(vdir / "safe_box.png")])
mid = a.ref_time if a.ref_time is not None else dur / 2
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", a.video, "-frames:v", "1", str(vdir / "bg_ref.png")])
print("look at:", vdir / "safe_box.png", "| card agents composite on:", vdir / "bg_ref.png")
