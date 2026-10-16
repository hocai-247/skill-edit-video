# Style preset: "kinetic podcast cold open" (studied 2026-10-13)

Learned from the first 2 minutes of a big interview-podcast episode (measured frame by frame:
2862 frames, 142 cuts). Use it when the user asks for a cinematic, high-retention, podcast-like
look instead of the card style. Copy the TECHNIQUES only. Never copy the reference's footage,
logos, branding or text.

## Structure
- **Cold open, then a breath.** The first ~100 s of the reference is a montage of the episode's
  strongest lines:
  - shots last 0.6–3 s,
  - bursts of 2–3-frame cuts appear at transitions,
  - then 2.5 s of black,
  - then the episode starts calmly (8–9 s shots, no graphics).
- For a short intro, scale it down to 8–10 s: 3–4 of the strongest lines (a number, the central
  question, the most surprising claim), then a 1.2 s black beat with a small title and an
  impact, then the normal intro.
- Pick cold-open cut points by listening to the energy envelope, not the ASR alone. A cut
  1 syllable early leaves "…hỏi" before "liệu". Verify with `words_asr.py` that the first word
  of each cold-open clip is the intended one.

## Text: two tiers
- **Ordinary lines:** small, clean, sentence-case subtitles at the bottom, white with a soft
  shadow, no box (here Avenir Next Demi Bold 54 px).
- **Punch lines:** the subtitle gives way to BIG kinetic words beside the head, in the negative
  space and not at the bottom.
  - Each word pops in on its own spoken time.
  - Layout is stacked and mixed-size: small connector words above, then one huge keyword.
  - Brand or product words are red italic; promises or gifts are gold; everything else is white.
  - A soft dark scrim behind the block keeps it readable on a light wall.
  - Leading must leave room for Vietnamese stacked capital marks: centre-to-centre ≈
    0.36·upper + 0.66·lower + 6 px.
- **Emotional beat:** a tight close-up (1.3x+, anchor moved so the face sits off-centre) with
  ONE lowercase word, shrink-to-fit, and no subtitle for that shot.
- Hold big text ≥ 1.4 s after its last word, even across a jump cut. In the cold open, each
  hook ends when the next one starts (fast on purpose).

## Cutaways and transitions
- **Headline cutaways:** full-frame "photographed screen" plates (paper + scanlines,
  push-in 1.0→1.09, slight tilt, edge blur, vignette), a purple marker behind the number or
  keyword, and 2–3 cards cut in a burst. Add a dark bottom band so the white subtitle stays
  readable on the plate. Content must be the speaker's own claims, never a fake news masthead.
- **Transitions:** a white flash (bloom) on big structural cuts and on entering a cutaway; a
  zoom-blur (`whip_in`) on cold-open cuts and out of the black beat. Elsewhere, hard cuts.
- **Grade:** darker and moodier, keeping skin natural:
  `eq=contrast=1.12:brightness=-0.05:saturation=0.88,curves=master='0/0 0.25/0.18 0.75/0.78 1/0.96',vignette=PI/4.2`.
  A stronger version (contrast 1.18, colorbalance) made the face muddy.

## Fonts (Vietnamese)
- Avenir Next Heavy is missing 47 Vietnamese capitals, so do not use it.
- Avenir Next Bold and Bold Italic (TTC 0/1) and Demi Bold (2) cover everything.
- Menlo covers ✓ › → and Vietnamese, which suits terminal plates.

## Reference implementation
The project `16.edit-video-gpt/edit/v2/`:
- `v2_build.py` (text plan + subtitle ASS),
- `v2_gfx.py` (hooks, singles, plates, flash, title as ProRes alpha),
- `v2_sfx.py`,
- `package.json` (compose.py with `grade` and `whip_in`).

## Text behind the speaker (depth), added 2026-10-16
The user wants big text that comes near the face to sit BEHIND them, as if it were on the wall
behind their back, never on top of the face.
1. Run `compose.py package.json --base`. It renders the framed footage only (zoom + grade, no
   graphics) to `_compose/base.mp4`.
2. Run `person_mask.py _compose/base.mp4 mask.mp4 accurate`. It uses Apple Vision person
   segmentation (Swift, built into macOS, no download), gives a clean hair edge, runs ~12 fps on
   an M-series Mac, and lightly smooths in time.
3. Flag the text overlays `{"behind": true}` and set `"person_mask": "mask.mp4"` in
   package.json. Compose multiplies their alpha by (1 − matte).
4. **Placement:** tuck only the block's LEFT EDGE (~40 px) behind the silhouette. Measure the
   person's right edge in the text rows over each hook's window from the mask (95th percentile)
   and start the block there − 40 px (`v3_place.py` in the reference project).
   - Tucking deeper hid the first letters of key words ("ất vui", "ẶNG CÁC BẠN"), which is
     unreadable.
   - Re-run the mask whenever framing or zoom changes; the matte must come from the same framed
     footage.
