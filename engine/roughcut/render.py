"""Render kept ranges into a finished rough cut, frame- and sample-exact.

Picture: each range is extracted with an exact frame count, then joined with the concat
FILTER and retimed to frame N = N/fps. Audio: each range is decoded straight from the
source, trimmed/padded to exactly its frames' duration, given 30 ms fades, and joined in
numpy. Master: gentle compressor → static gain to -14 LUFS → peak limiter at -2.5 dBFS (sample peak; AAC adds up to ~0.6 dB, measured -1.4 dBTP with -2).

Why not concat-demuxer + loudnorm (video-use's render.py): measured on the reference clip,
the concatenated AAC decodes to ~21 ms extra per segment (audio drifts +0.11 s over 7 cuts)
and loudnorm silently goes dynamic when the speech peak-to-loudness ratio is high.
"""

from __future__ import annotations

import math
import wave
from fractions import Fraction
from pathlib import Path
from typing import Callable

import numpy as np

from .ff import FFMPEG, MediaInfo, run, run_bytes

SR = 48000
FADE = 0.03
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _frames(a: float, b: float, fps: Fraction) -> int:
    return max(1, round((b - a) * fps))


def _write_wav(path: Path, pcm: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.astype(np.int16).tobytes())


def _audio(src: Path, a: float, n_samples: int) -> np.ndarray:
    raw = run_bytes([FFMPEG, "-v", "error", "-ss", f"{a:.4f}", "-i", str(src), "-t", f"{n_samples / SR + 0.1:.4f}",
                     "-vn", "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"])
    pcm = np.frombuffer(raw, np.int16).reshape(-1, 2).astype(np.float32)
    pcm = pcm[:n_samples] if len(pcm) >= n_samples else np.vstack([pcm, np.zeros((n_samples - len(pcm), 2), np.float32)])
    f = min(int(FADE * SR), n_samples // 2)
    ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
    pcm[:f] *= ramp
    pcm[n_samples - f:] *= ramp[::-1]
    return pcm


def render(src: Path, info: MediaInfo, rngs: list, out: Path, work: Path,
           progress: Callable[[str, float], None] = lambda s, p: None) -> dict:
    """rngs: (start, end) plays as is; (start, end, out_seconds) is a muted fast-forward of that span
    (tutorial mode); (start, end, None) is the same as (start, end)."""
    work.mkdir(parents=True, exist_ok=True)
    fps = info.fps
    vf = (TONEMAP + ",") if info.hdr else ""
    clips, pcm_parts, cum, ff_frames = [], [], 0, 0
    for k, r in enumerate(rngs):
        a, b = r[0], r[1]
        ff = r[2] if len(r) > 2 else None
        # snap the cut to the frame grid so the first video frame and the first audio
        # sample start at the same instant (otherwise audio can lead by up to 1 frame)
        a = float(round(Fraction(a) * fps) / fps)
        clip = work / f"seg_{k:03d}.mp4"
        if ff:
            # fast-forward: speed the span up so it lasts exactly n frames, resampled to the output fps
            n = max(1, round(ff * fps))
            speed = (b - a) / (n / float(fps))
            run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.4f}", "-t", f"{b - a + 0.5:.4f}", "-i", str(src), "-an",
                 "-vf", f"{vf}setpts=(PTS-STARTPTS)/{speed:.6f},fps={fps},format=yuv420p", "-frames:v", str(n),
                 "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(clip)])
            ff_frames += n
        else:
            n = _frames(a, b, fps)
            run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.4f}", "-i", str(src), "-frames:v", str(n), "-an",
                 "-vf", f"{vf}format=yuv420p", "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                 str(clip)])
        # sample range that matches frames [cum, cum+n) exactly, even for 29.97 fps
        s0, s1 = round(cum * SR / fps), round((cum + n) * SR / fps)
        pcm_parts.append(np.zeros((s1 - s0, 2), np.float32) if ff else _audio(src, a, s1 - s0))
        clips.append(clip)
        cum += n
        progress(f"Cắt đoạn {k + 1}/{len(rngs)}", (k + 1) / len(rngs) * 0.6)

    # picture: concat filter, frame-exact timestamps
    progress("Ghép hình", 0.65)
    video = work / "video.mp4"
    ins = sum((["-i", str(c)] for c in clips), [])
    graph = "".join(f"[{i}:v]" for i in range(len(clips))) + \
            f"concat=n={len(clips)}:v=1:a=0,setpts=N/({fps.numerator}/{fps.denominator}*TB)[v]"
    run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", graph, "-map", "[v]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-r", str(fps), "-frames:v", str(cum), str(video)])

    # audio: join, compress, measure, gain, limit
    progress("Xử lý âm thanh", 0.85)
    raw = work / "speech_raw.wav"
    _write_wav(raw, np.clip(np.vstack(pcm_parts), -32768, 32767))
    comp = work / "speech_comp.wav"
    run([FFMPEG, "-y", "-v", "error", "-i", str(raw),
         "-af", "acompressor=threshold=-20dB:ratio=3:attack=4:release=90:knee=4", "-c:a", "pcm_s24le", str(comp)])
    err = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(comp), "-af", "ebur128", "-f", "null", "-"])
    tail = err[err.rfind("Summary"):]
    mix_i = float(tail.split(" I:")[1].split("LUFS")[0])
    gain = 0.0 if math.isinf(mix_i) or mix_i < -70 else -14.0 - mix_i + 0.3
    master = work / "master.wav"
    run([FFMPEG, "-y", "-v", "error", "-i", str(comp),
         "-af", f"volume={gain:.2f}dB,alimiter=limit=0.75:attack=1:release=50:level=0", "-c:a", "pcm_s24le", str(master)])

    progress("Xuất file", 0.95)
    run([FFMPEG, "-y", "-v", "error", "-i", str(video), "-i", str(master), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", str(out)])
    progress("Xong", 1.0)
    return {"frames": cum, "duration": cum / float(fps), "gain_db": round(gain, 2), "input_lufs": mix_i,
            "ff_seconds": round(ff_frames / float(fps), 2)}
