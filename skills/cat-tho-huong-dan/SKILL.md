---
name: cat-tho-huong-dan
description: Free, offline rough cut of a SCREEN-RECORDING tutorial (an app / Claude Code / ChatGPT walkthrough with spontaneous Vietnamese narration, optionally a webcam bubble bottom-left). Speech is recognised on this Mac with Zipformer-vi, so there is no Vbee, no whisper, no API key and no bill. It removes fillers, restarts and retakes (last clean take wins), cuts still dead air, and FAST-FORWARDS (muted) the silent waits where the screen is moving. It flags suspected repeats for review and outputs a frame-exact mp4 at -14 LUFS plus a cut list. Use it whenever the user wants a "video hướng dẫn", tutorial, course lesson or screen recording rough-cut without Vbee: "cắt thô video hướng dẫn", "cắt thô clip quay màn hình", "tua nhanh đoạn chờ", "bỏ đoạn lặng / nói lặp", "cắt thô không dùng Vbee / offline / miễn phí", or drops a screen-recording .mov/.mp4 and says "cắt thô giúp". For a face-to-camera clip use cat-tho-talking-head. If a Vbee-based skill (cat-tho-huong-dan-vbee) is also installed, prefer this one unless the user asks for Vbee.
---

# Rough cut: screen-recording tutorial (offline, no Vbee)

This skill drives the rough-cut engine in `~/skill-edit-video/engine` (repo github.com/minhtam021/skill-edit-video) from the command line, in **tutorial** mode with the **Zipformer** engine. The rules, the motion measure, the renderer and the cache are the same code as the web app. On the reference clip (8.3 min), the CLI with the suggested repeats dropped gave 151.07 s, the same as the hand-reviewed web export.

```bash
R=~/skill-edit-video/engine
PY=$R/.venv/bin/python
CLI="$PY $R/scripts/roughcut_cli.py"
```

`$R/README.md` explains every rule and the fast-forward thresholds. Read it when a decision looks wrong.

## 0. Setup check (once per session)

- `$PY` exists. If not, run `bash ~/skill-edit-video/install.sh` (or `cd $R && uv sync`).
- ffmpeg-full is installed (`brew install ffmpeg-full`).
- The model is in `$R/models/sherpa-onnx-zipformer-vi-int8-2025-04-20`. If it is missing, the first analyze downloads ~70 MB with pinned SHA-256s. Tell the user before that first run.
- Look at a frame first (`ffmpeg -ss 30 -i "<video>" -frames:v 1 /tmp/x.png`). The motion measure masks a webcam bubble at the **bottom-left** (x 0–12 %, y 86–100 %). If the bubble sits elsewhere, its movement counts as screen activity, and still waits get fast-forwarded instead of cut. Warn the user. The mask is `MASK` in `$R/roughcut/motion.py`.

## 1. Names that get mis-heard

Tutorials are full of product names ("Claude", "skill", "Codex", "Astra"…). Zipformer spells them in Vietnamese, and retakes only match when the names match.

- By default the CLI uses the list last saved in the web app, else the built-in Claude/skill list.
- Write a file with one name per line, `Tên đúng: nghe nhầm 1, nghe nhầm 2`, and pass `--aliases FILE` for the names this video uses.

## 2. Analyze

```bash
$CLI analyze "<video>" --mode tutorial [--aliases FILE]
```

The source is symlinked into `$R/jobs/<id>/`, not copied (pass `--copy` if the original may move). An 8-minute clip takes about 20 s. Expect roughly 2–3 % of the clip length, and a re-run of the same file reuses the cached transcript.

The command prints the review (`$R/jobs/<id>/review.txt`) with three parts:

- every island with GIỮ/BỎ, kind, heard text and reason;
- **NGHI LẶP**: kept phrases whose words are said again in a later phrase within 30 s. These are suggestions only, and nothing is dropped automatically, because an automatic version cut real restatements in testing. Each line says `bỏ <i> (+ giữa: [ids]) vì <j> nói lại`.
- words that look like mis-heard names.

## 3. Review it yourself before showing the user

- **NGHI LẶP**: for each suggestion, compare the text of `i` and `j` in the list. Accept it when `j` really re-says `i` (a retake). Reject it when the two are a comparison or a deliberate recap. Accepting means dropping `i` **and** every id in `giữa`. Dropped phrases join the fast-forward when the screen is moving and are cut when it is still.
- **Read the GIỮ lines in order.** A sentence said twice in a row is a missed retake.
- **Check long BỎ lines** (RETAKE / rephrased). In a tutorial, "về giao diện…" re-said while clicking is usually a real restart, but a step repeated on purpose ("bấm lại lần nữa") is not.
- **Foreign words**: add the clear mis-hearings to the alias file and run `$CLI realias <id> --aliases FILE`. It is instant and does not re-listen.

Give the user a short summary: source → estimated length, phrases dropped by kind, the NGHI LẶP suggestions with your recommendation for each (quote both texts and the time), and anything else you are unsure about. Ask before applying the suggestions, unless the user already said to go ahead.

## 4. Export

Overrides go in a JSON file keyed by island index: `{"156": false, "158": false, "12": true}`. Fine edits use `{"12": {"keep": true, "start": s, "end": s, "cuts": [[a, b]]}}` in source seconds.

```bash
$CLI export <id> [--edits FILE] [--pace fast|relaxed] [--no-ff] --out "<video_dir>/<stem>_roughcut.mp4"
```

- Fast-forward is on by default. A silent wait over 1.5 s with more than 2.5 % of the pixels changing (or with an end screen that differs from the start) keeps only its moving part, sped up to clamp(length / 10, 1, 4) s and muted. A still wait is cut. `--no-ff` cuts every wait instead.
- `fast` pace (default) trims phrase edges tight and shrinks inner pauses. `relaxed` keeps the original pacing.
- The cut list (`<stem>_roughcut.cutlist.txt`) marks every fast-forward as `TUA NHANH → Ns, tắt tiếng`.

## 5. Verify, then hand over

- `ffprobe -v error -show_entries stream=codec_type,duration -of csv=p=0 <out>`: the video and audio durations must match.
- Spot-check one fast-forward from the cut list: extract a frame inside it and confirm the screen is actually doing something.
- Report the output path, the length (source → cut), the number of fast-forwards, and the cut-list path.
- For by-ear review with ▶ per phrase and a ✂ split at pauses, offer the web app: `$R/run.sh`, http://127.0.0.1:8765. The job is in the recent list.

## Limits

- One narrator, one clip per job. The webcam mask is fixed to bottom-left.
- A filler glued inside a sentence with no pause around it cannot be cut.
- Very long recordings (hours) work, but review takes longer; check NGHI LẶP carefully.
