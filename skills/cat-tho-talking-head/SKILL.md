---
name: cat-tho-talking-head
description: Free, offline rough cut of a SHORT talking-head clip (one person speaking to the camera, a few minutes, Vietnamese). Speech is recognised on this Mac with Zipformer-vi, so there is no Vbee, no API key and no per-second bill. It removes silences, fillers (à / ừ / ờm), stutters, restarts and retakes (last clean take wins), and outputs a frame-exact mp4 at -14 LUFS plus a cut list with a reason for every cut. Use it whenever the user wants an intro, vlog-to-camera, selfie, DJI/phone/webcam clip "cắt thô", "cắt thô intro", "cắt thô talking head", "bỏ đoạn lặng / từ đệm / nói lặp", "cắt thô không dùng Vbee", "cắt offline / miễn phí", or just drops a short face-to-camera .mov/.mp4 and says "cắt thô giúp". For a screen-recording tutorial use cat-tho-huong-dan instead. For Vbee speech-to-text instead, use the web app ($R/run.sh, engine "Vbee").
---

# Rough cut: talking head (offline, no Vbee)

This skill drives the rough-cut engine in `~/skill-edit-video/engine` (repo github.com/minhtam021/skill-edit-video) from the command line, in **intro** mode with the **Zipformer** engine. The rules, the renderer and the cache are the same code as the web app, so a CLI cut matches what the app exports. The reference clip raw-gpt.mp4 came out at 73.2 s from the CLI and 73.17 s from the web export.

```bash
R=~/skill-edit-video/engine
PY=$R/.venv/bin/python
CLI="$PY $R/scripts/roughcut_cli.py"
```

`$R/README.md` explains every rule (RETAKE, RESTART, STUTTER, TAIL_OVERLAP…). Read it when a decision looks wrong.

## 0. Setup check (once per session)

- `$PY` exists. If not, run `bash ~/skill-edit-video/install.sh` (or `cd $R && uv sync`).
- ffmpeg-full is installed (`brew install ffmpeg-full`). The app finds the keg-only build itself.
- The model is in `$R/models/sherpa-onnx-zipformer-vi-int8-2025-04-20`. If it is missing, the first analyze downloads ~70 MB from the sherpa-onnx GitHub release and checks it against pinned SHA-256s. Tell the user before that first run.

## 1. Names that get mis-heard

Zipformer hears English words in Vietnamese spelling ("skill" → "seo", "Claude" → "cloud/clot"). Two takes of one sentence only match when the names match, so the name list matters for retakes.

- By default the CLI uses the list last saved in the web app (`~/.config/vbee-roughcut/config.json`), else the built-in Claude/skill list.
- If the clip names other products or people, write a file, one name per line in the form `Tên đúng: nghe nhầm 1, nghe nhầm 2`, and pass `--aliases FILE`.

## 2. Analyze

```bash
$CLI analyze "<video>" --mode intro [--aliases FILE]
```

The source is symlinked into `$R/jobs/<id>/`, not copied. Pass `--copy` if the user may move the original. A clip of a few minutes takes under a minute. A re-run of the same file is instant, because the transcript is cached by file hash.

The command prints the job id and the review (`$R/jobs/<id>/review.txt`): every island with GIỮ/BỎ, its kind, the heard text (with names applied) and the reason, plus "TỪ NGHE KHÔNG GIỐNG TIẾNG VIỆT" (words that look like mis-heard names).

## 3. Review it yourself before showing the user

Read review.txt and check it the way an editor would:

- **Read the GIỮ lines in order.** They should read as one clean script. A sentence that appears twice in a row means a missed retake: drop the earlier one.
- **Check every long BỎ line** (RETAKE / rephrased, more than ~5 words). The known false positive is intentional repetition (anaphora within 60 s) and a dropped line the later take does not actually cover. Keep those.
- **Look at the foreign words.** If one is clearly a mis-heard name (for example "astra" ×4 for a product), add it to the alias file and run `$CLI realias <id> --aliases FILE`. This re-runs the rules without re-listening, and is instant.

Then tell the user, in a short summary: source length → estimated length, how many phrases were dropped by kind, and only the decisions you are unsure about, quoting their text and time. Do not paste the whole list. Ask before overriding any decision the rules made, unless the user said to go ahead.

## 4. Export

Overrides go in a JSON file keyed by island index: `{"12": true, "40": false}` (true = keep, false = drop). Optional fine edits use `{"12": {"keep": true, "start": s, "end": s, "cuts": [[a, b]]}}`, in source seconds, clamped to the island.

```bash
$CLI export <id> [--edits FILE] [--pace fast|relaxed] --out "<video_dir>/<stem>_roughcut.mp4"
```

- `fast` (default) keeps 0.06 s before and 0.10 s after each phrase and shrinks inner pauses over 0.6 s to 0.4 s. It matched a hand edit. `relaxed` keeps the original pacing.
- `--out` also writes `<stem>_roughcut.cutlist.txt` next to the video.

## 5. Verify, then hand over

- `ffprobe -v error -show_entries stream=codec_type,duration -of csv=p=0 <out>`: the video and audio durations must match, and roughly match the printed length.
- Report the output path, the length (source → cut), the gain applied, and the cut list path.
- For fine, by-ear review, offer the web app: `$R/run.sh` opens http://127.0.0.1:8765, and the job made here is in the recent list.

## Limits

- One speaker, one clip per job.
- A filler glued inside a sentence with no pause around it cannot be cut.
- If the user wants captions, effects or the podcast look afterwards, hand the mp4 to video-effects or cinematic-podcast-edit.
