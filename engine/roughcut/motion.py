"""How much the screen changes over time (tutorial mode).

Same measure and thresholds as the user's cat-tho-huong-dan-vbee skill (formerly tutorial-roughcut), measured there on a 61-min Codex
recording: the fraction of pixels that change by more than 12 gray levels between frames 0.5 s apart
(192×108, webcam corner masked). The cursor and a webcam face reach about 1.2 %, so a wait "really
changes" above 2.5 % for at least 0.5 s, or when its last frame differs from its first by more than
2.5 % (typing a prompt changes little per half second but a lot over the wait).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .ff import FFMPEG, run_bytes

W, H, STEP = 192, 108, 0.5
CHANGE = 0.025             # fraction of pixels for "the screen changed"
ACTIVE = 0.5               # seconds of change for "the wait was busy"
MASK = (0.0, 0.86, 0.12, 1.0)   # x0, y0, x1, y1 as fractions: webcam bubble, bottom-left


def measure(src: Path, mask=MASK) -> tuple[np.ndarray, np.ndarray]:
    """(motion, thumbs): motion[k] = changed fraction between frames k and k+1 (0.5 s apart);
    thumbs[k] = the masked 192×108 frame at k * 0.5 s."""
    raw = run_bytes([FFMPEG, "-v", "error", "-i", str(src), "-an", "-vf",
                     f"fps={1 / STEP:g},scale={W}:{H},format=gray", "-f", "rawvideo", "-"])
    f = np.frombuffer(raw, np.uint8).reshape(-1, H, W).copy()
    keep = np.ones((H, W), bool)
    if mask:
        x0, y0, x1, y1 = mask
        keep[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)] = False
    f[:, ~keep] = 0
    motion = (np.abs(np.diff(f.astype(np.int16), axis=0)) > 12)[:, keep].mean(1).astype(np.float32)
    return motion, f


def busy_seconds(motion: np.ndarray, thumbs: np.ndarray, a: float, b: float) -> float:
    """Seconds of real screen change inside (a, b)."""
    s = motion[int(a / STEP):int(b / STEP)]
    sec = float((s > CHANGE).sum() * STEP)
    if sec < ACTIVE and thumbs is not None and len(thumbs):
        i0, i1 = int(a / STEP) + 1, min(int(b / STEP), len(thumbs) - 1)
        if i1 > i0 and (np.abs(thumbs[i1].astype(np.int16) - thumbs[i0]) > 12).mean() > CHANGE:
            return ACTIVE
    return sec


def save(path: Path, motion: np.ndarray, thumbs: np.ndarray) -> None:
    np.savez_compressed(path, motion=motion, thumbs=thumbs)


def load(path: Path) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    if not path.exists():
        return None, None
    z = np.load(path)
    return z["motion"], z["thumbs"]


FF_MIN = 1.5               # a gap at least this long between kept ranges may be fast-forwarded…
FF_DIV, FF_LO, FF_HI = 10.0, 1.0, 4.0   # …into clamp(gap / 10, 1, 4) seconds of output


def busy_span(motion: np.ndarray, a: float, b: float, margin: float = 0.5) -> tuple[float, float]:
    """The part of the wait (a, b) where the screen moves: from the first to the last changing step,
    plus a margin. A still screen before or after it is cut, not fast-forwarded (it would read as a
    frozen frame). With no single changing step (typing, caught by the first/last frame test), the
    whole wait."""
    i0, i1 = int(a / STEP), int(b / STEP)
    idx = np.nonzero(motion[i0:i1] > CHANGE)[0]
    if not len(idx):
        return a, b
    return (float(max(a, (i0 + idx[0]) * STEP - margin)),
            float(min(b, (i0 + idx[-1] + 1) * STEP + margin)))


def plan(rngs: list[tuple[float, float]], motion, thumbs) -> list[tuple[float, float, float | None]]:
    """Kept ranges + muted fast-forwards: (start, end, None) plays as is, (start, end, out) plays the
    source span start..end in `out` seconds. A gap becomes a fast-forward when it is ≥ FF_MIN long
    and the screen really changed in it; only its moving part is kept. Any other gap is cut."""
    out: list[tuple[float, float, float | None]] = []
    for k, (a, b) in enumerate(rngs):
        if k and motion is not None:
            ga, gb = rngs[k - 1][1], a
            if gb - ga >= FF_MIN and busy_seconds(motion, thumbs, ga, gb) >= ACTIVE:
                fa, fb = busy_span(motion, ga, gb)
                if fb - fa >= FF_MIN:
                    out.append((fa, fb, round(min(FF_HI, max(FF_LO, (fb - fa) / FF_DIV)), 3)))
        out.append((a, b, None))
    return out
