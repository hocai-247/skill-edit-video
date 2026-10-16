"""Job orchestration: analyze (islands → Vbee → rules) and export (render). No Flask here."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import decide as rules
from . import ff, islands, motion, render, stt
from .vbee import TextCache, VbeeAuthError

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "jobs"
CACHE = TextCache(ROOT / "cache")
SECONDS_PER_CALL = 25   # measured average, for the ETA only


class Job:
    def __init__(self, jid: str):
        self.id = jid
        self.dir = JOBS / jid
        self.lock = threading.Lock()

    # --- persisted state -------------------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def state(self) -> dict:
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {}

    def update(self, **kw) -> None:
        with self.lock:
            s = self.state()
            s.update(kw, updated=time.time())
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1))
            tmp.replace(self.state_path)

    @property
    def source(self) -> Path:
        return next(self.dir.glob("source.*"))

    @classmethod
    def create(cls, upload_name: str, save) -> "Job":
        job = cls(time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
        job.dir.mkdir(parents=True)
        ext = Path(upload_name).suffix.lower() or ".mp4"
        save(job.dir / f"source{ext}")
        job.update(id=job.id, name=upload_name, stage="queued", message="Đang chờ", progress=0.0)
        return job


class _Speech:
    """Transcribes source spans with one engine and the shared on-disk cache.

    Vbee entries keep their old cache keys ("<start>-<end>" → text); local entries are
    "zipformer:<start>-<end>" → {"text", "words"}. The local engine decodes the whole
    soundtrack once and slices it (seeking into the source for every island took ~2× longer).
    """

    def __init__(self, src: Path, engine, tmp: Path):
        self.src, self.engine, self.tmp = src, engine, tmp
        self.key = TextCache.file_key(src)
        self.cached = CACHE.load(self.key)
        self.prefix = "" if engine.name == "vbee" else f"{engine.name}:"
        self.calls = 0
        self._audio = None

    def _k(self, a: float, b: float) -> str:
        return f"{self.prefix}{a:.3f}-{b:.3f}"

    def known(self, a: float, b: float) -> bool:
        return self._k(a, b) in self.cached

    def heard(self, a: float, b: float) -> tuple[str | None, list | None]:
        """(text, words) of a source span; words only from engines that time them."""
        k = self._k(a, b)
        if k not in self.cached:
            s = max(0.0, a - 0.12)
            if self.engine.name == "vbee":
                wav = self.tmp / f"span_{self.calls:04d}.wav"
                ff.run([ff.FFMPEG, "-y", "-v", "error", "-ss", f"{s:.3f}", "-i", str(self.src),
                        "-t", f"{b + 0.12 - s:.3f}", "-vn", "-ac", "1", "-ar", "16000",   # async: no 10 s cap
                        "-c:a", "pcm_s16le", str(wav)])
                value = self.engine.transcribe(wav, s)[0]
            else:
                x, sr = self._soundtrack()
                text, words = self.engine.transcribe_samples(x[int(s * sr): int((b + 0.12) * sr)], sr, s)
                value = {"text": text, "words": words}
            CACHE.put_key(self.key, k, value)
            self.cached[k] = value
            self.calls += 1
        v = self.cached[k]
        return (v.get("text"), v.get("words")) if isinstance(v, dict) else (v, None)

    def text(self, a: float, b: float) -> str | None:
        return self.heard(a, b)[0]

    def _soundtrack(self):
        if self._audio is None:
            wav = self.tmp / "soundtrack.wav"
            ff.run([ff.FFMPEG, "-y", "-v", "error", "-i", str(self.src), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav)])
            self._audio = stt.read_wav(wav)
        return self._audio


def make_engine(name: str, app_id: str = "", token: str = "", progress=lambda m: None):
    if name == "vbee":
        return stt.VbeeEngine(app_id, token)
    return stt.ZipformerEngine(progress)


PROBE_ROUNDS = 2   # a piece removed in round 1 can expose a second one ("vậy thứ… vậy thứ… vậy thứ họ")


def _decide_and_probe(job: Job, speech: _Speech, isl_objs, pauses, aliases, mode: str = "intro") -> tuple[list, list]:
    decisions = rules.decide(isl_objs, pauses, aliases, mode=mode)
    probes: list[dict] = []
    # Probe only for Vbee: the local engine already hears "ờ/à" and times every word.
    for _ in range(PROBE_ROUNDS if speech.engine.name == "vbee" else 0):
        cands = [c for c in rules.probe_candidates(decisions, pauses)
                 if not any(c["piece"] == p["piece"] and c["i"] == p["i"] for p in probes)]
        if not cands:
            break
        results = []
        for n, c in enumerate(cands):
            if not speech.known(*c["piece"]) or not speech.known(*c["rest"]):
                job.update(stage="probe", progress=0.9 + 0.09 * n / len(cands),
                           message=f"Vbee kiểm tra tiếng thừa đầu/cuối câu {n + 1}/{len(cands)}")
            r = {**c, "piece_text": speech.text(*c["piece"])}
            if rules.needs_rest(r["piece_text"], aliases):   # the piece has words: said again right after?
                r["rest_text"] = speech.text(*c["rest"])
            results.append(r)
        rules.apply_probes(decisions, results, pauses, aliases)
        probes += results
    return decisions, probes


MODES = ("intro", "tutorial")   # talking-head intro / screen-recorded tutorial (2026-10-15)


def analyze(job: Job, engine: str, app_id: str = "", token: str = "", aliases: str = "",
            mode: str = "intro") -> None:
    try:
        src = job.source
        info = ff.probe(src)
        if not info.has_audio:
            raise RuntimeError("Clip không có âm thanh")
        job.update(stage="detect", message="Đang tìm các quãng nói…", progress=0.02, aliases=aliases, engine=engine,
                   mode=mode, media={"duration": info.duration, "width": info.width, "height": info.height,
                                     "fps": str(info.fps), "hdr": info.hdr})
        isl, pauses, det = islands.detect(src, info.duration)
        job.update(detect=det)
        if mode == "tutorial":
            job.update(stage="detect", progress=0.04, message="Đang đo chuyển động trên màn hình…")
            motion.save(job.dir / "motion.npz", *motion.measure(src))

        with tempfile.TemporaryDirectory() as tmp:
            eng = make_engine(engine, app_id, token, lambda m: job.update(stage="detect", message=m))
            speech = _Speech(src, eng, Path(tmp))
            todo = [k for k, (a, b) in enumerate(isl) if b - a >= rules.MIN_TRANSCRIBE and not speech.known(a, b)]
            heard: dict[int, tuple] = {}
            for k, (a, b) in enumerate(isl):
                if b - a < rules.MIN_TRANSCRIBE:
                    continue
                if not speech.known(a, b):
                    n = todo.index(k)
                    left = "" if engine != "vbee" else \
                        f" (còn khoảng {max(1, (len(todo) - n) * SECONDS_PER_CALL // 60)} phút)"
                    job.update(stage="transcribe", progress=0.05 + 0.85 * n / max(1, len(todo)),
                               message=f"{eng.label.capitalize()} đang nghe quãng {n + 1}/{len(todo)}{left}")
                heard[k] = speech.heard(a, b)
            isl_objs = [rules.Island(k, a, b, *heard.get(k, (None, None))) for k, (a, b) in enumerate(isl)]
            decisions, probes = _decide_and_probe(job, speech, isl_objs, pauses, aliases, mode)
        _save_analysis(job, info.duration, pauses, isl_objs, decisions, probes, aliases,
                       speech.calls if engine == "vbee" else 0)
    except VbeeAuthError as e:
        job.update(stage="error", message=str(e))
    except Exception as e:  # surfaced in the UI; full trace kept in the job folder
        (job.dir / "error.log").write_text(traceback.format_exc())
        job.update(stage="error", message=f"Lỗi: {e}")


def reanalyze(job: Job, app_id: str, token: str, aliases: str) -> None:
    """Re-run the rules with new aliases on what was already heard (only new Vbee probes cost calls)."""
    try:
        a = json.loads((job.dir / "analysis.json").read_text())
        isl_objs = [rules.Island(**x) for x in a["islands"]]
        pauses = [tuple(p) for p in a["pauses"]]
        engine = job.state().get("engine", "vbee")          # jobs made before 2026-10-11 used Vbee
        mode = job.state().get("mode", "intro")
        job.update(stage="probe", progress=0.9, message="Đang áp dụng lại quy tắc…", aliases=aliases)
        with tempfile.TemporaryDirectory() as tmp:
            speech = _Speech(job.source, make_engine(engine, app_id, token), Path(tmp))
            decisions, probes = _decide_and_probe(job, speech, isl_objs, pauses, aliases, mode)
        _save_analysis(job, a["duration"], pauses, isl_objs, decisions, probes, aliases,
                       job.state().get("vbee_calls", 0) + (speech.calls if engine == "vbee" else 0))
    except VbeeAuthError as e:
        job.update(stage="error", message=str(e))
    except Exception as e:
        (job.dir / "error.log").write_text(traceback.format_exc())
        job.update(stage="error", message=f"Lỗi: {e}")


def _save_analysis(job, duration, pauses, isl_objs, decisions, probes, aliases, calls) -> None:
    (job.dir / "analysis.json").write_text(json.dumps(
        {"duration": duration, "pauses": pauses, "aliases": aliases,
         "islands": [{"i": x.i, "start": x.start, "end": x.end, "text": x.text, "words": x.words} for x in isl_objs],
         "probes": probes, "decisions": [d.to_dict() for d in decisions]},
        ensure_ascii=False, indent=1))
    segs = output_plan(job, decisions, pauses, duration, rules.DEFAULT_PACE)   # what "Xuất" gives by default
    job.update(stage="review", progress=1.0, message="Sẵn sàng để duyệt", estimate=plan_seconds(segs),
               vbee_calls=calls)


def output_plan(job: Job, decisions, pauses, duration: float, pace: str, fast_forward: bool = True) -> list[tuple]:
    """(start, end, ff) segments to render: kept speech, plus muted fast-forwards in tutorial mode."""
    rngs = rules.ranges(decisions, [tuple(p) for p in pauses], duration, pace)
    if job.state().get("mode") == "tutorial" and fast_forward:
        m, th = motion.load(job.dir / "motion.npz")
        return motion.plan(rngs, m, th)
    return [(a, b, None) for a, b in rngs]


def plan_seconds(segs) -> float:
    return round(sum(f if f else b - a for a, b, f in segs), 2)


def load_analysis(job: Job) -> tuple[dict, list[rules.Decision]]:
    a = json.loads((job.dir / "analysis.json").read_text())
    return a, [rules.Decision(**d) for d in a["decisions"]]


def apply_overrides(decisions: list[rules.Decision], edits: dict) -> list[rules.Decision]:
    """edits: island index → bool (keep) or {"keep": bool, "start": s, "end": s, "cuts": [[a, b], …]}.

    start/end/cuts come from the review screen (pause points inside the island); they are
    clamped to the island so a stale edit can never reach into a neighbour.
    """
    for d in decisions:
        e = edits.get(d.i)
        if e is None:
            continue
        if isinstance(e, bool):
            e = {"keep": e}
        changed = False
        if "keep" in e and bool(e["keep"]) != d.keep:
            d.keep, changed = bool(e["keep"]), True
        for f in ("start", "end"):
            if e.get(f) is not None:
                v = min(max(float(e[f]), d.start), d.end)
                if abs(v - getattr(d, "keep_" + f)) > 1e-3:
                    setattr(d, "keep_" + f, v)
                    changed = True
        if e.get("cuts") is not None:
            cuts = sorted([float(a), float(b)] for a, b in e["cuts"] if float(a) < float(b))
            if cuts != sorted(d.cuts):
                d.cuts, changed = cuts, True
        if d.keep_end - d.keep_start < 0.1:
            d.keep, changed = False, True
        d.cuts = [c for c in d.cuts if d.keep_start < c[0] and c[1] < d.keep_end]
        if changed:
            d.reason = "bạn chỉnh tay" if d.keep else "bạn chọn bỏ"
            d.kind = "USER"
    return decisions


def export(job: Job, keep: dict, pace: str = rules.DEFAULT_PACE, fast_forward: bool = True) -> None:
    try:
        a, decisions = load_analysis(job)
        decisions = apply_overrides(decisions, keep)
        segs = output_plan(job, decisions, a["pauses"], a["duration"], pace, fast_forward)
        # intro jobs keep the old (start, end) shape; tutorial segments carry the fast-forward length
        rngs = [(s0, s1, f) if job.state().get("mode") == "tutorial" else (s0, s1) for s0, s1, f in segs]
        if not rngs:
            raise RuntimeError("Không còn câu nào được giữ")
        job.update(stage="render", progress=0.0, message="Đang xuất video…")
        info = ff.probe(job.source)
        out = job.dir / "roughcut.mp4"
        work = job.dir / "work"
        shutil.rmtree(work, ignore_errors=True)
        stats = render.render(job.source, info, rngs, out, work,
                              progress=lambda m, p: job.update(stage="render", message=m, progress=p))
        write_cutlist(job, decisions, rngs, a["duration"], stats["duration"])
        shutil.rmtree(work, ignore_errors=True)
        job.update(stage="done", progress=1.0, message="Hoàn tất", result=stats, ranges=rngs, pace=pace,
                   fast_forward=fast_forward)
    except Exception as e:
        (job.dir / "error.log").write_text(traceback.format_exc())
        job.update(stage="error", message=f"Lỗi khi xuất: {e}")


def write_cutlist(job: Job, decisions, rngs, src_dur: float, out_dur: float) -> None:
    lines = [f"Nguồn: {job.state().get('name')}  ({src_dur:.1f}s) → bản cắt thô {out_dur:.1f}s",
             "", "ĐOẠN GIỮ (giây trong file gốc):"]
    for r in rngs:
        a, b = r[0], r[1]
        f = r[2] if len(r) > 2 else None
        lines.append(f"  {a:8.2f} – {b:8.2f}  ({b - a:5.2f}s)" + (f"  TUA NHANH → {f:.1f}s, tắt tiếng" if f else ""))
    lines += ["", "TỪNG QUÃNG NÓI:"]
    for d in decisions:
        mark = "GIỮ" if d.keep else "BỎ "
        lines.append(f"  [{mark}] {d.start:7.2f}–{d.end:7.2f}  {d.text or '—'}   ({d.reason})")
    (job.dir / "cutlist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def island_preview(job: Job, i: int) -> Path:
    """Short MP3 of one island for the ▶ button (cached)."""
    a, decisions = load_analysis(job)
    d = next(x for x in decisions if x.i == i)
    out = job.dir / "previews" / f"isl_{i:03d}.mp3"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        s = max(0.0, d.start - 0.1)
        ff.run([ff.FFMPEG, "-y", "-v", "error", "-ss", f"{s:.3f}", "-i", str(job.source),
                "-t", f"{d.end + 0.1 - s:.3f}", "-vn", "-ac", "1", "-b:a", "96k", str(out)])
    return out


def start_thread(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()
