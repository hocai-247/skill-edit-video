"""Headless rough cut with the local engine only (Zipformer-vi, offline, no Vbee).

Same rules and renderer as the web app, driven from the command line so a skill can run it:

  analyze <video> --mode intro|tutorial [--aliases FILE] [--copy]
      → prints the job id; writes jobs/<id>/analysis.json and jobs/<id>/review.txt
  review  <job>                  → reprint review.txt (decisions, suspected repeats, unknown words)
  realias <job> --aliases FILE   → re-run the rules with a new name list (no re-listening)
  export  <job> [--pace fast|relaxed] [--edits FILE] [--no-ff] [--out PATH]
      → renders roughcut.mp4 + cutlist.txt (and copies the mp4 to --out)

--edits is JSON {"<island>": true|false | {"keep", "start", "end", "cuts"}}, the same shape the
review screen sends. Run with the repo venv: .venv/bin/python scripts/roughcut_cli.py …
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roughcut import pipeline, stt  # noqa: E402
from roughcut.decide import DEFAULT_PACE, PACES, display_text, foreign_words, suspect_repeats  # noqa: E402

ENGINE = "zipformer"


def _job(jid: str) -> pipeline.Job:
    job = pipeline.Job(jid)
    if not job.dir.is_dir():
        sys.exit(f"Không có job {jid} trong {pipeline.JOBS}")
    return job


def _aliases(path: str | None) -> str:
    """Name list: the file given, else the app's remembered list, else the local defaults."""
    if path:
        return Path(path).read_text(encoding="utf-8").strip()[:2000]
    cfg = Path.home() / ".config" / "vbee-roughcut" / "config.json"
    saved = json.loads(cfg.read_text()).get("aliases") if cfg.exists() else None
    return saved or stt.LOCAL_ALIASES


def _check(job: pipeline.Job) -> None:
    s = job.state()
    if s.get("stage") == "error":
        log = job.dir / "error.log"
        sys.exit(f"LỖI: {s.get('message')}" + (f"\n{log.read_text()}" if log.exists() else ""))


def _write_review(job: pipeline.Job) -> str:
    a, ds = pipeline.load_analysis(job)
    aliases, pauses = a.get("aliases"), [tuple(p) for p in a["pauses"]]
    s = job.state()
    lines = [f"JOB {job.id}  mode={s.get('mode')}  nguồn={a['duration']:.1f}s  "
             f"ước tính bản cắt (nhịp {DEFAULT_PACE})={s.get('estimate')}s", "",
             "QUÃNG NÓI  (i  [GIỮ/BỎ]  thời gian  KIND  text  — lý do):"]
    for d in ds:
        mark = "GIỮ" if d.keep else "BỎ "
        span = f"{d.start:7.2f}–{d.end:7.2f}"
        trim = ""
        if d.keep and (abs((d.keep_start or d.start) - d.start) > 0.01 or abs((d.keep_end or d.end) - d.end) > 0.01
                       or d.cuts):
            trim = f"  [giữ {d.keep_start:.2f}–{d.keep_end:.2f}" + (f", cắt trong {d.cuts}" if d.cuts else "") + "]"
        lines.append(f"{d.i:4d} [{mark}] {span} {d.kind:<12} {display_text(d.text, aliases) or '—'}"
                     f"   — {d.reason}{trim}")
    if s.get("mode") == "tutorial":
        sus = suspect_repeats(ds, aliases, pauses)
        lines += ["", f"NGHI LẶP (gợi ý, CHƯA áp dụng) — {len(sus)}:"]
        for x in sus:
            lines.append(f"  bỏ {x['i']} (+ giữa: {x['between']}) vì {x['by']} nói lại ({x['shared']} từ chung,"
                         f" lúc {x['at']}s)")
    fw = foreign_words(ds, aliases)
    if fw:
        lines += ["", "TỪ NGHE KHÔNG GIỐNG TIẾNG VIỆT (có thể là tên riêng nghe nhầm):",
                  "  " + ", ".join(f"{w['w']}×{w['n']}" for w in fw)]
    text = "\n".join(lines) + "\n"
    (job.dir / "review.txt").write_text(text, encoding="utf-8")
    return text


def cmd_analyze(args) -> None:
    src = Path(args.video).expanduser().resolve()
    if not src.exists():
        sys.exit(f"Không thấy file {src}")
    pipeline.JOBS.mkdir(exist_ok=True)

    def save(dst: Path) -> None:
        if args.copy:
            shutil.copy2(src, dst)
        else:
            os.symlink(src, dst)   # hours-long tutorials: no multi-GB copy

    job = pipeline.Job.create(src.name, save)
    print(f"JOB {job.id}", flush=True)
    pipeline.analyze(job, ENGINE, aliases=_aliases(args.aliases), mode=args.mode)
    _check(job)
    print(_write_review(job), end="")
    print(f"\n→ {job.dir / 'review.txt'}")


def cmd_review(args) -> None:
    job = _job(args.job)
    _check(job)
    print(_write_review(job), end="")


def cmd_realias(args) -> None:
    job = _job(args.job)
    pipeline.reanalyze(job, "", "", _aliases(args.aliases))
    _check(job)
    print(_write_review(job), end="")


def cmd_export(args) -> None:
    job = _job(args.job)
    edits = {}
    if args.edits:
        for k, v in json.loads(Path(args.edits).read_text()).items():
            edits[int(k)] = v if isinstance(v, dict) else bool(v)
    job.update(keep={str(k): v for k, v in edits.items()}, pace=args.pace)
    pipeline.export(job, edits, args.pace, not args.no_ff)
    _check(job)
    out = job.dir / "roughcut.mp4"
    r = job.state().get("result", {})
    if args.out:
        dst = Path(args.out).expanduser()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, dst)
        shutil.copy2(job.dir / "cutlist.txt", dst.with_suffix(".cutlist.txt"))
        out = dst
    print(f"XONG {out}  ({r.get('duration', 0):.1f}s, gain {r.get('gain_db')} dB)")
    print(f"cutlist: {job.dir / 'cutlist.txt'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("video")
    a.add_argument("--mode", choices=pipeline.MODES, required=True)
    a.add_argument("--aliases", help="file: one name per line, 'Claude: cloud, clot'")
    a.add_argument("--copy", action="store_true", help="copy the source into the job instead of a symlink")
    a.set_defaults(fn=cmd_analyze)
    r = sub.add_parser("review")
    r.add_argument("job")
    r.set_defaults(fn=cmd_review)
    ra = sub.add_parser("realias")
    ra.add_argument("job")
    ra.add_argument("--aliases", required=True)
    ra.set_defaults(fn=cmd_realias)
    e = sub.add_parser("export")
    e.add_argument("job")
    e.add_argument("--pace", choices=list(PACES), default=DEFAULT_PACE)
    e.add_argument("--edits", help="JSON file of keep/drop overrides by island index")
    e.add_argument("--no-ff", action="store_true", help="tutorial: cut busy silent waits instead of fast-forwarding")
    e.add_argument("--out", help="also copy the result here (cutlist next to it)")
    e.set_defaults(fn=cmd_export)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
