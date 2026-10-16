"""Synthesize the SFX library into OUT_DIR (usage: make_sfx.py OUT_DIR). The few sound effects the edit uses (48 kHz stereo WAV, peak -3 dBFS).

whoosh.wav       0.50 s  band-passed noise sweep 350→2800→600 Hz (big move, scissors sweep)
swoosh_soft.wav  0.35 s  short airy swoosh (a card settling)
pop.wav          0.12 s  pitch-dropping sine blip (element / pill appears)
tick.wav         0.03 s  tiny tick (counter steps, stars filling)
bloop.wav        0.18 s  soft rising bubble (comment bubbles, hearts)
ding.wav         0.90 s  bell partials (✓, a number landing)
sparkle.wav      0.90 s  scattered high pings (bursts, gift opening)
buzz.wav         0.32 s  detuned low square (✕)
thud.wav         0.40 s  pitch-dropping sub + transient (stamp / badge)
riser.wav        0.80 s  noise riser, peak at the very end (into the stinger)
impact.wav       1.20 s  sub drop + crack + tail (stinger slam)

Prints each file's attack (first sample within 30 dB of the peak) and the
time of its peak, so effects can be placed to hit on the visible frame.
"""

from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt, stft, istft
import wave

SR = 48000
import sys
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)


def write(name, x):
    x = np.asarray(x, dtype=np.float64)
    x = x / (np.max(np.abs(x)) + 1e-12) * 10 ** (-3 / 20)
    st = np.stack([x, x], axis=1)
    pcm = (st * 32767).astype(np.int16)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    env = np.abs(x)
    peak_i = int(np.argmax(env))
    attack_i = int(np.argmax(env >= env.max() * 10 ** (-30 / 20)))
    print(f"{name:11s} dur={len(x)/SR:.2f}s attack={attack_i/SR:.3f}s peak_at={peak_i/SR:.3f}s")


def t_axis(d):
    return np.arange(int(SR * d)) / SR


def whoosh():
    d = 0.50
    n = rng.standard_normal(int(SR * d))
    f, tt, Z = stft(n, SR, nperseg=1024)
    # center frequency path and loudness envelope over the frames
    u = tt / d
    fc = np.where(u < 0.56, 350 * (2800 / 350) ** (u / 0.56), 2800 * (600 / 2800) ** ((u - 0.56) / 0.44))
    bw = 0.55 * fc + 150
    mask = np.exp(-0.5 * ((f[:, None] - fc[None, :]) / bw[None, :]) ** 2)
    _, y = istft(Z * mask, SR, nperseg=1024)
    y = y[: int(SR * d)]
    t = t_axis(d)
    env = np.where(t < 0.28, (t / 0.28) ** 2.2, np.exp(-(t - 0.28) / 0.07))
    return y * env


def pop():
    t = t_axis(0.12)
    f = 300 + 700 * np.exp(-t / 0.018)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.035) * np.minimum(1, t / 0.002)


def ding():
    t = t_axis(0.90)
    y = (np.sin(2 * np.pi * 1318.5 * t) + 0.55 * np.sin(2 * np.pi * 2637 * t + 0.3)
         + 0.25 * np.sin(2 * np.pi * 3955.5 * t + 1.1))
    return y * np.exp(-t / 0.28) * np.minimum(1, t / 0.003)


def buzz():
    t = t_axis(0.32)
    y = np.sign(np.sin(2 * np.pi * 140 * t)) + np.sign(np.sin(2 * np.pi * 147 * t))
    y = sosfilt(butter(4, 1400, "low", fs=SR, output="sos"), y)
    env = np.minimum(1, t / 0.01) * np.where(t > 0.24, np.exp(-(t - 0.24) / 0.03), 1.0)
    return y * env


def thud():
    t = t_axis(0.40)
    f = 55 + 60 * np.exp(-t / 0.05)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
    click = sosfilt(butter(2, 2500, "low", fs=SR, output="sos"), rng.standard_normal(len(t))) * np.exp(-t / 0.012)
    return (sub + 0.35 * click) * np.minimum(1, t / 0.001)




def swoosh_soft():
    """Short airy swoosh for card entrances (0.35 s, peak ~0.16 s)."""
    d = 0.35
    n = rng.standard_normal(int(SR * d))
    f, tt, Z = stft(n, SR, nperseg=512)
    u = tt / d
    fc = 900 * (4200 / 900) ** np.clip(u / 0.5, 0, 1) * np.where(u > 0.5, (0.6) ** ((u - 0.5) / 0.5), 1)
    mask = np.exp(-0.5 * ((f[:, None] - fc[None, :]) / (0.6 * fc[None, :] + 200)) ** 2)
    _, y = istft(Z * mask, SR, nperseg=512)
    y = y[: int(SR * d)]
    t = t_axis(d)
    env = np.where(t < 0.16, (t / 0.16) ** 1.6, np.exp(-(t - 0.16) / 0.06))
    return y * env


def tick():
    """Tiny counter tick (25 ms)."""
    t = t_axis(0.025)
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t / 0.004) * np.minimum(1, t / 0.0005)


def sparkle():
    """Glittery shimmer: 9 short high bell pings scattered over 0.8 s."""
    d = 0.9
    t = t_axis(d)
    y = np.zeros_like(t)
    freqs = [2637, 3136, 3520, 2794, 4186, 3322, 3951, 2960, 4699]
    for k, fr in enumerate(freqs):
        st = 0.07 * k + 0.01 * rng.random()
        tt = np.clip(t - st, 0, None)
        on = t >= st
        y += on * np.sin(2 * np.pi * fr * tt) * np.exp(-tt / 0.09) * (0.9 - 0.06 * k)
    return y * np.minimum(1, t / 0.002)


def bloop():
    """Soft rising bubble for hearts / bubbles (0.18 s)."""
    t = t_axis(0.18)
    f = 380 + 520 * (t / 0.18) ** 0.7
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.18) ** 1.5


def riser():
    """0.8 s noise riser into the stinger; peak at the very end."""
    d = 0.8
    n = rng.standard_normal(int(SR * d))
    f, tt, Z = stft(n, SR, nperseg=1024)
    fc = 300 * (5000 / 300) ** (tt / d)
    mask = np.exp(-0.5 * ((f[:, None] - fc[None, :]) / (0.5 * fc[None, :] + 100)) ** 2)
    _, y = istft(Z * mask, SR, nperseg=1024)
    y = y[: int(SR * d)]
    t = t_axis(d)
    return y * (t / d) ** 2.5


def impact():
    """Cinematic hit for the stinger slam: sub drop + noise crack + tail (1.2 s)."""
    t = t_axis(1.2)
    f = 45 + 90 * np.exp(-t / 0.06)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
    crack = sosfilt(butter(2, [800, 6000], "band", fs=SR, output="sos"), rng.standard_normal(len(t))) * np.exp(-t / 0.05)
    tail = sosfilt(butter(2, 1500, "low", fs=SR, output="sos"), rng.standard_normal(len(t))) * np.exp(-t / 0.4) * 0.25
    return (sub + 0.5 * crack + tail) * np.minimum(1, t / 0.001)


if __name__ == "__main__":
    write("whoosh.wav", whoosh())
    write("pop.wav", pop())
    write("ding.wav", ding())
    write("buzz.wav", buzz())
    write("thud.wav", thud())
    write("swoosh_soft.wav", swoosh_soft())
    write("tick.wav", tick())
    write("sparkle.wav", sparkle())
    write("bloop.wav", bloop())
    write("riser.wav", riser())
    write("impact.wav", impact())
