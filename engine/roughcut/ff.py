"""ffmpeg / ffprobe helpers. Prefers the keg-only Homebrew ffmpeg-full build."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

_CANDIDATES = ["/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"]


def _find(tool: str) -> str:
    for d in _CANDIDATES:
        p = Path(d) / tool
        if p.exists():
            return str(p)
    found = shutil.which(tool)
    if not found:
        raise RuntimeError(f"{tool} not found. Install it with: brew install ffmpeg-full")
    return found


FFMPEG = _find("ffmpeg")
FFPROBE = _find("ffprobe")

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


class FFError(RuntimeError):
    pass


def run(args: list[str]) -> str:
    """Run ffmpeg/ffprobe; return stderr (where ffmpeg prints analysis). Raise on failure."""
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise FFError(f"{Path(args[0]).name} failed: {p.stderr[-1500:]}")
    return p.stderr


def run_bytes(args: list[str]) -> bytes:
    p = subprocess.run(args, capture_output=True)
    if p.returncode != 0:
        raise FFError(f"{Path(args[0]).name} failed: {p.stderr.decode(errors='replace')[-1500:]}")
    return p.stdout


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: Fraction
    has_audio: bool
    hdr: bool


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate,color_transfer",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise FFError(f"cannot read {path.name}: {out.stderr[-500:]}")
    data = json.loads(out.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFError(f"{path.name} has no video stream")
    fps = None
    for key in ("avg_frame_rate", "r_frame_rate"):
        v = video.get(key)
        if v and v != "0/0":
            fps = Fraction(v)
            break
    return MediaInfo(
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=(fps or Fraction(30)).limit_denominator(1001),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        hdr=video.get("color_transfer") in HDR_TRANSFERS,
    )
