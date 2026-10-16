# Card agent brief — template

Copy this file to `<edit>/animations/BRIEF_COMMON.md`, fill every `{{…}}`, and adapt the video
description and palette to the project. Every card agent reads it plus its own `SPEC.md`.

---

# Common spec for every animation slot (read fully before starting)

Video: {{one paragraph: who is speaking, about what, language, where the person sits in frame,
where the empty area is}}.

## Canvas / placement
- Output frame 1920x1080, 30 fps, RGBA, FULLY TRANSPARENT except the card.
- The card and everything in it stay inside the SAFE BOX x {{X0}}..{{X1}}, y {{Y0}}..{{Y1}}.
  Do not draw outside it, because the face and the captions are elsewhere. A full-frame slot
  (the end stinger) has its own rule in its SPEC.
- Exact frame count = round(duration * 30). Frame k shows time t = k / 30 s from the slot start.

## Card look: visual first (icons, shapes, motion), little text
- Card panel: rounded rect with radius 28. Fill (22,22,28) at alpha 235. Border 2 px (255,255,255,28).
  Soft drop shadow (black, alpha ~110, gaussian blur 22, offset +10 y), feathered so it never
  reaches the safe-box edge. Inner padding ~36 px.
- Accents: Yellow #FFD400 for emphasis, Green #2BD45B for good/done, Red #FF4757 for hearts,
  play buttons and ✕ only, plus White and dim gray #8A8A93. At most 2 accent colours at once.
  Keep ~35% empty space.
- Draw every icon with PIL vector shapes. Supersample 3x and downscale with LANCZOS. Do not use:
  - emoji or font-glyph icons
  - logos (OpenAI, Anthropic, YouTube…) or copies of a brand's UI
  - real names or invented quotes. Comments are abstract: an avatar circle plus gray "text" bars.
- Text sizes (phone readability): headline ≥ 58 px, secondary text and labels ≥ 40 px, nothing < 36 px.

## Fonts (Vietnamese diacritics — DO NOT substitute)
- Headlines: `/System/Library/Fonts/HelveticaNeue.ttc` index 9 (Helvetica Neue Condensed Black), UPPERCASE.
  For an optional slant, put the text on its own RGBA layer, pad it by ceil(k*h) px, then apply
  `layer.transform(layer.size, Image.AFFINE, (1, k, -k*layer.height, 0, 1, 0), resample=Image.BICUBIC)` with k = 0.12.
- Body and labels: `/System/Library/Fonts/Avenir Next.ttc` index 2 (Avenir Next Demi Bold).
- Do not use Avenir Next Heavy Italic (it is missing Vietnamese glyphs) or PIL's default font.
- Centre text on the FULL string width, never on a partially revealed string.
- In the check frames, confirm that every diacritic is drawn (ư ơ ă â ê ô đ and the tone marks).
  A slight gap after Ư in this font is normal.

## Motion (non-negotiable; the viewer must be able to read every card)
- SPEC times are LANDING times: the moment an element is FULLY in. Each element starts its
  entrance 0.30–0.35 s earlier, so it lands on (or 0.1–0.2 s before) the word that it illustrates.
- CARD ENTRANCE at t = 0: 0.40 s ease_out_cubic, opacity 0→1, slide up 40 px, scale 0.96→1.
  The card must never look empty. Its first content (header or icon) arrives with the panel,
  and placeholders (faint stubs or outlines) reserve the space for later content.
- CARD EXIT: the LAST 0.90 s of the slot. The whole card fades opacity 1→0 with ease_in_out_cubic
  and drifts up 12 px. The last frame must be fully transparent. The card must not pop off or cut.
- Inner elements enter one at a time over 0.30–0.35 s each (ease_out_cubic, fade plus a 20–40 px slide).
  Stamps and badges take 0.25 s with ease_out_back from 130%.
- Once an element is in, it stays until the card exits. The only exception is a replacement the
  SPEC asks for, which cross-fades over ≥ 0.35 s.
- Easings (use exactly these, never linear):
  ```python
  def ease_out_cubic(t): return 1 - (1 - t) ** 3
  def ease_in_out_cubic(t): return 4*t**3 if t < 0.5 else 1 - (-2*t + 2)**3 / 2
  def ease_out_back(t, s=1.7): t -= 1; return 1 + (s + 1)*t**3 + s*t**2
  ```
- A gentle idle motion while the card holds is welcome, e.g. an icon breathing 1.00↔1.03 over 2 s.

## Technical
- Python: `{{PYTHON}}` (PIL and numpy). ffmpeg: `{{FFMPEG}}`.
- Render RGBA PNG frames to `<slot_dir>/frames/f_%04d.png`, then:
  `ffmpeg -y -framerate 30 -i frames/f_%04d.png -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le -r 30 render.mov`
  (ffprobe will report yuva444p12le; that is normal.)
- Speed: render the card on a small RGBA canvas and paste it into the transparent 1920x1080 frame.
  Pre-render static layers once.
- Write ONLY inside your slot directory. Delete `frames/` after `render.mov` is verified.

## Deliverable checklist (do all of it, then report)
1. `<slot_dir>/make.py`, self-contained.
2. `<slot_dir>/render.mov`.
3. ffprobe: width, height, fps and nb_frames must equal the spec.
4. Assert in code:
   - alpha is 0 outside the safe box (except a faint shadow ≤ 6);
   - the last frame's alpha is all 0 (except the stinger).
5. Check frames: composite onto `{{BG_REF}}` at t=0.2, at each landing time, and at duration−0.3.
   Save them as `check_<t>.png` and LOOK at them. Fix any clipping, overlap, unreadable text or
   broken diacritics.
6. Report: path, ffprobe numbers, the time (s from slot start) each element LANDS, and the moments that deserve a sound effect.

Do not ask questions. If something is ambiguous, pick the most obvious interpretation and proceed.
