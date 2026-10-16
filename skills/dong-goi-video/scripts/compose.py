"""Final package render: segments → per-segment zoom → concat → alpha overlays → captions LAST,
plus speech (compressor) + SFX → static gain to target LUFS → limiter, muxed.

Two passes (video, then audio) straight from the sources in segments.json, so there is no
concat-demuxer timestamp drift. Every video stream is put on ONE integer frame clock
(settb=1/fps, setpts=N[+start_frame]): mixing the source timebase with ProRes overlay timebases
made some cards repeat every 3rd frame (measured), even though the overlay files were smooth.

package.json (paths relative to the file):
{
  "segments": "segments.json",
  "zooms": {"2": 1.12, "16": ["push", 1.0, 1.06],    # per segment index; omitted = wide
            "5": {"z": 1.16, "anchor": [930, 420]},   # per-segment anchor when the speaker sits differently
            "7": {"z": 1.0, "whip_in": true}},        # zoom-blur transition into (or "whip_out" of) a segment
  "grade": "eq=contrast=1.1:brightness=-0.04,vignette=PI/5",  # optional ffmpeg filter on the footage
  "grade_accent": {"filter": "eq=brightness=-0.05,...", "windows": [[0, 9.5], [21.6, 24.2]],
                   "fade_in": 0.35, "fade_out": 0.5},   # optional: a second grade faded in over windows
  "zoom_anchor": [930, 400],                         # point kept fixed while zooming: eyes/forehead,
                                                     # not the face centre (that crops the hair at 1.12+)
  "overlays": [["animations/s1/render.mov", 1.30],   # [file, start on output timeline]
               ["animations/s9/render.mov", 69.55, {"full_frame": true}]],
  "safe_box": [1180, 100, 680, 600],                 # x, y, w, h — qc.py checks card motion here
  "person_mask": "mask.mp4",                         # with overlays flagged {"behind": true}: text goes
                                                     # BEHIND the speaker (mask from person_mask.py on --base)
  "captions": "captions.ass", "fonts_dir": "fonts",
  "sfx_cues": "sfx_cues.json", "sfx_dir": "sfx",     # cues: [[name, hit_time, gain_db], ...]
  "target_lufs": -14, "audio_tail_fade": 0.15, "video_fade_out": 0,
  "out": "final.mp4", "preview_out": "preview.mp4"
}
Usage: python compose.py package.json [--preview]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("ffmpeg failed:\n" + p.stderr[-3000:])
    return p.stderr


def peak_offset(wav: Path) -> float:
    """Seconds from file start to the loudest sample, so the cue's hit time lands on the transient."""
    with wave.open(str(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, w.getnchannels())
        return int(np.abs(x).max(1).argmax()) / w.getframerate()


def z_anchor(z, default):
    """A zoom may carry its own anchor: {"z": 1.12, "anchor": [930, 420]} (speaker sits lower in that take)."""
    return z.get("anchor", default) if isinstance(z, dict) else default


def zoom_filter(z, d: float, fps: int, anchor) -> str:
    ax, ay = anchor
    n = max(1, round(d * fps) - 1)
    if isinstance(z, dict) and (z.get("whip_in") or z.get("whip_out")):
        # zoom-blur transition: the first/last 6 frames punch from +28% back to the base zoom,
        # the 3 frames nearest the cut are heavily blurred (a cheap "zoom through" / whip).
        base = float(z.get("z", 1.0))
        terms = []
        if z.get("whip_in"):
            terms.append("0.28*pow(max(0,1-on/6),2)")
        if z.get("whip_out"):
            terms.append(f"0.28*pow(max(0,(on-{n - 6})/6),2)")
        zexpr = f"{base}*(1+{'+'.join(terms)})"
        blur = []
        if z.get("whip_in"):
            blur.append("lt(n,3)")
        if z.get("whip_out"):
            blur.append(f"gt(n,{n - 3})")
        return (f",scale=3840:2160:flags=lanczos,zoompan=z='{zexpr}':x='{2 * ax}*(1-1/zoom)':"
                f"y='{2 * ay}*(1-1/zoom)':d=1:s=1920x1080:fps={fps},"
                f"gblur=sigma=22:steps=2:enable='{'+'.join(blur)}'")
    if isinstance(z, dict):
        z = z.get("push") and ["push", *z["push"]] or z.get("z")
    if z is None:
        return ""
    if isinstance(z, (int, float)):
        z = float(z)
        w, h = round(1920 * z / 2) * 2, round(1080 * z / 2) * 2
        return f",scale={w}:{h}:flags=lanczos,crop=1920:1080:{round(ax * (z - 1))}:{round(ay * (z - 1))}"
    _, z0, z1 = z
    zexpr = f"{z0}+({z1}-{z0})*(1-pow(1-on/{n},3))"     # ease-out push; 2x upscale avoids zoompan jitter
    return (f",scale=3840:2160:flags=lanczos,zoompan=z='{zexpr}':x='{2 * ax}*(1-1/zoom)':"
            f"y='{2 * ay}*(1-1/zoom)':d=1:s=1920x1080:fps={fps}")


def main() -> None:
    cfg_path = Path(sys.argv[1]).resolve()
    here = cfg_path.parent
    cfg = json.loads(cfg_path.read_text())
    preview = "--preview" in sys.argv
    base_only = "--base" in sys.argv     # footage only (zoom + grade, no graphics/captions/audio) for person_mask.py
    P = lambda p: str((here / p).resolve())  # noqa: E731
    seginfo = json.loads(Path(P(cfg.get("segments", "segments.json"))).read_text())
    fps, segs, total = seginfo["fps"], seginfo["segments"], seginfo["total"]
    nframes = round(total * fps)
    zooms = {int(k): v for k, v in cfg.get("zooms", {}).items()}
    anchor = cfg.get("zoom_anchor", [960, 480])
    out = Path(P(cfg.get("preview_out", "preview.mp4") if preview else cfg.get("out", "final.mp4")))
    work = here / "_compose"; work.mkdir(exist_ok=True)
    srcs = sorted({s["src"] for s in segs})

    # ---------------- VIDEO ----------------
    inputs = sum((["-i", s] for s in srcs), [])
    fc, cat = [], ""
    for i, s in enumerate(segs):
        k = srcs.index(s["src"])
        # CFR first, then trim by FRAME INDEX: on variable-frame-rate phone footage a time-based
        # trim produced one frame fewer than planned and audio drifted 1-2 frames.
        f0, f1 = round(s["start"] * fps), round(s["end"] * fps)
        z = zooms.get(i)
        fc.append(f"[{k}:v]fps={fps},trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS"
                  f"{zoom_filter(z, (f1 - f0) / fps, fps, z_anchor(z, anchor))},setsar=1,format=yuv420p[v{i}]")
        cat += f"[v{i}]"
    grade = f",{cfg['grade']}" if cfg.get("grade") else ""        # applied to the footage only, under the graphics
    acc = cfg.get("grade_accent")
    if not acc:
        fc.append(f"{cat}concat=n={len(segs)}:v=1:a=0,settb=1/{fps},setpts=N{grade}[b0]")
    else:
        # Base grade most of the time; an "accent" grade (e.g. darker, moodier) cross-fades in over
        # given windows (cold open, big-text punch lines, close-ups). The accent copy is trimmed per
        # window BY FRAME INDEX (timestamps stay on the shared frame clock), given an alpha fade
        # in/out, and overlaid on the base.
        wins = acc["windows"]
        fi, fo = acc.get("fade_in", 0.35), acc.get("fade_out", 0.5)
        fc.append(f"{cat}concat=n={len(segs)}:v=1:a=0,settb=1/{fps},setpts=N,split=2[gb][ga]")
        fc.append(f"[gb]{cfg['grade'] if cfg.get('grade') else 'null'}[gbase]")
        fc.append(f"[ga]{acc['filter']},format=yuva420p,split={len(wins)}" + "".join(f"[ga{k}]" for k in range(len(wins))))
        cur_g = "[gbase]"
        for k, (a, b) in enumerate(wins):
            a = max(0.0, a); b = min(total, b)
            f0, f1 = round(a * fps), round(b * fps)
            fin = f"fade=t=in:st={a:.3f}:d={fi}:alpha=1," if a > 0.01 else ""
            fout = f"fade=t=out:st={max(a, b - fo):.3f}:d={fo}:alpha=1" if b < total - 0.01 else "null"
            fc.append(f"[ga{k}]trim=start_frame={f0}:end_frame={f1},{fin}{fout}[acc{k}]")
            fc.append(f"{cur_g}[acc{k}]overlay=0:0:eof_action=pass:format=auto[gm{k}]")
            cur_g = f"[gm{k}]"
        fc.append(f"{cur_g}format=yuv420p[b0]")
    if base_only:
        out = work / "base.mp4"
        run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc + ["[b0]format=yuv420p[vout]"]), "-map", "[vout]", "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-r", str(fps), "-frames:v", str(nframes), str(out)])
        print("base footage:", out)
        return
    cur = "[b0]"
    ovs = cfg.get("overlays", [])
    mask_idx = None
    is_behind = [len(o) > 2 and o[2].get("behind", False) for o in ovs]
    groups_end = [j for j in range(1, len(ovs) + 1) if is_behind[j - 1] and (j == len(ovs) or not is_behind[j])]
    if groups_end:
        # "Text behind the speaker": overlays flagged {"behind": true} are stacked on a transparent
        # canvas, their alpha is multiplied by (1 - person matte), and the result goes on the footage.
        # The matte input is split once (a filtergraph may consume an input stream only once).
        mask_idx = len(srcs) + len(ovs)
        fc.append(f"[{mask_idx}:v]settb=1/{fps},setpts=N,format=gray,negate,split={len(groups_end)}"
                  + "".join(f"[inv{j}]" for j in groups_end))
    canvas = None
    for j, ov in enumerate(ovs, start=1):
        f, t = ov[0], ov[1]   # optional 3rd item: {"full_frame": true} (qc.py) / {"behind": true}
        opts = ov[2] if len(ov) > 2 else {}
        idx = len(srcs) + j - 1
        inputs += ["-i", P(f)]
        fc.append(f"[{idx}:v]format=yuva444p,settb=1/{fps},setpts=N+{round(t * fps)}[o{j}]")   # PTS-shifted overlay
        if opts.get("behind"):
            if canvas is None:
                fc.append(f"color=c=black@0.0:s=1920x1080:r={fps}:d={total:.4f},format=yuva444p,settb=1/{fps},setpts=N[cv0_{j}]")
                canvas = f"[cv0_{j}]"
            fc.append(f"{canvas}[o{j}]overlay=0:0:eof_action=pass:format=auto[cv{j}]")
            canvas = f"[cv{j}]"
            nxt = ovs[j] if j < len(ovs) else None
            if nxt is None or not (len(nxt) > 2 and nxt[2].get("behind")):     # end of a behind-group: matte it
                fc.append(f"{canvas}split[tc{j}][ta{j}]")
                fc.append(f"[ta{j}]alphaextract[al{j}]")
                fc.append(f"[al{j}][inv{j}]blend=all_mode=multiply[am{j}]")
                fc.append(f"[tc{j}][am{j}]alphamerge[tm{j}]")
                fc.append(f"{cur}[tm{j}]overlay=0:0:format=auto[b{j}]")
                cur, canvas = f"[b{j}]", None
            continue
        fc.append(f"{cur}[o{j}]overlay=0:0:eof_action=pass:format=auto[b{j}]")
        cur = f"[b{j}]"
    if mask_idx is not None:
        inputs += ["-i", P(cfg["person_mask"])]
    tail = ""
    if cfg.get("captions"):
        ass = P(cfg["captions"]).replace(":", r"\:")
        fonts = P(cfg.get("fonts_dir", "fonts")).replace(":", r"\:")
        tail += f"subtitles='{ass}':fontsdir='{fonts}',"                              # captions LAST
    vf = cfg.get("video_fade_out", 0)
    if vf:
        tail += f"fade=t=out:st={total - vf:.3f}:d={vf},"
    fc.append(f"{cur}{tail}format=yuv420p[vout]")
    vid = work / "video.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-an",
         "-c:v", "libx264", "-preset", "veryfast" if preview else "slow", "-crf", "21" if preview else "17",
         "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-r", str(fps), "-frames:v", str(nframes), str(vid)])

    # ---------------- AUDIO ----------------
    ains = sum((["-i", s] for s in srcs), [])
    afc, acat = [], ""
    for i, s in enumerate(segs):
        k = srcs.index(s["src"])
        d = s["end"] - s["start"]
        afc.append(f"[{k}:a]atrim=start={s['start']:.6f}:end={s['end']:.6f},asetpts=PTS-STARTPTS,aresample={SR},"
                   f"apad,atrim=end={d:.6f},"   # exact length even if the source audio ends early
                   f"afade=t=in:st=0:d=0.03,afade=t=out:st={d - 0.03:.6f}:d=0.03[a{i}]")   # no pops at cuts
        acat += f"[a{i}]"
    afc.append(f"{acat}concat=n={len(segs)}:v=0:a=1,"
               f"acompressor=threshold=-24dB:ratio=2.5:attack=15:release=200:makeup=1,"
               f"aformat=sample_rates={SR}:channel_layouts=stereo[speech]")
    labels = []
    cues = json.loads(Path(P(cfg["sfx_cues"])).read_text()) if cfg.get("sfx_cues") else []
    sfx_dir = Path(P(cfg.get("sfx_dir", "sfx")))
    offsets: dict[str, float] = {}
    for j, (name, hit, gain) in enumerate(cues, start=len(srcs)):
        wav = sfx_dir / f"{name}.wav"
        offsets.setdefault(name, peak_offset(wav))
        ms = max(0, round((hit - offsets[name]) * 1000))
        ains += ["-i", str(wav)]
        afc.append(f"[{j}:a]aresample={SR},aformat=channel_layouts=stereo,volume={gain}dB,adelay={ms}|{ms}[s{j}]")
        labels.append(f"[s{j}]")
    tf = cfg.get("audio_tail_fade", 0.15)
    afc.append(f"[speech]{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first,"
               f"afade=t=out:st={total - max(tf, vf):.3f}:d={max(tf, vf):.3f}[mix]")
    mix = work / "mix.wav"
    run(["ffmpeg", "-y", *ains, "-filter_complex", ";".join(afc), "-map", "[mix]", "-c:a", "pcm_s24le",
         "-t", f"{total:.6f}", str(mix)])
    # loudnorm goes dynamic on speech (peak-to-loudness ~18 dB) and pumps SFX-only moments:
    # use a static gain to the target, then a peak limiter.
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mix), "-af", "ebur128", "-f", "null", "-"])
    mix_i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])
    gain = cfg.get("target_lufs", -14) - mix_i + 0.2
    master = work / "master.wav"
    run(["ffmpeg", "-y", "-i", str(mix), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.79:attack=5:release=50:level=0",
         "-c:a", "pcm_s24le", str(master)])

    got = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                              "stream=nb_read_packets", "-of", "csv=p=0", str(vid)], capture_output=True, text=True).stdout.strip() or 0)
    if got != nframes:
        print(f"WARNING: video has {got} frames, expected {nframes} — a segment came out short; check the sources")
    run(["ffmpeg", "-y", "-i", str(vid), "-i", str(master), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)])
    err = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-"])
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1]
    TP = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)[-1]
    print(f"done: {out}  frames={nframes} ({total:.3f}s)  mix I={mix_i:.2f}  final I={I} LUFS  TP={TP} dBFS")


if __name__ == "__main__":
    main()
