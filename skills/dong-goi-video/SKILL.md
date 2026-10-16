---
name: dong-goi-video
description: Packaging pass for an already rough-cut talking-head video. Adds burned-in captions (UPPERCASE, yellow keywords), motion-graphics cards that illustrate what is being said (built in parallel by sub-agents with PIL), punch-in zooms that hide jump cuts, synthesized sound effects tied to on-screen motion, an end stinger, and a loudness-mastered final render. Use this skill whenever the user wants to "thêm hiệu ứng", "thêm phụ đề và motion graphic", "làm video sinh động hơn", "đóng gói video", add subtitles + effects + SFX, or make a cut YouTube / social talking-head video look professionally edited, even if they only say "edit tiếp cho đẹp" after a rough cut. The rough cut itself (removing silences/retakes) is the job of cat-tho-talking-head; this one starts from its _roughcut.mp4, from a video-use edl.json, or from any already-cut mp4.
---

# Đóng gói video: packaging a rough cut

Turn a rough-cut talking head into a lively, readable video:
- captions with highlighted keywords,
- one motion-graphics card per idea on the empty side of the frame,
- framing changes at the jump cuts,
- a small, deliberate set of sound effects,
- an end stinger,
- a final render at -14 LUFS.

Everything visual is drawn in code (PIL to ProRes alpha), so there is no template lock-in, and
each card is built for the words it illustrates.

The user asked for three things that are the soul of this skill:
- **Cards fade out slowly.** They never pop off.
- **Cards stay long enough to be read.**
- **The video is visual.** Use icons, motion and diagrams instead of walls of text.

Most rules below exist because one of those three broke in a real render.

## Environment

- Python with numpy, scipy, Pillow, fontTools: use `PY=~/skill-edit-video/engine/.venv/bin/python`
  (the system python3 lacks the deps). If it is missing, run `bash ~/skill-edit-video/install.sh`.
- `whisper-cli` (whisper.cpp) and the model `ggml-large-v3-turbo.bin` for word timing. install.sh puts
  the model in `~/skill-edit-video/engine/models/whisper/`; `words_asr.py` finds it there.
- ffmpeg with libass (the `subtitles` filter) and zscale. On this machine prefix every command with
  `PATH=/opt/homebrew/opt/ffmpeg-full/bin:$PATH`. The slim ffmpeg has no `subtitles` filter.
- Scripts live in this skill's `scripts/` folder. Call them by absolute path. They write into the
  project's edit dir (`<videos_dir>/edit/`), never into the skill folder.
- Read `<edit>/project.md` first if it exists, and summarize the last session in one sentence.

## The process

### 1. Inventory: segments and audio envelope

You need the cut timeline as segments (one per jump cut) and the text that is said in each one.

- **From a cat-tho-talking-head result**: use the mp4 mode below on `<stem>_roughcut.mp4`.
- **From a video-use EDL** (best when there is one): `segments.py --edit-dir E --edl E/edl.json [--tail-end T]`.
  Compose renders straight from the sources, so zoom can change per range.
  - `--tail-end` extends the last range past the final word, for an outro of ~1 s of real footage.
- **From an already-cut mp4**: `segments.py --edit-dir E --video cut.mp4`. Jump cuts are detected
  from frame-difference spikes. Check the printed list against a contact sheet; pass `--cuts t1,t2`
  if detection is off.

`segments.py` writes:
- `segments.json` (all boundaries on the 30 fps grid),
- `rms_out.npy`, a 10 ms loudness envelope of the cut, used for caption timing.

In mp4 mode it also prints near misses. Look at those frames: one real cut measured only ~2.6x its
neighbours.

**Word timing (do this before writing any card spec):** run `words_asr.py --edit-dir E`. It uses
whisper.cpp with DTW token timestamps on the cut audio and writes `words_asr.json`, the onset of
every spoken word on the output timeline (±0.1–0.2 s).
- Card landings, SFX hits and captions all hang on these times.
- Utterance-level ASR such as Vbee cannot give them. Interpolating over the audio drifted up to
  0.75 s in a test, and plain whisper word times (without DTW) ran 0.3–0.9 s early.
- Use the ASR only for timing. Caption text comes from your corrected transcript.

**Text:** use the EDL `quote`s or the cached transcript. If no transcript exists, transcribe with
whatever ASR the project uses (video-use notes say which). Fix the ASR's misspellings of names
and products before they reach captions (e.g. "cloud code" → Claude Code, "code s" → Codex,
"prom" → prompt, "mười lăm không" → 15.000).

### 2. Where cards can live, and the face anchor

Run `safe_box.py --edit-dir E --video <cut or preview> --box x,y,w,h` and LOOK at
`verify/safe_box.png`. The box must stay clear of face, hair and gesturing hands in every tile.
Leave margin, because punch-ins push the person outward.

- Typical result: the empty wall on one side, ~680x600 px.
- The script also saves `verify/bg_ref.png` for the card agents' check frames.
- Pass `--ref-time` to pick a wide, typical take for `bg_ref.png`; mid-clip may be a close take.
- Note the point to keep fixed while zooming: the eyes / forehead (x, y in 1920x1080 coordinates).
  It becomes `zoom_anchor`.
  - An anchor at the face centre cropped the hair at 1.12–1.16.
  - If the speaker sits differently in some take, give that segment its own anchor:
    `{"z": 1.16, "anchor": [x, y]}`.

### 3. Plan and confirm (do not build before the user agrees)

Map ideas to cards. Read `references/card_catalog.md`: it has ten proven patterns (reference to a
previous video, a number counting up, comments, a question, a pipeline, "made with", a
limitation, a gift/bonus, an agenda checklist, an end stinger) with their timing skeletons.

Show the user one table: time | what is being said | what the card shows. Under it, add:
- **Caption style:** 2–5 word UPPERCASE chunks, yellow keywords, bottom centre.
- **Zoom plan.**
- **SFX approach:** each effect tied to a visible landing, quieter than the voice.
- **The ending.**

Ask whether they want a music bed. Prefer their own track, because synthesized music sounds cheap.

Planning rules that came from real mistakes:
- **One card per idea, about 5–9 s each, placed on the empty side.** Cards must not appear back to back.
  - Vary the format so it does not become "the same dark box in the same corner" every time:
    a lower band, a full-frame beat, a spotlight / picture-in-picture product reveal
    (see the ideas at the end of `card_catalog.md`).
  - A card's 0.9 s exit must finish ≥ 0.35 s before the next card starts.
  - Otherwise two dark boxes in the same place read as one box blinking.
- **Content lands ON the word.** Every element's landing time is 0.1–0.2 s before the word it
  illustrates; take the word times from `words.json` (step 4). Content that arrives after the
  narration has moved on reads as lag.
- **No empty cards, no long loading screens.** The panel arrives with its header or icon. Faint
  stubs or outlines may reserve space for later content, but for ≤ ~1.5 s. If the next content
  lands later than that, start the card later or show something real first. A critic read a
  4.6 s placeholder as "unfinished".
- **Hold ≥ 0.8 s after the last element lands** before the exit begins.
- **Fill long gaps.** A card-free stretch of ~5–8 s is fine when a slow push-in carries it. When it
  is longer and the speaker explains something concrete (a limitation, a before/after), give it a card.
- **Honest content.** No invented quotes, names, review text or fake screenshots. Comments are
  abstract (an avatar plus gray bars). Use no logos.
  - If real screenshots would be better (comments, a dashboard, a product UI), say so and ask
    the user for them.
- **The stinger uses the speaker's own words** and must not cover the mouth or eyes.
  - Measure the chin line in the stinger's segment as it will be FRAMED (after its zoom).
  - Put the band below it. Do not assume y≈800: one speaker sat so low that y≈800 was his mouth.
  - If there is no room under the chin, drop that segment's punch-in or move the stinger into the empty side area.
  - Captions keep running under the stinger, and the band must end above the caption line
    (~y 900), unless the stinger headline IS the remaining spoken words (then use `--stop-at`).
  - In a test, captions were stopped under a stinger that showed other keywords, and 2.7 s of
    speech went uncaptioned.
- **Do not fade to black** when the clip is an intro that hands off to the main content.
  - End about 1 s after the last word, on real footage. With an EDL, extend it via `--tail-end`.
  - A cut mp4 may end 0.2 s after the last word. Then land the stinger on the key word and let it
    ride to the end; do not freeze frames to fake a tail.

### 4. Captions

1. Write `E/chunks.json` (format in the `scripts/captions.py` docstring):
   - one group per segment (`"seg": i`), chunks UPPERCASE with 2–5 words,
   - `*keyword*` for the 1–2 words per sentence that carry the meaning,
   - `weights` for foreign words whose syllable count differs from their letters (ChatGPT=4).
2. Run `extract_font.py E/fonts` once. libass ignores face names inside a .ttc and silently falls
   back to regular Helvetica Neue; this writes a standalone "VU Cond Black".
3. Run `captions.py --edit-dir E --chunks E/chunks.json --words E/words_asr.json`. Add
   `--stop-at <stinger start>` only when the stinger repeats the last spoken words.
   It aligns your corrected caption tokens to the ASR words and should match ≥ 85%. Merge any
   chunk it reports as SHORT (< 0.45 s flashes).

It also writes `words.json`, the start time of every caption token. Use it to time cards and SFX.
Without `--words`, it falls back to interpolating over voiced audio (expect ±0.2–0.7 s).

### 5. Cards: one sub-agent per card, all spawned in ONE message

1. Copy `references/brief_common.md` to `E/animations/BRIEF_COMMON.md` and fill its placeholders
   (video description, safe box, python and ffmpeg paths, bg_ref path).
2. For each card, write `E/animations/<slot>/SPEC.md`, modelled on the catalog entries:
   - duration,
   - exit fade (the last 0.90 s),
   - the narration line,
   - each element's LANDING time (seconds from slot start), derived as `word_time - 0.15 - slot_start`,
   - which frames to check.
3. Spawn all card agents in parallel (`general-purpose`, run in the background), one Agent call
   per card, all in the same message. If your harness cannot spawn sub-agents (e.g. Codex), build
   the cards yourself one by one, following the same BRIEF_COMMON.md + SPEC.md. The prompt is short and self-contained: the slot dir, and
   "read BRIEF_COMMON.md, then SPEC.md, build it, verify it, report it, and do not ask questions".
4. As each agent reports, open one or two of its `check_*.png` files yourself. Things to catch:
   - text over the face, a stinger over the eyes,
   - an overloaded or empty card,
   - broken diacritics.

   Send fixes with SendMessage to the same agent, which keeps its context.
5. Record each card's reported landing times. The SFX cues come from them.

### 6. Sound effects

Run `make_sfx.py E/sfx` once. It synthesizes:
- `swoosh_soft`, `whoosh`, `pop`, `tick`, `bloop`, `ding`, `thud`, `sparkle`, `buzz`, `riser`, `impact`
  (48 kHz, peak -3 dBFS).

Write `E/sfx_cues.json` as `[[name, hit_time_on_output, gain_db], ...]`. Generating it from a
small Python file that adds the slot start to each landing time keeps it editable. Compose aligns
each file's loudest sample to the hit time, so a riser + impact lands on the slam frame.

A back-eased stamp or pop (ease_out_back) visually lands ~0.1 s before its nominal landing time,
when it first reaches full size. Put its hit 0.1 s earlier than the reported landing.

Taste that held up:
- `swoosh_soft` -24 dB as each card settles (+0.22 s).
- `pop` -26…-30 for elements, `ding` -22 for a key landing (counter reaches its number, final ✓).
- `thud` -20 for a stamp or badge, `bloop` -24 for bubbles, `sparkle` -22…-32 for bursts.
- `buzz` -27 for ✕, `riser` -26 + `impact` -19 for the stinger.

Keep it sparse: a counter gets 3–4 thinning ticks, not 11; a row of avatars gets 2 pops, not 5.
Cards exiting make no sound. Roughly 1 cue per second of video is plenty.

### 7. Compose, self-check, critic, final

Write `E/package.json` (format in the `scripts/compose.py` docstring):
- segments, zooms, zoom_anchor, overlays `[file, start]`, safe_box, captions, fonts_dir, sfx_cues, sfx_dir.
- Mark the stinger `[file, start, {"full_frame": true}]` so `qc.py` checks it by eye, not in the card box.

**Zoom plan:** change framing only where the take changes.
- Cuts inside one take (a pause removed) keep the same framing.
- Use 1.12 for a normal punch-in and 1.16–1.18 for emotional beats and the ending.
- Use `["push", 1.0, 1.06]` for a card-free stretch.
- Strict wide/tight alternation on every cut reads as a metronome.

Then:
1. `compose.py E/package.json --preview` (fast x264). It warns if the video frame count differs
   from the plan. Then run `qc.py E/package.json E/preview.mp4` and check:
   - stream durations equal the segment total,
   - every card entrance says `smooth`. A `JUDDER` line means a repeated frame; the compose
     frame clock should prevent it, so investigate.
   - no `LOUD SFX` lines (an effect louder than speech p90),
   - LOOK at `verify/qc_sheet.png`.
2. Send the preview to the user while the critic runs.
3. Spawn one critic sub-agent to roast the preview. Give it:
   - the video path, the card schedule and the cue list,
   - the user's three requirements,
   - "verdict, ranked problems with timecodes + evidence, 5 fixes first".

   Verify each critic claim before acting. Measure it, because critics also invent problems.
   Fix with SendMessage to the card agents (retime via a `SPEC_v2.md`) and edits to package.json / cues.
4. Run `compose.py E/package.json` for the final (x264 slow, CRF 17), re-run `qc.py`, and send `final.mp4`.
5. You cannot listen. Report loudness as numbers (integrated LUFS, true peak, SFX level vs speech)
   and say that you have measured it, not heard it.

### 8. Persist

Append a session to `E/project.md` with:
- the strategy,
- the card schedule with output times,
- the decisions and why,
- what the critic found and what changed,
- what is still the user's call (real screenshots, music, caption timing precision).

## Hard rules (each one broke a real render)

1. **Captions are the LAST video filter**, after every overlay. Otherwise cards cover them.
2. **One integer frame clock.** Put every stream on it: `settb=1/30,setpts=N` (overlays `+start_frame`).
   With `setpts=PTS-STARTPTS+T/TB` across mixed timebases (source 1/600, ProRes 1/15360), 3 of 9
   cards repeated every 3rd frame, while the overlay files themselves were smooth. `compose.py`
   does this; keep it if you edit.
3. **Render from the sources via segments, not from a concat-demuxer rough-cut file.**
   - AAC priming and timestamp drift accumulate per segment in a `-c copy` concat.
   - Every segment is converted to CFR and trimmed by frame index, so audio length = frames × sr / fps exactly.
   - This matters for variable-frame-rate phone footage: a time-based trim lost a frame there.
4. **30 ms audio fades at every segment boundary**, otherwise every cut pops.
5. **Loudness: compressor → static gain to target → alimiter.** `loudnorm` silently switches to
   dynamic mode on speech (peak-to-loudness ≈ 18 dB) and pumps SFX-only moments.
6. **Fonts:**
   - Captions use the extracted "VU Cond Black" via `fontsdir`.
   - Cards use Helvetica Neue Condensed Black (TTC index 9) and Avenir Next Demi Bold (index 2).
   - Never use Avenir Next Heavy Italic, which is missing Vietnamese glyphs.
7. **Card exits are 0.9 s with gaps between cards.** A 0.6 s ease exit is visible for only ~0.4 s
   and reads as a blink.
8. **SPEC times are landing times.** Agents read bare times as start times and land everything
   0.35 s late, so always say "lands at".
9. **Verify sub-agent claims.**
   - Agents report "all checks pass"; open a check frame and run `qc.py` yourself.
   - Only one agent may write a given slot dir at a time.

## Scripts

| script | what it does |
|---|---|
| `scripts/segments.py` | EDL or cut mp4 → `segments.json` + `rms_out.npy` (jump-cut detection in mp4 mode) |
| `scripts/words_asr.py` | whisper.cpp + DTW → `words_asr.json`, the word onsets on the output timeline |
| `scripts/safe_box.py` | candidate card box drawn over frames sampled across the cut → `verify/safe_box.png`, plus `bg_ref.png` |
| `scripts/extract_font.py` | Helvetica Neue Condensed Black → `fonts/VUCondBlack.ttf` for libass |
| `scripts/captions.py` | `chunks.json` → `captions.ass`, `captions_timing.json`, `words.json` |
| `scripts/make_sfx.py` | synthesizes the 11-sound SFX library into a folder |
| `scripts/compose.py` | `package.json` → preview/final mp4 (zoom, overlays, captions last, SFX, mastering) |
| `scripts/person_mask.py` | Apple Vision person matte of the framed footage (from `compose.py --base`) → `mask.mp4`, so text overlays flagged `behind` sit behind the speaker |
| `scripts/qc.py` | durations, card-motion judder, SFX loudness vs speech, contact sheet |

References:
- `references/card_catalog.md`: the ten card patterns with timing skeletons. Read it at step 3.
- `references/brief_common.md`: the template for the card agents' common brief. Use it at step 5.
- `references/style_kinetic_podcast.md`: an alternative look. It has a cold open, two-tier
  captions with big kinetic words beside the head, headline cutaways, flash/zoom-blur
  transitions and a dark grade. Read it when the user wants a "podcast / cinematic / DOAC-like"
  style instead of cards, or points at a reference video in that style.
