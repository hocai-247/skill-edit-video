"""Speech-to-text engines. Default: Zipformer-vi running on this Mac (free, offline).

Benchmark on uncut.mp4 (2026-10-11, PLAN.md): Zipformer-vi int8 (VietASR, Apache-2.0) transcribed the
9-minute clip in ~45 s, kept every disfluency the rules need ("vậy thứ vậy thứ", "ờ", "ờm") and returns
a time per word. Vbee stays available as an option (text only, one request at a time).

engine.transcribe(wav, offset) -> (text | None, words | None); words = [[word, t_abs], …].
"""

from __future__ import annotations

import hashlib
import tarfile
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

ZIPFORMER = "sherpa-onnx-zipformer-vi-int8-2025-04-20"
ZIPFORMER_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{ZIPFORMER}.tar.bz2"
ZIPFORMER_FILES = {   # sha256 of the files used, pinned from the release downloaded on 2026-10-11
    "encoder-epoch-12-avg-8.int8.onnx": "b3abdef7a660fea7faf5e076b3c7613b0fc98406707103784d018189bb522124",
    "decoder-epoch-12-avg-8.onnx": "d1d27cca84c824a8acf5ce6edf0f2c0880cfe295d2e69b95134de1707e1d9998",
    "joiner-epoch-12-avg-8.int8.onnx": "38ec49e1c18e4feb0cad4de13e25c83a866cf56f4a66f22e8ff579d591a69a46",
    "tokens.txt": "f536d03c2e95ebd2930cf0abec88e823bd17d3c1933da7ae6a82db3b80605e15",
}
# Zipformer emits a word ~0.15 s before it is heard (median over 234 words that follow a pause
# in uncut.mp4); word times are shifted by this much.
WORD_LAG = 0.15

# What the local engine hears for English tech words: measured on uncut.mp4 across five decoding
# settings (2026-10-12); with all of these, every setting gave the same rough cut. Prefilled in the
# alias box; Vietnamese words are deliberately left out ("lót", "sờ", "lo" are real words).
LOCAL_ALIASES = ("Claude: cloud, clot, clod, clos, clo, load, lott, clock, clop, clost, cload, clus\n"
                 "skill: seo, sko, sku, sky, es, se, sw")


class ModelError(RuntimeError):
    pass


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_ready() -> bool:
    d = MODELS / ZIPFORMER
    return all((d / f).exists() for f in ZIPFORMER_FILES)


def ensure_model(progress=lambda msg: None) -> Path:
    """Download the model once (~70 MB) and check every file against its pinned hash."""
    d = MODELS / ZIPFORMER
    if not model_ready():
        MODELS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=MODELS) as tmp:
            arc = Path(tmp) / "model.tar.bz2"
            with requests.get(ZIPFORMER_URL, stream=True, timeout=60) as r:
                r.raise_for_status()
                total, done, shown = int(r.headers.get("content-length", 0)), 0, -1
                with open(arc, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                        done += len(chunk)
                        pct = done * 100 // total if total else 0
                        if pct // 10 != shown:
                            shown = pct // 10
                            progress(f"Đang tải model nghe tiếng Việt (lần đầu, ~70 MB) {pct}%")
            with tarfile.open(arc) as t:
                members = [m for m in t.getmembers() if m.isfile() and Path(m.name).name in ZIPFORMER_FILES]
                for m in members:
                    m.name = Path(m.name).name          # flatten; never write outside tmp
                t.extractall(Path(tmp) / ZIPFORMER, members=members, filter="data")
            for name, sha in ZIPFORMER_FILES.items():
                got = _sha256(Path(tmp) / ZIPFORMER / name)
                if got != sha:
                    raise ModelError(f"Model tải về không khớp mã kiểm tra ({name}). Đã huỷ, không dùng file này.")
            d.parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / ZIPFORMER).rename(d)
    return d


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    return x, sr


def words_from_tokens(tokens: list[str], times: list[float], offset: float) -> list[list]:
    """BPE tokens → [[word, source time]]. A token that starts with a space starts a new word."""
    out: list[list] = []
    new_word = True
    for tok, t in zip(tokens, times):
        piece = tok.lower()
        if piece.startswith((" ", "▁")):
            new_word = True
        word = piece.strip(" ▁")
        if not word:            # a bare space token: the NEXT token starts a word ("có", " ", "ờ", "m")
            continue
        if new_word or not out:
            out.append([word, round(offset + t + WORD_LAG, 3)])
        else:
            out[-1][0] += word
        new_word = False
    return out


class ZipformerEngine:
    name = "zipformer"
    label = "máy này"
    _lock = threading.Lock()
    _rec = None

    def __init__(self, progress=lambda msg: None):
        with ZipformerEngine._lock:
            if ZipformerEngine._rec is None:
                import sherpa_onnx
                d = ensure_model(progress)
                f = lambda n: str(d / n)
                ZipformerEngine._rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=f("encoder-epoch-12-avg-8.int8.onnx"), decoder=f("decoder-epoch-12-avg-8.onnx"),
                    joiner=f("joiner-epoch-12-avg-8.int8.onnx"), tokens=f("tokens.txt"),
                    num_threads=8, decoding_method="modified_beam_search", max_active_paths=4)

    def transcribe(self, wav: Path, offset: float) -> tuple[str | None, list | None]:
        """offset = source time of the wav's first sample."""
        x, sr = read_wav(wav)
        return self.transcribe_samples(x, sr, offset)

    def transcribe_samples(self, x: np.ndarray, sr: int, offset: float) -> tuple[str | None, list | None]:
        with ZipformerEngine._lock:        # one recogniser, shared across jobs
            s = ZipformerEngine._rec.create_stream()
            s.accept_waveform(sr, x)
            ZipformerEngine._rec.decode_stream(s)
            r = s.result
        words = words_from_tokens(list(r.tokens), list(r.timestamps), offset)
        text = " ".join(w for w, _ in words) or None
        return text, (words or None)


class VbeeEngine:
    name = "vbee"
    label = "Vbee"

    def __init__(self, app_id: str, token: str):
        from .vbee import VbeeClient
        self.client = VbeeClient(app_id, token)

    def transcribe(self, wav: Path, offset: float) -> tuple[str | None, list | None]:
        return self.client.transcribe(wav), None
