# vbee-roughcut

A local web app that turns a raw talking-head clip into a rough cut. It removes
silences, fillers (à / ừ / ờm) and retakes. Speech is recognised on this Mac by
default (Zipformer-vi, free, offline); Vbee speech-to-text is an option.

## Run

```bash
~/skill-edit-video/engine/run.sh
```

The script opens http://127.0.0.1:8765. In the app:

1. Choose how speech is heard:
   - **Máy này** (default): Zipformer-vi runs on this Mac. It is free and needs
     no key. On the first run the app downloads the model (~70 MB, from the
     sherpa-onnx GitHub release) into `models/` and checks every file against a
     pinned SHA-256.
   - **Vbee**: enter your App ID and token. Tick "Nhớ key" to keep them in
     `~/.config/vbee-roughcut/config.json` (chmod 600).

   The box below lists names and English words that get mis-heard, one per line
   (`Claude: cloud, clot, lót`). For "Máy này" it is prefilled with what the
   model usually hears for "skill" and "Claude". The list is remembered for the
   next clip.
2. Drop in a clip, pick the video type, then click "Bắt đầu cắt". The engine,
   the Vbee keys and the name list sit under "Tuỳ chọn nâng cao". The types are:
   - **Cắt thô intro**: a talking head speaking to the camera. This is the
     original behaviour, unchanged.
   - **Cắt thô video hướng dẫn**: a screen recording with spontaneous narration.
     Same rules, plus two for restarts heard slightly differently ("về giao
     diện…" said twice in a row; a sentence re-said after a few broken-off
     fragments). Silent waits where the screen is moving (more than 2.5 % of
     the pixels change, or the screen at the end differs from the start) are
     **fast-forwarded** and muted: only the moving part, shortened to
     clamp(length / 10, 1, 4) s. A still screen is cut. The review screen has a
     switch to cut those waits instead. The thresholds come from the
     cat-tho-huong-dan-vbee skill (formerly tutorial-roughcut).
     The review screen also marks **suspected repeats** ("NGHI LẶP"): a kept
     phrase whose words (at least 5, in order, and 60 % of it) are said again in
     a later phrase within 30 s, unless the two name different products (a
     comparison). Nothing is dropped automatically: an automatic version cut real
     restatements in testing. One click drops the phrase and the stumbles said
     between it and its retake. Dropped phrases join the fast-forward when the
     screen is moving, and are cut when it is still.

   Then wait. With "Máy này", a 9-minute clip takes about 1 minute
   (measured 50 s, ~2 minutes on the first run after start). With Vbee it takes
   about 25 s per phrase, one at a time.
3. Review. A timeline across the top shows the whole source: green is kept,
   red is dropped speech, purple is fast-forward and grey is cut silence. Click it
   to jump to that phrase. Then review the list. Names are shown with your list applied ("skill" instead of
   the heard "seo"; hover to see what was heard). Under "Tên riêng hay bị nghe
   nhầm" the app lists the words it heard that do not look Vietnamese. Click
   one to say which word it stands for, then "Áp dụng lại quy tắc".
    Each phrase shows keep/drop with a reason. ▶ plays the
   phrase, and the button on the right flips keep/drop. ✂ splits the phrase at
   its breath pauses: click a piece to drop or keep it (⌥-click plays just that
   piece). Use it for a stumble at the start, or a tail you said again. Under
   "Tên riêng hay bị nghe nhầm" you can change the name list and re-apply the
   rules to the text Vbee already heard.
4. Pick the pacing ("Nhịp"), then click "Xuất video" and download the video and
   `cutlist.txt`:
   - **Nhanh** (default): each phrase starts 0.06 s before the voice and ends
     0.10 s after it, and pauses over 0.6 s inside a phrase shrink to 0.4 s. This
     matches a hand edit made earlier (raw-gpt.mp4: 73 s against the hand edit's
     71 s; the same speech is kept).
   - **Thong thả**: the original pacing, with 0.12 s around the detected phrase
     edges (which start ~0.15 s before the voice) and pauses left as they are
     (raw-gpt.mp4: 86 s).

Results are cached per file and per engine in `cache/`, so re-running the same
clip costs nothing. Jobs live in `jobs/<id>/`, and the source clip is copied there
untouched.

## Command line (no browser)

`scripts/roughcut_cli.py` runs the same pipeline with the local engine only (no Vbee).
The `cat-tho-talking-head` and `cat-tho-huong-dan` skills drive it.

```bash
.venv/bin/python scripts/roughcut_cli.py analyze <video> --mode intro|tutorial [--aliases FILE]
.venv/bin/python scripts/roughcut_cli.py realias <job> --aliases FILE
.venv/bin/python scripts/roughcut_cli.py export <job> [--edits FILE] [--pace fast|relaxed] [--no-ff] [--out PATH]
```

`analyze` symlinks the source into the job (`--copy` to copy it) and writes
`jobs/<id>/review.txt`. `--edits` is JSON `{"<island>": true|false}`, the same shape
the review screen sends. CLI jobs show up in the web app's recent list.

## Requirements

- ffmpeg-full (`brew install ffmpeg-full`). The app finds the keg-only build on its own.
- Python dependencies via `uv sync` (already done).

## How it decides

See `roughcut/decide.py`:

- **FILLER / SHORT** — the island has no recognised words, only filler words,
  or lasts under 0.3 s.
Words are compared on content words: và/thì/là/cái are ignored, and the
names in your list are mapped first.

- **STRAY** — an island with at most one content word ("chưa", "đúng").
- **RESTART** — inside one island the speaker restarts. A phrase repeats: 2+
  words at the start, or 3+ words anywhere, within 15 words. The abandoned part
  is cut at its pauses.
- **STUTTER** — the same word twice with a pause between ("có có").
- **RETAKE** ("last take wins") — a later island within 60 s opens like this
  one. A short take that trails off counts too ("cái skill của họ làm cho
  các…"), and so does a later island within 30 s that re-says the second half
  of this one. The re-said part and everything in between are dropped. A
  parallel sentence ("…clip của họ…, còn clip của bạn…") is not a retake: the
  repeated part must match the later island by at least 70 %. Exception: if
  the later take stutters and the earlier one was complete, the earlier one is
  kept.
- **TAIL_OVERLAP** — a kept island ends with the words the next kept island
  starts with. Those words are trimmed.
- **Rephrased retake** — the next kept sentence (within 30 s) says the same
  thing in other words: both have at least 5 content words, and at least 70 %
  of the shorter one's content words appear in the other, in order. The
  earlier sentence is dropped.
- **Restart details** — a word broken off and said again ("để chạy s… để chạy
  skill"); a whole clause restarted ("và cũng là do… và do…": the cut starts at
  the first "và"); a repeat said back to back one word into a phrase ("ok cũng
  là cũng là…"). The same two words far apart, as in "để các bạn … mà các bạn
  còn", stay.
- **Leftover** — after the cuts, at most 2 words remain and they open the next
  kept sentence: the rest of the island is dropped.
- **FILLER inside a phrase** ("Máy này" only) — the local engine hears
  "ờ/ừm/à" and times every word. A filler word is cut when a pause sits right
  before and after it. With no pause around it, nothing is cut.
- **PROBE** (Vbee only) — a short first or last piece of a kept phrase, set off
  by a pause, is often "à" or a throat sound. Vbee hears the piece alone. The
  piece is cut when Vbee hears nothing, only a filler, or words that are said
  again right after it. Expect about 6 extra calls for a 10-minute clip.

With "Máy này", cut edges come from measured word times (shifted 0.15 s, the
model's measured lead) and snap to the pause that ends at the word. Restarts
and stutters are found on the text without fillers ("có ờm có cấu trúc"). A
short take of at most 5 words counts as abandoned when its first two words
match the next, longer take, even if a tone or one letter differs ("go
Claude" → "gói Claude đã gần…").

Silence thresholds adapt to the room's noise floor, starting at -40 dB and going higher in noisy rooms. If the speaker breathes between every few words, the minimum pause grows so that each Vbee call covers about one sentence.

Every cut lands inside a measured pause. Padding never reaches into
neighbouring speech.

## Limits

- A repetition you meant to say (anaphora within 60 s) gets dropped. Use the
  review screen to keep it.
- A filler or stumble glued inside a sentence with no pause around it ("chưa"
  in "…đẹp chưa đủ…") cannot be found. Vbee has no per-word timestamps. Use ✂
  in the review if there is a pause around it.
- Word labels in the ✂ editor are approximate (word times from "Máy này", or
  estimates for Vbee). The cut points themselves are measured pauses.
- "Máy này" hears English words in Vietnamese spelling ("skill" → "seo/sko").
  Keep the name list up to date, or two takes of the same sentence may not be
  recognised as one.
- The app is built for one speaker and one clip per job.
