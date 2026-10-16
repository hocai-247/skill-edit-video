"""vbee-roughcut web app. Run: ./run.sh  →  http://127.0.0.1:8765"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from roughcut import pipeline, stt
from roughcut.decide import DEFAULT_PACE, PACES, display_text, foreign_words, pause_points, ranges, suspect_repeats

ROOT = Path(__file__).resolve().parent
CONFIG = Path.home() / ".config" / "vbee-roughcut" / "config.json"
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm"}

app = Flask(__name__, static_folder=str(ROOT / "static"))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 ** 3   # 8 GB


def job_or_404(jid: str) -> pipeline.Job:
    if not re.fullmatch(r"[\w-]{1,64}", jid) or not (pipeline.JOBS / jid).is_dir():
        abort(404)
    return pipeline.Job(jid)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def get_config():
    """Only says whether keys are saved — never returns them."""
    data = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    return jsonify(saved=bool(data.get("app_id")), aliases=data.get("aliases"),
                   engine=data.get("engine", "zipformer"), local_aliases=stt.LOCAL_ALIASES,
                   pace=data.get("pace", DEFAULT_PACE),
                   model_ready=stt.model_ready())


@app.delete("/api/config")
def forget_config():
    """Forget the keys (aliases stay: they are not secret)."""
    data = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    data.pop("app_id", None)
    data.pop("token", None)
    if data:
        CONFIG.write_text(json.dumps(data))
    else:
        CONFIG.unlink(missing_ok=True)
    return jsonify(saved=False)


def _keys(form, engine: str = "vbee") -> tuple[str, str]:
    """Vbee keys (only the Vbee engine needs them)."""
    app_id, token = str(form.get("app_id") or "").strip(), str(form.get("token") or "").strip()
    if engine != "vbee":
        return app_id, token
    if not app_id or not token:
        if CONFIG.exists():
            saved = json.loads(CONFIG.read_text())
            app_id, token = app_id or saved.get("app_id", ""), token or saved.get("token", "")
    if not app_id or not token:
        abort(400, "Thiếu App ID hoặc token")
    if str(form.get("remember")) == "1":
        data = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        data.update(app_id=app_id, token=token)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data))
        os.chmod(CONFIG, 0o600)
    return app_id, token


@app.post("/api/jobs")
def create_job():
    f = request.files.get("clip")
    if f is None or not f.filename:
        abort(400, "Chưa chọn clip")
    if Path(f.filename).suffix.lower() not in VIDEO_EXT:
        abort(400, f"Định dạng không hỗ trợ: {Path(f.filename).suffix}")
    engine = request.form.get("engine", "zipformer")
    if engine not in ENGINES:
        abort(400, f"Không biết công cụ nghe: {engine}")
    app_id, token = _keys(request.form, engine)
    aliases = request.form.get("aliases", "").strip()[:2000]
    mode = request.form.get("mode", "intro")
    if mode not in pipeline.MODES:
        abort(400, f"Không biết kiểu cắt: {mode}")
    _remember(aliases=aliases, engine=engine)
    job = pipeline.Job.create(f.filename, f.save)
    pipeline.start_thread(pipeline.analyze, job, engine, app_id, token, aliases, mode)
    return jsonify(id=job.id)


ENGINES = ("zipformer", "vbee")


def _remember(**kw) -> None:
    """Aliases and the engine choice are not secret: kept next to the keys for the next clip."""
    data = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if any(data.get(k) != v for k, v in kw.items()):
        data.update(kw)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data))
        os.chmod(CONFIG, 0o600)


@app.post("/api/jobs/<jid>/reanalyze")
def job_reanalyze(jid):
    job = job_or_404(jid)
    if job.state().get("stage") in ("detect", "transcribe", "probe", "render"):
        abort(409, "Job đang chạy")
    if not (job.dir / "analysis.json").exists():
        abort(409, "Chưa phân tích xong")
    body = request.json or {}
    app_id, token = _keys(body, job.state().get("engine", "vbee"))
    aliases = str(body.get("aliases", "")).strip()[:2000]
    _remember(aliases=aliases)
    pipeline.start_thread(pipeline.reanalyze, job, app_id, token, aliases)
    return jsonify(ok=True)


@app.get("/api/jobs")
def list_jobs():
    jobs = []
    for d in sorted(pipeline.JOBS.glob("*"), reverse=True)[:20]:
        if (d / "state.json").exists():
            s = json.loads((d / "state.json").read_text())
            jobs.append({k: s.get(k) for k in ("id", "name", "stage", "message", "estimate")})
    return jsonify(jobs)


@app.get("/api/jobs/<jid>")
def job_state(jid):
    return jsonify(job_or_404(jid).state())


@app.get("/api/jobs/<jid>/decisions")
def job_decisions(jid):
    job = job_or_404(jid)
    if not (job.dir / "analysis.json").exists():
        abort(409, "Chưa phân tích xong")
    a, ds = pipeline.load_analysis(job)
    pauses = [tuple(p) for p in a["pauses"]]
    out = []
    for d in ds:
        row = d.to_dict()
        row["points"] = pause_points(d, pauses, a.get("aliases"), min_len=0.0)
        row["display"] = display_text(d.text, a.get("aliases"))
        out.append(row)
    # tutorial jobs: kept phrases that look like an earlier take of a later one (suggested, never applied)
    suspects = suspect_repeats(ds, a.get("aliases"), pauses) if job.state().get("mode") == "tutorial" else []
    return jsonify(duration=a["duration"], aliases=a.get("aliases", ""), decisions=out,
                   foreign=foreign_words(ds, a.get("aliases")), suspects=suspects)


def _fast_forward(body) -> bool:
    """Tutorial mode: fast-forward busy silent waits (default) or cut them like the intro mode."""
    return bool((body or {}).get("fast_forward", True))


def _pace(body) -> str:
    pace = (body or {}).get("pace") or DEFAULT_PACE
    if pace not in PACES:
        abort(400, f"Nhịp không hợp lệ: {pace}")
    return pace


def _edits(body) -> dict:
    """{"keep": {i: bool | {keep, start, end, cuts}}} from the review screen."""
    out = {}
    for k, v in (body or {}).get("keep", {}).items():
        if isinstance(v, dict):
            out[int(k)] = {f: v[f] for f in ("keep", "start", "end", "cuts") if f in v}
        else:
            out[int(k)] = bool(v)
    return out


@app.post("/api/jobs/<jid>/estimate")
def job_estimate(jid):
    """Length of the result for a given set of keep toggles (live total in the review screen)."""
    job = job_or_404(jid)
    a, ds = pipeline.load_analysis(job)
    keep = _edits(request.json)
    segs = pipeline.output_plan(job, pipeline.apply_overrides(ds, keep), a["pauses"], a["duration"],
                                _pace(request.json), _fast_forward(request.json))
    ff = [(x, b, f) for x, b, f in segs if f]
    return jsonify(estimate=pipeline.plan_seconds(segs), segments=len(segs) - len(ff),
                   ff_count=len(ff), ff_source=round(sum(b - x for x, b, _ in ff), 1),
                   ff_output=round(sum(f for *_, f in ff), 1),
                   plan=[[round(x, 3), round(b, 3), f] for x, b, f in segs])   # for the review timeline


@app.post("/api/jobs/<jid>/export")
def job_export(jid):
    job = job_or_404(jid)
    if job.state().get("stage") in ("detect", "transcribe", "probe", "render"):
        abort(409, "Job đang chạy")
    keep = _edits(request.json)
    pace = _pace(request.json)
    fast_forward = _fast_forward(request.json)
    _remember(pace=pace)
    job.update(stage="render", progress=0.0, message="Đang chuẩn bị xuất…", keep={str(k): v for k, v in keep.items()},
               pace=pace)
    pipeline.start_thread(pipeline.export, job, keep, pace, fast_forward)
    return jsonify(ok=True)


@app.get("/api/jobs/<jid>/island/<int:i>.mp3")
def island_audio(jid, i):
    return send_file(pipeline.island_preview(job_or_404(jid), i), mimetype="audio/mpeg")


@app.get("/api/jobs/<jid>/result.mp4")
def result(jid):
    job = job_or_404(jid)
    p = job.dir / "roughcut.mp4"
    if not p.exists():
        abort(404)
    name = Path(job.state().get("name", "clip")).stem + "_roughcut.mp4"
    return send_file(p, mimetype="video/mp4", conditional=True,
                     as_attachment=request.args.get("download") == "1", download_name=name)


@app.get("/api/jobs/<jid>/cutlist.txt")
def cutlist(jid):
    p = job_or_404(jid).dir / "cutlist.txt"
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="text/plain; charset=utf-8", as_attachment=True,
                     download_name="cutlist.txt")


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(409)
def err(e):
    return jsonify(error=getattr(e, "description", str(e))), e.code


if __name__ == "__main__":
    pipeline.JOBS.mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", "8765"))
    print(f"vbee-roughcut → http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
