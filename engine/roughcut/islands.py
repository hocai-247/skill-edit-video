"""Speech islands (between silences) and the finer pauses inside them."""

from __future__ import annotations

import re
from pathlib import Path

from .ff import FFMPEG, run

# Coarse pass: what counts as a separate utterance (one Vbee call each).
ISLAND_NOISE_DB, ISLAND_MIN_SILENCE = -40, 0.25
# Fine pass: short pauses inside an utterance = legal internal cut points.
PAUSE_NOISE_DB, PAUSE_MIN_SILENCE = -38, 0.06
MIN_ISLAND = 0.08
TARGET_MEDIAN_ISLAND = 1.2      # seconds; shorter islands = too many slow Vbee calls
MAX_ISLAND_MIN_SILENCE = 0.5


def silences(path: Path, noise_db: float, min_silence: float, duration: float) -> list[tuple[float, float]]:
    err = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-vn",
               "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"])
    out, start = [], None
    for kind, t in re.findall(r"silence_(start|end): (-?[\d.]+)", err):
        t = max(0.0, float(t))
        if kind == "start":
            start = t
        elif start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, duration))
    return merge_close(out, 0.05)


def merge_close(spans: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    """silencedetect often splits one pause into touching pieces; join them."""
    merged: list[list[float]] = []
    for a, b in sorted(spans):
        if merged and a - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def complement(sil: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    spans, prev = [], 0.0
    for a, b in sil:
        if a - prev >= MIN_ISLAND:
            spans.append((prev, a))
        prev = b
    if duration - prev >= MIN_ISLAND:
        spans.append((prev, duration))
    return spans


def noise_peak_db(path: Path) -> float:
    """20th-percentile peak of 50 ms blocks ≈ the loudest the room gets between words."""
    import numpy as np
    from .ff import run_bytes
    raw = run_bytes([FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    x = np.abs(np.frombuffer(raw, np.int16).astype(np.float32)) / 32768
    n = len(x) // 800
    if n == 0:
        return -90.0
    return float(np.percentile(20 * np.log10(x[:n * 800].reshape(n, 800).max(1) + 1e-9), 20))


def detect(path: Path, duration: float) -> tuple[list[tuple[float, float]], list[tuple[float, float]], dict]:
    """Return (islands, fine_pauses, settings), all times in absolute seconds.

    Thresholds adapt to the room: silencedetect compares sample PEAKS, so a noisy room
    (uncut.mp4: noise peaks ~-37 dB) never drops below a fixed -40 dB and the whole clip
    becomes one island. Floor at -40 dB keeps quiet recordings exactly as before.
    Islands are what Vbee transcribes one by one (~25 s each): if a speaker breathes
    between every few words, the minimum pause grows until islands are sentence-sized.
    """
    import statistics
    noise = max(ISLAND_NOISE_DB, round(noise_peak_db(path) + 3, 1))
    min_sil = ISLAND_MIN_SILENCE
    while True:
        islands = complement(silences(path, noise, min_sil, duration), duration)
        spoken = [b - a for a, b in islands if b - a >= 0.3]
        if min_sil >= MAX_ISLAND_MIN_SILENCE or not spoken or statistics.median(spoken) >= TARGET_MEDIAN_ISLAND:
            break
        min_sil = round(min_sil + 0.125, 3)
    pauses = silences(path, noise + (PAUSE_NOISE_DB - ISLAND_NOISE_DB), PAUSE_MIN_SILENCE, duration)
    return islands, pauses, {"noise_db": noise, "min_silence": min_sil}
