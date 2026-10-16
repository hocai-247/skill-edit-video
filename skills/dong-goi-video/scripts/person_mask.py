"""Person matte video for "text behind the speaker" (Apple Vision via personmask/personmask.swift).

Run it on the FRAMED footage that compose will show (zoom + grade, no overlays): compose.py
--base writes that file. Output: a gray mask video (255 = person) with the same frame count,
scaled to 1920x1080, lightly smoothed in time (Vision masks shimmer at hair edges).

Usage: python person_mask.py base.mp4 mask.mp4 [accurate|balanced|fast]
"""
import subprocess, sys, threading, time
from pathlib import Path
here = Path(__file__).resolve().parent
binary = here / "personmask" / "personmask"
if not binary.exists():
    subprocess.run(["swiftc", "-O", str(here / "personmask" / "personmask.swift"), "-o", str(binary)], check=True)
src, dst = sys.argv[1], sys.argv[2]
quality = sys.argv[3] if len(sys.argv) > 3 else "accurate"
p = subprocess.Popen([str(binary), src, quality], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
line = p.stderr.readline().decode().strip()
assert line.startswith("size "), f"personmask said: {line!r}"
w, h = map(int, line.split()[1].split("x"))
ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", "30",
                       "-i", "-", "-vf", "scale=1920:1080:flags=bicubic,tmix=frames=3:weights='1 2 1',format=gray",
                       "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-pix_fmt", "yuv420p", dst], stdin=subprocess.PIPE)
err = []
threading.Thread(target=lambda: err.extend(p.stderr.read().decode().splitlines()), daemon=True).start()
t0, n, size = time.time(), 0, w * h
while True:
    buf = p.stdout.read(size)
    if not buf or len(buf) < size:
        break
    ff.stdin.write(buf); n += 1
ff.stdin.close(); ff.wait(); p.wait()
print(f"mask {w}x{h} → 1920x1080, {n} frames in {time.time() - t0:.0f}s → {dst}", *[e for e in err if e.startswith("warning")][:3], sep="\n")
