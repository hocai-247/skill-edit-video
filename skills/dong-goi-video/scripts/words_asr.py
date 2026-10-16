"""Word onsets on the OUTPUT timeline with whisper.cpp + DTW token timestamps.

Card landings and SFX must hit the spoken word; utterance-level ASR (e.g. Vbee) is not enough.
Plain whisper word times ran 0.3–0.9 s early in a test; DTW (`-dtw <model> -nfa`) matched the
speech onsets to +0.07–0.2 s. Without `-nfa`, DTW silently returns -1 for every token.
Onset = t_dtw − 0.10 s (measured offset).

The cut audio is rebuilt from segments.json exactly as compose.py does, so times line up.
Text from whisper may be misspelled; only its TIMING is used (captions.py aligns your corrected
caption text to these words).

Usage: python words_asr.py --edit-dir E [--lang vi] [--model PATH]   (default: first of MODEL_PATHS that exists)
Writes E/words_asr.json: [{"w": "chào", "t": 0.38}, ...]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


MODEL_PATHS = [Path.home() / "skill-edit-video/engine/models/whisper/ggml-large-v3-turbo.bin",   # install.sh
               Path.home() / "Developer/whisper-models/ggml-large-v3-turbo.bin"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", required=True)
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--model", default=str(next((p for p in MODEL_PATHS if p.exists()), MODEL_PATHS[0])))
    ap.add_argument("--dtw", default="large.v3.turbo", help="DTW preset matching the model")
    ap.add_argument("--offset", type=float, default=-0.10)
    a = ap.parse_args()
    if not shutil.which("whisper-cli") or not Path(a.model).exists():
        raise SystemExit("whisper-cli or the model is missing (brew install whisper-cpp; download ggml-large-v3-turbo.bin). "
                         "Fall back to captions.py interpolation (±0.2–0.7 s).")
    edit = Path(a.edit_dir).resolve()
    seg = json.loads((edit / "segments.json").read_text())
    asr = edit / "asr"; asr.mkdir(exist_ok=True)
    srcs = sorted({s["src"] for s in seg["segments"]})
    ins = sum((["-i", s] for s in srcs), [])
    fc, cat = [], ""
    for i, s in enumerate(seg["segments"]):
        k = srcs.index(s["src"])
        fc.append(f"[{k}:a]atrim=start={s['start']:.6f}:end={s['end']:.6f},asetpts=PTS-STARTPTS[a{i}]")
        cat += f"[a{i}]"
    fc.append(f"{cat}concat=n={len(seg['segments'])}:v=0:a=1,aresample=16000,aformat=channel_layouts=mono[o]")
    wav = asr / "cut16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[o]",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    subprocess.run(["whisper-cli", "-m", a.model, "-l", a.lang, "-f", str(wav), "-ojf", "-of", str(asr / "whisper"),
                    "-dtw", a.dtw, "-nfa", "-np"], check=True, capture_output=True)
    data = json.loads((asr / "whisper.json").read_text())
    words = []
    for segm in data["transcription"]:
        for tok in segm["tokens"]:
            text = tok["text"]
            if text.startswith("[_") or tok.get("t_dtw", -1) < 0:
                continue
            if text.startswith(" ") or not words:
                words.append({"w": text.strip(), "t": round(max(0.0, tok["t_dtw"] / 100 + a.offset), 3)})
            else:
                words[-1]["w"] += text          # continuation token of the same word
    words = [w for w in words if w["w"]]
    (edit / "words_asr.json").write_text(json.dumps(words, ensure_ascii=False))
    print(f"{len(words)} words →", edit / "words_asr.json")
    print(" ".join(f"{w['w']}@{w['t']:.2f}" for w in words))


if __name__ == "__main__":
    main()
