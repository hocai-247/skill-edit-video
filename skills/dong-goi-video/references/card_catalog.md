# Card catalog — proven patterns

These are the cards that shipped in a 72 s Vietnamese talking-head intro (2026-10-10). Treat them
as worked examples: match the pattern to what is being SAID and invent new ones when nothing
fits. Specs are written in LANDING times (s from slot start). The slot start is chosen so the
first content lands just before its word.

Each entry: **when the speaker says…** → what the card shows → timing skeleton.

## 1. Reference to a previous video / earlier work
"cảm ơn mọi người đã xem video hướng dẫn X…" → a pill label "VIDEO TRƯỚC" with a play icon, then a
16:9 "thumbnail" tile containing:
- a drawn motif of the topic (film strip + scissors for editing),
- the title in yellow slanted Condensed Black and the tool name in white,
- a red play button and a full red progress bar ("watched").

Timing: pill 0.55 → tile 1.20. The headline pulses (1→1.08→1) on the title word, then a yellow
underline sweeps under the tool name. 7.1 s.

## 2. A number (views, users, money, %)
"video đã có hơn 15.000 lượt xem… đón nhận nhiều nhất" → an eye icon plus a counter that counts
up with ease_out to the exact number (Vietnamese thousands separator is a DOT: 15.000). Then
a "+" stamp and a label below it.
- Second beat: a mini bar chart grows (5 bars, the last one tallest and yellow), and a green
  badge "#1 TRÊN KÊNH" stamps above it.
- Draw faint bar stubs from the start so the lower half never looks empty.
- Keep the counter right-anchored with fixed-width digits so it does not jitter.

Timing: count 0.40→1.60 (lands on the number), "+" 1.85, bars 2.55→3.45, badge 4.20. 6.2 s.

## 3. Comments / audience reaction
"mình đã đọc tất cả bình luận, từ lời động viên đến góp ý… rất vui" → a speech-bubble header,
then 3 abstract comment bubbles (avatar circle + 2 gray bars, no text, no names):
- the 2nd bubble carries a green tag "ĐỘNG VIÊN" with a heart,
- the 3rd bubble carries a yellow tag "GÓP Ý" with a lightbulb,
- on "rất vui", a big red heart pops and a fan of small hearts bursts upward.

Timing: bubbles 0.70 / 1.85 / 3.10, heart 3.90. 6.8 s.

## 4. A question the video will answer
"liệu ChatGPT có làm được tương tự không?"
- State A: a row of 5 generic avatars pops in, then "NHIỀU BẠN DÙNG CHATGPT".
- State B replaces it with a 0.35 s cross-fade: a huge yellow "?" pops, then "CHATGPT" and
  "LÀM ĐƯỢC KHÔNG?" ("KHÔNG?" in yellow). The "?" wobbles ±4° until exit.

Timing: avatars 0.40–1.16, label 1.50, cross-fade 2.75→3.10, "?" 3.10, lines 3.45 / 4.30. 7.4 s.

## 5. A pipeline / how-it-works (A → B → C)
"dùng Codex của ChatGPT để chạy skill edit video tự động" → a small header, then 3 stacked node
boxes, each with a drawn icon:
- terminal ">_" for the tool,
- clapper for the skill,
- lightning bolt for the result.

Arrows draw themselves downward between the nodes. The last node stamps in green with one glow pulse.

Timing: node1 0.60, arrow 0.80→1.20, node2 2.75, arrow 3.10→3.50, node3 3.90. 5.9 s.

## 6. Meta / "this very video was made with…"
"phần mở đầu video này được làm bằng skill X để cắt thô và thêm hiệu ứng" → a header with a
blinking REC dot, then a mini editor timeline (7 clip blocks, 3 tinted red as bad takes, with a
moving playhead):
- pills show the tool names,
- scissors sweep the track, the red blocks collapse and the gaps close, and a "CẮT THÔ" tag appears,
- sparkles twinkle on the clips and a "HIỆU ỨNG" tag appears.

Timing: timeline 0.95, pills 2.00 / 3.75, cut 4.50→4.95, sparkles 5.60. 7.5 s.

## 7. Done / not done / constraint (a confession or limitation)
"video trước tập trung cắt thô, thời gian có hạn, chưa tinh chỉnh prompt hiệu ứng" → header
"VIDEO TRƯỚC", then 3 rows, each a round badge plus text:
- a green ✓ badge with "CẮT THÔ" and a "TẬP TRUNG" pill,
- a yellow clock badge (the minute hand sweeps once) with "THỜI GIAN CÓ HẠN",
- a red ✕ badge that shakes, with "PROMPT HIỆU ỨNG" and a gray "CHƯA TINH CHỈNH KỸ" under it.

Use it to fill a long card-free stretch where the speaker explains a limitation. 7.5 s.

## 8. A promise / gift / bonus
"cuối video mình sẽ tặng bộ prompt để thêm phụ đề và tạo hiệu ứng… chuyên nghiệp hơn" → a drawn
gift box bounces in, then the header "QUÀ / CUỐI VIDEO". On "tặng":
- the lid pops open with a sparkle burst,
- a document "BỘ PROMPT" rises out of the box,
- the chips "PHỤ ĐỀ" (green, CC icon) and "HIỆU ỨNG" (yellow, sparkle) land,
- 5 stars fill on "chuyên nghiệp".

Timing: header 1.05, lid 2.70, doc 3.55, chips 4.40 / 5.50, stars 6.83→7.15. 8.8 s.

## 9. Agenda / what you'll get (checklist)
"mình sẽ làm trực tiếp từng bước, vướng đâu sửa đó, để các bạn biết cách khắc phục" → header
"VIDEO HÔM NAY" with a yellow underline, then 3 checkbox rows. Each row slides in and a green
check draws itself in the box. A dashed placeholder reserves the space for a row that comes later.

Timing: rows 0.40 / 1.15 / 6.30 (each landing on its phrase). 8.2 s.

## 10. End stinger (full frame)
"ok chúng ta cùng bắt đầu nhé" → a dark feathered band across the CHEST (centre y≈800, never
over the eyes), with the headline slamming in from 140%. The headline uses the speaker's own
words ("CÙNG BẮT ĐẦU NHÉ!"): yellow Condensed Black ~190 px with an 8 px black outline. A thin
shockwave ring plays at the landing, then the headline breathes.
- It does not fade out by itself.
- Captions are dropped under it (`--stop-at`) ONLY when the headline is the speaker's own last words.
  If speech continues with other words, keep the captions and end the band above them.
- The clip ends ~1 s after the last word on real footage. There is no fade to black when an
  intro hands off to the main content.

Timing: headline lands 0.87 on the key word. 2.6 s. Riser + impact on the landing.

## Layout of the timeline
- Gaps: a card's 0.9 s exit must finish ≥ 0.35 s before the next card starts. Two dark cards in
  the same spot with a 0.1 s gap read as one box blinking.
- After the last element lands, hold ≥ 0.8 s before the exit starts.
- Plan one card per idea. A 5–9 s stretch with no card is fine if a slow push-in carries it.
  If it is longer than ~8 s and the speaker is explaining something concrete, give it a card
  (pattern 7 was born from this).

## Ideas worth borrowing (seen in a no-skill test run; not built into the scripts yet)
- **Spotlight product reveal:** when the product or hero name is spoken, the whole frame shrinks
  into a rounded picture-in-picture on one side, over a blurred, darkened copy of itself. The
  name then builds word by word on the other side, with a "MỚI RA MẮT" badge, and the frame
  expands back. It hides a jump cut too.
  - Build it as a per-segment scale/position move in compose (or a full-frame overlay carrying
    the blurred plate), not as a card.
- **Active-word caption highlight:** a rounded colour box slides under the word being spoken
  inside the current chunk. It needs real word timestamps (`words_asr.json`). In ASS, make one
  Dialogue line per word-state, or render the captions in PIL.
- **Before/after story panel:** for a "the old way breaks, the new way works" narration:
  - one panel builds the old way's failure step by step (original image → request → a totally
    different image → red "KHÁC HẲN!" stamp);
  - the next panel shows the same original with only the requested change, plus a green stamp.

  Reuse ONE drawn picture across the cards so they read as one story.
