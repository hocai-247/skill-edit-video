"""Burned-in caption track (ASS) + per-token timing, without word-level ASR timestamps.

Timing source, best first:
  --words words_asr.json (words_asr.py, whisper DTW): your corrected caption tokens are aligned to
     the ASR words (difflib on lower-cased text); matched tokens take the ASR onset, unmatched ones
     are interpolated between their matched neighbours. Accuracy ~0.1–0.2 s.
  fallback: each caption group's tokens are spread over that group's VOICED pieces (rms_out.npy > -38 dB,
gaps < 80 ms merged). Vietnamese syllables are near-isochronous, so drift stays ~0.1-0.2 s inside
a group and resets at every group edge. Use one group per EDL range / per segment (tightest), or
per transcript utterance when the cut has no EDL.

chunks.json:
  {"groups": [
     {"seg": 0, "chunks": ["CHÀO CÁC BẠN!", "ĐẦU TIÊN"]},           # seg = segment index
     {"start": 5.13, "end": 7.90, "chunks": ["*SKILL EDIT VIDEO*"]}  # or an explicit output span
   ],
   "weights": {"CHATGPT": 4, "VIDEO": 3}}                           # spoken syllables per token
  *word* = keyword (yellow). Write chunks UPPERCASE, 2–5 words, spelled correctly (fix ASR).

Usage:
  python captions.py --edit-dir DIR --chunks DIR/chunks.json [--words DIR/words_asr.json] [--stop-at 69.55]
Outputs: captions.ass, captions_timing.json, words.json (every token's estimated start).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np

YELLOW = r"{\c&H00D4FF&}"   # ASS colours are BGR: #FFD400
WHITE = r"{\c&HFFFFFF&}"
DEFAULT_WEIGHTS = {"CHATGPT": 4, "CLAUDE": 1, "CODE": 1, "CODEX": 2, "SKILL": 1, "EDIT": 2, "VIDEO": 3,
                   "AI": 2, "BUILD": 1, "PROMPT": 1, "OK": 2, "CLIP": 1, "IMAGE": 2, "USE": 1, "CASE": 1}
MIN_CUE = 0.45   # shorter cues flash; the script reports them so you can merge chunks


def tokens(c: str) -> list[str]:
    return re.sub(r"[*!?,.:;]", " ", c).split()


def voiced(db: np.ndarray, a: float, b: float) -> list[tuple[float, float]]:
    s, e = int(round(a * 100)), int(round(b * 100))
    v = db[s:e] > -38
    runs, i = [], 0
    while i < len(v):
        if v[i]:
            j = i
            while j < len(v) and v[j]:
                j += 1
            runs.append([i, j]); i = j
        else:
            i += 1
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < 8:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    pieces = [((s + x) / 100, (s + y) / 100) for x, y in merged if y - x >= 5]
    return pieces or [(a, b)]


def ass_time(t: float) -> str:
    cs = int(round(t * 100)); h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", required=True)
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--words", help="words_asr.json from words_asr.py (preferred timing)")
    ap.add_argument("--stop-at", type=float, help="drop cues from here on (e.g. under an end stinger)")
    ap.add_argument("--font", default="VU Cond Black")
    ap.add_argument("--size", type=int, default=88)
    ap.add_argument("--margin-v", type=int, default=64)
    a = ap.parse_args()
    edit = Path(a.edit_dir)
    db = np.load(edit / "rms_out.npy")
    seginfo = json.loads((edit / "segments.json").read_text())
    segs, total = seginfo["segments"], seginfo["total"]
    spec = json.loads(Path(a.chunks).read_text())
    weights = {**DEFAULT_WEIGHTS, **spec.get("weights", {})}
    w = lambda t: weights.get(t, 1.0)  # noqa: E731

    cues, words = [], []
    for g in spec["groups"]:
        if "seg" in g:
            ga, gb = segs[g["seg"]]["out_start"], segs[g["seg"]]["out_end"]
        else:
            ga, gb = g["start"], g["end"]
        pieces = voiced(db, ga, gb)
        span = sum(b - x for x, b in pieces)
        n = sum(w(t) for c in g["chunks"] for t in tokens(c))

        def at(u: float) -> float:
            target = span * u / n
            for x, b in pieces:
                if target <= (b - x) + 1e-9:
                    return x + target
                target -= b - x
            return pieces[-1][1]

        u = 0.0
        for c in g["chunks"]:
            cue = {"text": c, "group_end": gb, "toks": []}
            for t in tokens(c):
                words.append({"w": t, "t": round(at(u), 3), "end": round(at(u + w(t)), 3), "cue": len(cues)})
                cue["toks"].append(len(words) - 1)
                u += w(t)
            cues.append(cue)

    if a.words:
        norm = lambda s: re.sub(r"[^\w.]", "", unicodedata.normalize("NFC", s).lower())  # noqa: E731
        asr = json.loads(Path(a.words).read_text())
        sm = difflib.SequenceMatcher(None, [norm(x["w"]) for x in words], [norm(x["w"]) for x in asr], autojunk=False)
        anchor: dict[int, float] = {}
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                anchor[blk.a + k] = asr[blk.b + k]["t"]
        idx = sorted(anchor)
        print(f"ASR alignment: {len(anchor)}/{len(words)} caption tokens matched")
        for i in range(len(words)):
            if i in anchor:
                words[i]["t"] = anchor[i]
                continue
            lo = max((j for j in idx if j < i), default=None)
            hi = min((j for j in idx if j > i), default=None)
            if lo is not None and hi is not None:   # interpolate by position between matched neighbours
                words[i]["t"] = round(anchor[lo] + (anchor[hi] - anchor[lo]) * (i - lo) / (hi - lo), 3)
        for i in range(len(words) - 1):   # a token ends where the next one starts (same cue/group)
            words[i]["end"] = words[i + 1]["t"] if words[i + 1]["t"] - words[i]["t"] < 1.0 else words[i]["t"] + 0.35
        words[-1]["end"] = words[-1]["t"] + 0.35
    for c in cues:
        c["start"] = words[c["toks"][0]]["t"]
        c["end"] = words[c["toks"][-1]]["end"]
        del c["toks"]
    for x in words:
        x.pop("cue", None); x.pop("end", None)

    cues.sort(key=lambda c: c["start"])
    for x, y in zip(cues, cues[1:]):   # hold to the next cue across short gaps; never across a long pause
        x["end"] = y["start"] if y["start"] - x["end"] < 0.35 else min(x["end"] + 0.2, x["group_end"])
    cues[-1]["end"] = min(cues[-1]["end"] + 0.4, total)
    if a.stop_at is not None:
        cues = [c for c in cues if c["start"] < a.stop_at - 0.5]
        cues[-1]["end"] = min(cues[-1]["end"], a.stop_at)
    for c in cues:
        if c["end"] - c["start"] < MIN_CUE:
            print(f"SHORT {c['end'] - c['start']:.2f}s  {c['text']}  ← merge it with a neighbour")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{a.font},{a.size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1.5,0,1,7,3,2,120,120,{a.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in cues:
        body = re.sub(r"\*(.+?)\*", lambda m: YELLOW + m.group(1) + WHITE, c["text"])
        lines.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Cap,,0,0,0,,"
                     r"{\fscx112\fscy112\t(0,90,\fscx100\fscy100)}" + body)
    (edit / "captions.ass").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    (edit / "captions_timing.json").write_text(json.dumps(cues, ensure_ascii=False, indent=1), encoding="utf-8")
    (edit / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    for c in cues:
        print(f"{c['start']:6.2f}-{c['end']:6.2f}  {c['text']}")
    print("words:", " ".join(f"{x['w']}@{x['t']:.2f}" for x in words))


if __name__ == "__main__":
    main()
