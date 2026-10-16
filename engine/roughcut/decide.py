"""Keep/drop rules for a single-speaker take. Pure functions, no I/O.

Rules, applied in order:
  SHORT / FILLER  too short to transcribe, nothing recognised, or only filler words → drop
  STRAY        an island with at most one content word ("chưa", "đúng", "thì") → drop
  RESTART      inside one island the speaker restarts: a repeated phrase (≥ 2 words at the
               start, ≥ 3 words elsewhere, ≤ 15 words apart) → drop from the first occurrence
               to the restart. Covers "nhưng với X nhưng với X Y" and longer false starts.
  STUTTER      the same word twice in a row with a pause between ("có có") → drop the first
  RETAKE       "last take wins": a later island (≤ RETAKE_WINDOW s) that opens like this one —
               or like a part INSIDE this one (≤ MID_RETAKE_WINDOW s) — supersedes it from that
               point on; everything in between is dropped. Exception: if the later take is a
               stuttered repeat of a complete earlier take, the earlier one is kept.
  TAIL_OVERLAP a kept island ends with words that start the next kept island (or one of the
               dropped takes in between) → trim them; a remainder of ≤ 1 content word → drop

Openings are compared on CONTENT words (stop words such as và/thì/là/cái are ignored), after
mapping user aliases for names the recogniser mis-hears (cloud/load/lott → claude).

Times: drops are decided on words, then mapped to measured pauses — a cut edge is always
inside a silence. A kept island can therefore have internal `cuts`.

Probe step (needs Vbee, run by the pipeline): `probe_candidates` lists short first/last
voiced pieces of kept spans (0.3-0.8 s, set off by a pause). The pipeline lets Vbee hear the
PIECE itself; `apply_probes` cuts it when Vbee hears nothing or only "à/ừ", or when the piece's
words are said again right after it (then the rest is transcribed to check).
Measured on uncut.mp4: transcribing the span WITHOUT the piece does not work — Vbee fills in
the missing first word from context ("thì rất là cao" → "giá thì rất là cao"), 10/11 wrong.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher

FILLERS = {"à", "ừ", "ờ", "ừm", "ừ ừ", "hả", "ơ", "ạ", "ờm", "ừa", "hừm", "uh", "um", "uhm", "hmm", "ah", "eh"}
STOP = {"và", "thì", "là", "cái", "mà", "á", "à", "ạ", "nè", "nhé", "nha", "ơ", "ờ", "ừ"}
MIN_TRANSCRIBE = 0.30      # Vbee FAILs below this; such islands are clicks/breaths
RETAKE_WINDOW = 60.0       # a restart further away than this is treated as intentional
MID_RETAKE_WINDOW = 30.0   # a later island repeating the middle/end of an earlier one
OPEN_WORDS = 6             # content words compared at an opening
RESTART_SPAN = 15          # a within-island restart repeats a phrase at most this many words later
FALSE_START_MAX = 8        # (v1 helper, kept for compatibility)
PAD = 0.12                 # silence kept before/after every kept phrase
MERGE_GAP = 0.50           # kept phrases closer than this stay one continuous range
FILLER_CUT = {"à", "ừ", "ờ", "ừm", "ờm", "ừa", "hừm", "ơ", "uh", "um", "uhm", "hmm", "ah", "eh"}
WORD_SNAP = 0.35           # with word times: the pause before word k must END within this of its time
SHORT_TAKE = 5             # an abandoned take of at most this many content words: its first two words
                           # may differ from the next take's by one letter / tone ("go claude" → "gói claude")
SLIVER = 0.15              # voiced piece shorter than a syllable left at a cut edge
PROBE_MAX_PIECE = 0.80     # a candidate leading/trailing piece is at most this long
PROBE_MIN_PIECE = 0.35     # …and long enough for Vbee to hear it: at 0.30 s Vbee returned nothing for a
                           # real "thứ" (uncut.mp4, island 65), so "heard nothing" means nothing only above this
PROBE_MIN_GAP = 0.20       # …and separated from the rest by at least this much silence

# Spoken-syllable weights for tokens that are not single Vietnamese syllables.
WEIGHTS = {"chatgpt": 4, "image": 2, "video": 2.5, "ai": 1, "use": 1, "case": 1, "app": 1,
           "youtube": 3, "tiktok": 2, "google": 2, "iphone": 3, "claude": 1, "gpt": 3, "edit": 2}


@dataclass
class Island:
    i: int
    start: float
    end: float
    text: str | None          # None = not transcribed / Vbee could not recognise
    words: list | None = None  # [[word, source time], …] from an engine that times words (Zipformer)


@dataclass
class Decision:
    i: int
    start: float              # island bounds (speech)
    end: float
    text: str
    keep: bool
    kind: str                 # KEEP | SHORT | FILLER | STRAY | RESTART | STUTTER | RETAKE | TAIL_OVERLAP | PROBE | USER
    reason: str
    keep_start: float | None = None   # speech bounds actually kept (after trims)
    keep_end: float | None = None
    by: int | None = None             # island that superseded this one
    cuts: list = field(default_factory=list)   # [[s, e], …] removed inside the kept span
    words: list | None = None                  # word times when the engine gave them

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- tokens

def tokens(text: str | None) -> list[str]:
    if not text:
        return []
    t = unicodedata.normalize("NFC", text.lower())
    t = re.sub(r"[^\w\s.]", " ", t)          # keep "2.5"
    return [w.strip(".") for w in t.split() if w.strip(".")]


def parse_aliases(spec) -> dict[str, str]:
    """"Claude: cloud, load, lott" (one name per line) or {variant: name} → {"cloud": "claude", …}."""
    if not spec:
        return {}
    if isinstance(spec, dict):
        out = {}
        for k, v in spec.items():
            kt, vt = tokens(k), tokens(v)
            if len(kt) == 1 and vt:
                out[kt[0]] = " ".join(vt)
        return out
    out = {}
    for line in str(spec).splitlines():
        if ":" not in line:
            continue
        name, variants = line.split(":", 1)
        canon = " ".join(tokens(name))
        for v in variants.split(","):
            vt = tokens(v)
            if len(vt) == 1 and canon:
                out[vt[0]] = canon
    return out


def norm_tokens(text: str | None, aliases: dict[str, str]) -> list[str]:
    return [aliases.get(t, t) for t in tokens(text)]


def is_filler(toks: list[str]) -> bool:
    return not toks or all(w in FILLERS for w in toks) or " ".join(toks) in FILLERS


def content(toks: list[str]) -> list[str]:
    return [t for t in toks if t not in STOP and t not in FILLERS]


def collapse(toks: list[str]) -> list[str]:
    out = []
    for t in toks:
        if not out or out[-1] != t:
            out.append(t)
    return out


REPHRASE_MIN = 5           # both sentences have at least this many content words
REPHRASE_SHARE = 0.7       # …and share this much of the shorter one, in order


def lcs_len(a: list[str], b: list[str]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def has_stutter(toks: list[str]) -> bool:
    return any(a == b for a, b in zip(toks, toks[1:]))


def overlap(a: list[str], b: list[str]) -> int:
    return sum(bl.size for bl in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


def same_opening(a: list[str], b: list[str]) -> bool:
    """a, b: content words (collapsed). Same first word, then enough overlap."""
    a, b = a[:OPEN_WORDS], b[:OPEN_WORDS]
    n = min(len(a), len(b))
    if n < 2 or a[0] != b[0]:
        return False
    if n == 2:
        return a[:2] == b[:2]
    matched = overlap(a, b)
    return matched >= 3 and matched / n >= 0.6


def abandoned_opening(a: list[str], b: list[str]) -> bool:
    """A short take that re-appears as the exact start of the next one, then trails off:
    "cái skill của họ làm cho các" → "cái skill của họ dùng trong những clip ngắn…".
    ≥ 3 identical opening content words and at most 3 more words in the short take."""
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    return prefix >= 3 and len(a) <= prefix + 3 and len(b) > prefix


def base(t: str) -> str:
    """Letters without tone marks or vowel hats: "gói" → "goi", "đã" → "da"."""
    s = unicodedata.normalize("NFD", t.replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def near(a: str, b: str) -> bool:
    """Same word, or one letter apart once tones are removed ("go"/"gói", "góp"/"gói")."""
    if a == b:
        return True
    x, y = base(a), base(b)
    if not x or not y or x[0] != y[0] or abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(c != d for c, d in zip(x, y)) <= 1
    if len(x) > len(y):
        x, y = y, x
    return any(y[:k] + y[k + 1:] == x for k in range(len(y)))


def misheard_short_take(a: list[str], b: list[str]) -> bool:
    """A short take (≤ SHORT_TAKE content words) that starts like the next take, allowing the
    recogniser to hear the two opening words slightly differently, and the next take goes on
    longer: "go claude" → "góp claude trả phí" → "gói claude đã gần sáu trăm nghìn một tháng…",
    "nhưng với tat cpt em" → "nhưng với chat gpt emit hai chấm năm…"."""
    return (2 <= len(a) <= SHORT_TAKE and len(b) > len(a)
            and near(a[0], b[0]) and near(a[1], b[1]))


def opens_like(a: list[str], b: list[str]) -> bool:      # v1 name, kept for callers
    return same_opening(collapse(content(a)), collapse(content(b)))


# --------------------------------------------------------------------------- time mapping

def weight(tok: str) -> float:
    return WEIGHTS.get(tok, 1.0)


def voiced(start: float, end: float, pauses: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pieces, cur = [], start
    for a, b in pauses:
        if b <= start or a >= end:
            continue
        a, b = max(a, start), min(b, end)
        if a > cur:
            pieces.append((cur, a))
        cur = max(cur, b)
    if end > cur:
        pieces.append((cur, end))
    return pieces or [(start, end)]


def time_at_token(isl_start: float, isl_end: float, toks: list[str], k: int,
                  pauses: list[tuple[float, float]]) -> float:
    """Estimated start time of token k: syllables spread evenly over voiced time."""
    pieces = voiced(isl_start, isl_end, pauses)
    total_w = sum(weight(t) for t in toks) or 1.0
    target = sum(b - a for a, b in pieces) * sum(weight(t) for t in toks[:k]) / total_w
    for a, b in pieces:
        if target <= b - a:
            return a + target
        target -= b - a
    return pieces[-1][1]


def nearest_pause(t: float, lo: float, hi: float, pauses: list[tuple[float, float]]) -> tuple[float, float] | None:
    inside = [(a, b) for a, b in pauses if a > lo + 0.15 and b < hi - 0.15]
    if not inside:
        return None
    return min(inside, key=lambda p: abs((p[0] + p[1]) / 2 - t))


SNAP_WINDOW = 1.2          # a cut edge snaps to the LONGEST pause within this distance of the estimate


def snap_pause(t: float, lo: float, hi: float, pauses: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Pause for a cut edge: speakers pause longest right before they restart, so among pauses
    near the word-time estimate take the longest (estimates drift ~0.5 s on long islands)."""
    inside = [(a, b) for a, b in pauses if a > lo + 0.15 and b < hi - 0.15]
    near = [p for p in inside if abs((p[0] + p[1]) / 2 - t) <= SNAP_WINDOW]
    if near:
        return max(near, key=lambda p: p[1] - p[0])
    return nearest_pause(t, lo, hi, pauses)


def false_start_restart(toks: list[str]) -> int | None:
    """v1: index where the speaker restarts the sentence, if the opening words repeat."""
    for k in range(2, min(FALSE_START_MAX, len(toks) - 1) + 1):
        m = 2
        while k + m <= len(toks) and m <= k and toks[k:k + m] == toks[:m]:
            m += 1
        if m - 1 >= 2:
            return k
    return None


def restarts(toks: list[str]) -> list[tuple[int, int]]:
    """Token ranges [p, q) abandoned by a restart inside one island."""
    drops, start, q = [], 0, 1
    while q < len(toks):
        found = None
        for p in range(max(start, q - RESTART_SPAN), q):
            m = 0
            while q + m < len(toks) and p + m < q and toks[p + m] == toks[q + m]:
                m += 1
            # R2: a word broken off mid-way and said again: "để chạy s | để chạy skill"
            truncated = (m >= 2 and q == p + m + 1 and q + m < len(toks)
                         and len(toks[p + m]) < len(toks[q + m]) and toks[q + m].startswith(toks[p + m]))
            # (2 words also one word into the island when said back to back: "ok cũng là | cũng là
            #  video…" — that word belongs to the abandoned start. Not "để các bạn … mà các bạn còn")
            lead = m >= 2 and p == start + 1 and q == p + m
            if m >= 3 or (m >= 2 and p == start) or lead or truncated:
                found = (start if lead and m < 3 else p, q)
                # R3: the whole clause was restarted: the word right before the repeat also opens
                # the abandoned part ("và cũng là do thời gian có giá | và do thời gian có giới hạn")
                if q - 1 >= p + m:
                    for p2 in range(max(start, p - 3), p):
                        if toks[p2] == toks[q - 1]:
                            found = (p2, q - 1)
                            break
                break
        if found:
            drops.append(found)
            start = q
        q += 1
    return drops


# --------------------------------------------------------------------------- decide

class _Isl:
    """Working state: one island, its tokens and a keep-mask over them."""

    def __init__(self, isl: Island, aliases: dict[str, str]):
        self.isl, self.i = isl, isl.i
        self.times = None
        if isl.words:
            pairs = [(tokens(w), t) for w, t in isl.words]
            pairs = [(tk[0], t) for tk, t in pairs if tk]
            self.toks = [aliases.get(w, w) for w, _ in pairs]
            self.times = [t for _, t in pairs]
        else:
            self.toks = norm_tokens(isl.text, aliases)
        self.mask = [True] * len(self.toks)
        self.strict = [False] * len(self.toks)    # a filler word: cut only at a pause around it
        self.keep = True
        self.kind, self.reasons, self.by = "KEEP", [], None

    def kept_idx(self) -> list[int]:
        return [k for k, m in enumerate(self.mask) if m]

    def kept_toks(self) -> list[str]:
        return [self.toks[k] for k in self.kept_idx()]

    def opening(self) -> list[str]:
        return collapse(content(self.kept_toks()))

    def t(self, k: int, pauses) -> float:
        """Start time of token k (k == len: end of the island)."""
        if self.times is not None:
            return self.times[k] if k < len(self.times) else self.isl.end
        return time_at_token(self.isl.start, self.isl.end, self.toks, k, pauses)

    def drop(self, kind, reason, by=None):
        self.keep, self.kind, self.by = False, kind, by
        self.reasons = [reason]

    def cut(self, lo: int, hi: int, kind: str, reason: str):
        for k in range(lo, hi):
            self.mask[k] = False
        if self.kind == "KEEP":
            self.kind = kind
        self.reasons.append(reason)


def decide(islands: list[Island], pauses: list[tuple[float, float]], aliases=None,
           mode: str = "intro") -> list[Decision]:
    """mode "intro" (talking head, the original rules) or "tutorial" (screen recording, spontaneous
    speech: two extra rules for restarts the recogniser hears slightly differently)."""
    al = parse_aliases(aliases)
    W = [_Isl(isl, al) for isl in islands]

    # SHORT / FILLER / STRAY
    for w in W:
        if w.isl.end - w.isl.start < MIN_TRANSCRIBE:
            w.drop("SHORT", "tiếng động ngắn, không phải lời nói")
        elif is_filler(w.toks):
            w.drop("FILLER", f"từ đệm “{w.isl.text}”" if w.isl.text else "không nhận ra lời (thường là à/ừ/tiếng động)")
        elif len(content(w.toks)) <= 1 and len(w.toks) <= 2:
            w.drop("STRAY", f"chữ lạc “{w.isl.text}”")

    # FILLER words inside a kept island (only when words are timed): cut at the pauses around them
    for w in W:
        if w.keep and w.times is not None:
            for k, tok in enumerate(w.toks):
                if tok in FILLER_CUT:
                    w.mask[k], w.strict[k] = False, True

    # RESTART / STUTTER inside an island, found on the words without fillers ("có ờm có" is a stutter)
    for w in W:
        if not w.keep:
            continue
        idx = [k for k, tok in enumerate(w.toks) if tok not in FILLERS]
        seq = [w.toks[k] for k in idx]
        for p, q in restarts(seq):
            w.cut(idx[p], idx[q], "RESTART", f"bỏ đoạn nói hỏng “{' '.join(seq[p:q])}”")
        for j in range(len(seq) - 1):
            k, k2 = idx[j], idx[j + 1]
            if w.mask[k] and w.mask[k2] and seq[j] == seq[j + 1] and _pause_between(w, k2, pauses):
                w.cut(k, k2, "STUTTER", f"bỏ chữ lặp “{seq[j]}”")

    # RETAKE: a later island re-says this one (from its start or from a point inside it)
    for n, w in enumerate(W):
        if not w.keep:
            continue
        for later in W[n + 1:]:
            if not later.keep:
                continue
            if later.isl.start - w.isl.start > RETAKE_WINDOW:
                break
            lo = _match_point(w, later, mid_ok=later.isl.start - w.isl.end <= MID_RETAKE_WINDOW)
            if lo is None:
                continue
            between = [m for m in W if w.isl.start < m.isl.start < later.isl.start and m.keep]
            tail = [w.toks[k] for k in w.kept_idx() if k >= lo]
            if (has_stutter(later.kept_toks()) and not has_stutter(tail)
                    and len(later.opening()) <= len(collapse(content(tail))) + 1):
                later.drop("RETAKE", f"lần nói lại ở {later.isl.start:.1f}s bị vấp — giữ lần trước", by=w.i)
                for m in between:
                    m.drop("RETAKE", "nằm giữa hai lần nói cùng một câu", by=w.i)
                continue
            if lo == _first_kept(w):
                w.drop("RETAKE", f"nói lại ở {later.isl.start:.1f}s", by=later.i)
            else:
                w.cut(lo, len(w.toks), "RETAKE", f"phần cuối được nói lại ở {later.isl.start:.1f}s")
            for m in between:
                m.drop("RETAKE", f"nằm giữa lần nói hỏng và lần nói lại ở {later.isl.start:.1f}s", by=later.i)
            break

    if mode == "tutorial":
        _tutorial_rules(W)

    # R1 REPHRASE: the next kept sentence says the same thing in other words (≥ 70 % of the
    # shorter one's content words, in order) → the earlier one was a take
    kept = [w for w in W if w.keep]
    for a, b in zip(kept, kept[1:]):
        ca, cb = collapse(content(a.kept_toks())), collapse(content(b.kept_toks()))
        if (b.isl.start - a.isl.end <= MID_RETAKE_WINDOW and min(len(ca), len(cb)) >= REPHRASE_MIN
                and lcs_len(ca, cb) >= REPHRASE_SHARE * min(len(ca), len(cb))):
            a.drop("RETAKE", f"nói lại bằng cách diễn đạt khác ở {b.isl.start:.1f}s", by=b.i)

    # R4 LEFTOVER: what remains of a cut-up island is ≤ 2 words that open the next kept sentence
    kept = [w for w in W if w.keep]
    for a, b in zip(kept, kept[1:]):
        rest = collapse(content(a.kept_toks()))
        head = b.opening()[:4]
        if (not all(a.mask) and 1 <= len(rest) <= 2 and b.isl.start - a.isl.end <= MID_RETAKE_WINDOW
                and any(head[k:k + len(rest)] == rest for k in range(len(head)))):
            a.drop("RETAKE", f"mảnh còn sót “{' '.join(rest)}” được nói lại ở {b.isl.start:.1f}s", by=b.i)

    # TAIL_OVERLAP between consecutive kept islands (or the dropped takes in between)
    kept = [w for w in W if w.keep]
    for a, b in zip(kept, kept[1:]):
        heads = [b.kept_toks()] + [m.toks for m in W if a.isl.start < m.isl.start < b.isl.start and not m.keep]
        idx = a.kept_idx()
        ta = [a.toks[k] for k in idx]
        for m in range(min(4, len(ta) - 1), 1, -1):
            if any(len(h) >= m and h[:m] == ta[-m:] for h in heads):
                a.cut(idx[-m], len(a.toks), "TAIL_OVERLAP", f"cắt đuôi “{' '.join(ta[-m:])}” vì được nói lại ngay sau")
                break
        if a.keep and a.mask != [True] * len(a.mask) and len(content(a.kept_toks())) <= 1:
            a.drop("TAIL_OVERLAP", f"chỉ còn chữ lạc “{' '.join(a.kept_toks())}” sau khi bỏ phần nói lại")

    return [_to_decision(w, pauses) for w in W]


ADJACENT_GAP = 3.0         # tutorial rules look at phrases at most this far apart
REPEAT_TAIL_MAX = 4        # a fragment between a sentence and its retake has at most this many content words
FRAGMENT_WINDOW = 10.0     # T3 looks this far for the real retake behind short fragments


def _tutorial_rules(W: list[_Isl]) -> None:
    """Spontaneous narration over a screen recording (measured on 2026-09-05 21-24-36.mov)."""
    # T2 adjacent restart: the next phrase, right after, opens with the same three content words
    # ("về giao diện lấy a các nước…" | "về giao diện lau cái nốp…": heard differently after that)
    kept = [w for w in W if w.keep]
    for a, b in zip(kept, kept[1:]):
        oa, ob = a.opening(), b.opening()
        if (len(oa) >= 3 and len(ob) >= 3 and oa[:3] == ob[:3]
                and b.isl.start - a.isl.end <= ADJACENT_GAP):
            a.drop("RETAKE", f"nói lại ngay ở {b.isl.start:.1f}s (cùng mở đầu “{' '.join(oa[:3])}”)", by=b.i)
    # T3 rephrase across fragments: "trong khi Fable chỉ là [một bản chữ nhỏ]" | "một bản chữ" |
    # "trong khi phía bên Fable chỉ là một bản chữ tĩnh": compare a sentence with the next real one,
    # skipping short fragments (≤ REPEAT_TAIL_MAX content words) said in between
    kept = [w for w in W if w.keep]
    for n, a in enumerate(kept):
        if not a.keep:
            continue
        # all of a's words: its tail may have been cut as "re-said" by the very fragment that goes now
        ca = collapse(content([t for t in a.toks if t not in FILLERS]))
        between = []
        for b in kept[n + 1:]:
            if not b.keep:
                continue
            if b.isl.start - a.isl.end > FRAGMENT_WINDOW:
                break
            cb = collapse(content(b.kept_toks()))
            if len(cb) <= REPEAT_TAIL_MAX:
                between.append(b)
                continue
            if (between and min(len(ca), len(cb)) >= REPHRASE_MIN
                    and lcs_len(ca, cb) >= REPHRASE_SHARE * min(len(ca), len(cb))):
                a.drop("RETAKE", f"nói lại ở {b.isl.start:.1f}s (sau vài mẩu nói dở)", by=b.i)
                for m in between:
                    m.drop("RETAKE", f"mẩu nói dở trước lần nói lại ở {b.isl.start:.1f}s", by=b.i)
            break


def _first_kept(w: _Isl) -> int:
    idx = w.kept_idx()
    return idx[0] if idx else 0


def _pause_between(w: _Isl, k: int, pauses) -> bool:
    t = w.t(k, pauses)
    p = nearest_pause(t, w.isl.start - 0.2, w.isl.end + 0.2, pauses)
    return p is not None and p[1] - p[0] >= 0.1 and abs((p[0] + p[1]) / 2 - t) <= 0.35


def _match_point(w: _Isl, later: _Isl, mid_ok: bool) -> int | None:
    """Token index in w from which `later` re-says w (its first kept word, or a later word)."""
    head = later.opening()
    idx = w.kept_idx()
    if not idx or len(head) < 2:
        return None
    if (same_opening(w.opening(), head) or abandoned_opening(w.opening(), head)
            or misheard_short_take(w.opening(), head)):
        return idx[0]
    if not mid_ok:
        return None
    for pos in range(1, len(idx)):
        k = idx[pos]
        if w.toks[k] != head[0]:
            continue
        rest = collapse(content([w.toks[j] for j in idx[pos:]]))
        window = rest[:OPEN_WORDS]
        n = min(len(window), len(head))
        if n < 3:
            continue
        prefix = 0
        while prefix < n and window[prefix] == head[prefix]:
            prefix += 1
        full = later.opening()
        whole = overlap(rest, full) / min(len(rest), len(full))
        # A mid-sentence retake re-says ≥ 3 words in a row (or ≥ 2 when it re-says w's TAIL),
        # AND the rest of w is ≥ 70 % the same as the later island. This rejects parallel
        # phrasing ("…clip của họ… còn clip của bạn quay nấu ăn" vs "còn clip của bạn dài 20 phút",
        # 33 %) and ("nó tạo ra một bức ảnh đẹp" vs "nó lại tạo ra một bức ảnh mới").
        is_tail = len(rest) <= len(full) + 1
        if whole >= 0.7 and (prefix >= 3 or (prefix >= 2 and is_tail)):
            return k
    return None


def _pause_before_word(w: _Isl, k: int, pauses) -> tuple[float, float] | None:
    """With word times: the pause that ends right where word k starts (longest if several)."""
    t = w.t(k, pauses)
    near_ = [(a, b) for a, b in pauses
             if a > w.isl.start + 0.05 and b < w.isl.end - 0.05 and abs(b - t) <= WORD_SNAP]
    return max(near_, key=lambda p: p[1] - p[0]) if near_ else None


def _to_decision(w: _Isl, pauses) -> Decision:
    isl = w.isl
    d = Decision(isl.i, isl.start, isl.end, isl.text or "", w.keep, w.kind,
                 "; ".join(w.reasons) if w.reasons else "giữ", isl.start, isl.end, w.by,
                 words=isl.words)
    if not w.keep or all(w.mask):
        return d
    if not any(w.mask):
        d.keep = False
        return d
    runs, k = [], 0
    while k < len(w.mask):
        if not w.mask[k]:
            j = k
            while j < len(w.mask) and not w.mask[j]:
                j += 1
            runs.append((k, j))
            k = j
        else:
            k += 1

    def pause_at(k):
        """Pause just before token k: from word times when known, else from the estimate."""
        if w.times is not None:
            p = _pause_before_word(w, k, pauses)
            if p or strict:
                return p
        return snap_pause(w.t(k, pauses), isl.start, isl.end, pauses)

    fillers = []
    for a, b in runs:
        strict = all(w.strict[k] for k in range(a, b))   # filler words only: no fallback guess
        done = False
        if a == 0:
            p = pause_at(b)
            if p:
                d.keep_start, done = p[1], True
        elif b == len(w.mask):
            p = pause_at(a)
            if p and p[0] > d.keep_start:
                d.keep_end, done = p[0], True
        else:
            p1, p2 = pause_at(a), pause_at(b)
            if p1 and p2 and p1[1] <= p2[0]:
                d.cuts.append([p1[0], p2[1]])
                done = True
        if strict and done:
            fillers.append(" ".join(w.toks[a:b]))
    d.cuts = [c for c in d.cuts if d.keep_start < c[0] and c[1] < d.keep_end]
    if fillers:
        note = "bỏ từ đệm " + ", ".join(f"“{f}”" for f in fillers)
        d.reason = note if d.reason == "giữ" else d.reason + "; " + note
        if d.kind == "KEEP":
            d.kind = "FILLER"
    # A trailing cut must not leave a sliver (< SLIVER s of voice, shorter than a syllable)
    # before it: that is the onset of the dropped word → end at the pause before it.
    # (Not applied at a leading cut: a short voiced piece there is usually the burst of a
    # kept word's first consonant — measured on "đừng" and "nó" in the uncut fixture.)
    pieces = voiced(d.keep_start, d.keep_end, pauses)
    if d.keep_end < isl.end and len(pieces) > 1 and pieces[-1][1] - pieces[-1][0] < SLIVER:
        d.keep_end = pieces[-2][1]
    return d


# --------------------------------------------------------------------------- spans / ranges

def kept_spans(d: Decision) -> list[tuple[float, float]]:
    if not d.keep:
        return []
    spans, cur = [], d.keep_start
    for s, e in sorted(d.cuts):
        if s > cur:
            spans.append((cur, s))
        cur = max(cur, e)
    if d.keep_end > cur:
        spans.append((cur, d.keep_end))
    return spans


# Pacing of the output. "fast" copies the hand edit of raw-gpt.mp4 made with Vbee texts on 2026-10-10
# (measured: 0.06 s kept before the first voiced sound, 0.10 s after the last; pauses inside phrases up to
# ~0.9 s). "relaxed" is the original app pacing (PAD around the detected island edges, which start
# ~0.15 s before the voice).
PACES = {
    "fast": {"lead": 0.06, "tail": 0.10, "snap": True, "max_pause": 0.60, "keep_pause": 0.40},
    "relaxed": {"lead": PAD, "tail": PAD, "snap": False, "max_pause": None, "keep_pause": None},
}
DEFAULT_PACE = "fast"


def ranges(decisions: list[Decision], pauses: list[tuple[float, float]], duration: float,
           pace: str = "relaxed") -> list[tuple[float, float]]:
    """Kept speech → padded output ranges. Padding never reaches into neighbouring speech.

    pace "fast": edges hug the voice (measured pauses, not the coarse island edges) and any pause
    longer than max_pause inside a range is shortened to keep_pause (split in its middle).
    """
    cfg = PACES[pace]
    all_spans = sorted((d.start, d.end) for d in decisions)
    kept = sorted(s for d in decisions for s in kept_spans(d))
    dropped = [(d.start, d.end) for d in decisions if not d.keep]
    dropped += [tuple(c) for d in decisions if d.keep for c in d.cuts]
    dropped += [(d.start, d.keep_start) for d in decisions if d.keep and d.keep_start > d.start + 0.05]
    dropped += [(d.keep_end, d.end) for d in decisions if d.keep and d.keep_end < d.end - 0.05]
    out: list[list[float]] = []
    for a, b in kept:
        prev_end = max([e for s, e in all_spans if e <= a + 1e-6] + [0.0])
        next_start = min([s for s, e in all_spans if s >= b - 1e-6] + [duration])
        # trims at an internal pause: stay inside that pause
        lo_pause = next((p for p in pauses if abs(p[1] - a) < 1e-6), None)
        hi_pause = next((p for p in pauses if abs(p[0] - b) < 1e-6), None)
        lo_limit = (lo_pause[0] + lo_pause[1]) / 2 if lo_pause else (prev_end + a) / 2
        hi_limit = (hi_pause[0] + hi_pause[1]) / 2 if hi_pause else (b + next_start) / 2
        if cfg["snap"]:                      # from the first to the last voiced sound of the span
            v = voiced(a, b, pauses)
            va, vb = v[0][0], v[-1][1]
        else:
            va, vb = a, b
        ra, rb = max(va - cfg["lead"], lo_limit, 0.0), min(vb + cfg["tail"], hi_limit, duration)
        # Merge only across a plain pause: never across speech that was dropped in between
        # (a filler or a stumble inside the gap would otherwise be put back).
        dropped_between = out and any(s < a and e > out[-1][2] for s, e in dropped)
        if out and a - out[-1][2] <= MERGE_GAP and not dropped_between:
            out[-1][1], out[-1][2] = rb, b
        else:
            out.append([ra, rb, b])
    res = [(a, b) for a, b, _ in out]
    if cfg["max_pause"]:
        res = _shorten_pauses(res, pauses, cfg["max_pause"], cfg["keep_pause"])
    return [(round(a, 3), round(b, 3)) for a, b in res]


def _shorten_pauses(rngs, pauses, max_pause: float, keep: float) -> list[tuple[float, float]]:
    """Inside each range, a silence longer than max_pause keeps only `keep` seconds (half after the
    word before it, half before the word after it); the range is split there."""
    out = []
    for a, b in rngs:
        cur = a
        for p0, p1 in sorted(pauses):
            if p0 > cur and p1 < b and p1 - p0 > max_pause:
                out.append((cur, p0 + keep / 2))
                cur = p1 - keep / 2
        out.append((cur, b))
    return out


def pause_points(d: Decision, pauses, aliases=None, min_len: float = 0.12) -> list[dict]:
    """Pauses inside an island with the words around them — the cut points offered in review.

    Word positions are estimates (syllable weights over voiced time), so the labels say
    roughly which words sit on each side: good enough to pick "cut after 'hướng dẫn'".
    """
    if d.words:                                   # measured word times
        toks = [w for w, _ in d.words]
        starts = [t for _, t in d.words]
    else:                                         # estimates spread over voiced time
        toks = (d.text or "").split()
        norm = norm_tokens(d.text, parse_aliases(aliases))
        if len(norm) != len(toks):
            toks = norm
        starts = [(time_at_token(d.start, d.end, norm, j, pauses)
                   + time_at_token(d.start, d.end, norm, j + 1, pauses)) / 2 for j in range(len(norm))]
    out = []
    for a, b in pauses:
        if a <= d.start + 0.05 or b >= d.end - 0.05 or b - a < min_len:
            continue
        # measured word starts that land inside the pause belong to the word after it (the
        # recogniser's onset is ±0.3 s); estimates are word mid-points, split at the pause middle
        edge = a if d.words else (a + b) / 2
        k = sum(1 for t in starts if t < edge)
        out.append({"a": round(a, 3), "b": round(b, 3), "k": k,
                    "before": " ".join(toks[max(0, k - 3):k]), "after": " ".join(toks[k:k + 3])})
    return out


# --------------------------------------------------------------------------- review helpers

_VI_SYLLABLE = re.compile(r"^(ngh|ng|nh|ch|gh|gi|kh|ph|th|tr|qu|[bcdghklmnprstvx])?"
                          r"[aeiouy]{1,3}(ch|ng|nh|[cmnpt])?$")


def looks_vietnamese(tok: str) -> bool:
    """Shape of a Vietnamese syllable (onset + vowels + allowed final), tones ignored.
    "clot", "sw", "cpt", "exo", "ok" fail; "seo", "cho", "gói" pass."""
    return bool(_VI_SYLLABLE.match(base(tok)))


def alias_names(spec) -> dict[str, str]:
    """variant → name as the user typed it ("cloud" → "Claude"), for display."""
    out = {}
    for line in str(spec or "").splitlines():
        if ":" in line:
            name, variants = line.split(":", 1)
            for v in variants.split(","):
                vt = tokens(v)
                if len(vt) == 1 and name.strip():
                    out[vt[0]] = name.strip()
    return out


def display_text(text: str | None, spec) -> str:
    """The heard text with the name list applied ("tạo seo cho clod" → "tạo skill cho Claude")."""
    names = alias_names(spec)
    if not text or not names:
        return text or ""
    out = []
    for w in text.split():
        k = tokens(w)
        out.append(names[k[0]] if len(k) == 1 and k[0] in names else w)
    return " ".join(out)


# English words both engines hear correctly: not worth suggesting
COMMON_EN = {"video", "clip", "clips", "demo", "file", "app", "apps", "ok", "image", "edit", "vlog", "use", "case",
             "chatgpt", "gpt", "prompt", "youtube", "tiktok", "google", "iphone", "ai", "web", "online", "email",
             "robot", "game", "like"}


def foreign_words(decisions: list[Decision], spec, limit: int = 20) -> list[dict]:
    """Words heard that do not look Vietnamese and are not in the name list yet, most frequent first:
    candidates for the name list ("sw" ×3 → maybe "skill")."""
    al = parse_aliases(spec)
    known = set(al) | set(al.values())
    count: dict[str, int] = {}
    for d in decisions:
        for t in tokens(d.text):
            if t not in known and t not in COMMON_EN and not t.isdigit() and not looks_vietnamese(t):
                count[t] = count.get(t, 0) + 1
    return [{"w": w, "n": n} for w, n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


SUSPECT_WINDOW = 30.0      # suggested repeats: phrases at most this far apart…
SUSPECT_MIN = 5            # …sharing at least this many content words in order…
SUSPECT_SHARE = 0.6        # …and this share of the earlier phrase (the one the suggestion drops)


def kept_words(d: Decision, al: dict[str, str], pauses=()) -> list[str]:
    """The words of a decision that end up in the cut: by measured word times, else (Vbee) by times
    estimated over the voiced pieces — a trimmed phrase must not be compared by its dropped part."""
    spans = kept_spans(d)
    if d.words:
        toks = [tokens(w)[0] for w, t in d.words if tokens(w) and any(a - 0.05 <= t <= b for a, b in spans)]
        return [al.get(t, t) for t in toks]
    if spans == [(d.start, d.end)]:
        return norm_tokens(d.text, al)
    return [t for a, b in spans for t in span_words(d, (a, b), pauses, al)]


def suspect_repeats(decisions: list[Decision], spec, pauses=()) -> list[dict]:
    """Kept phrases that look like an earlier take of a later one: suggestions for the review screen,
    never applied automatically (an automatic version cut real restatements, measured 2026-10-15).
    Returns [{"i": earlier, "by": later, "at": later's start, "shared": n, "between": [kept ids in between]}]."""
    al = parse_aliases(spec)
    names = set(al.values())
    kept = [d for d in decisions if d.keep]
    words = {d.i: collapse(content([t for t in kept_words(d, al, pauses) if t not in FILLERS])) for d in kept}
    out = []
    for x, a in enumerate(kept):
        for b in kept[x + 1:]:
            if b.start - a.end > SUSPECT_WINDOW:
                break
            ca, cb = words[a.i], words[b.i]
            shared = lcs_len(ca, cb)
            na, nb = {t for t in ca if t in names}, {t for t in cb if t in names}
            # share of the EARLIER phrase: the suggestion drops all of it, so the later one must re-say
            # most of it (not just its tail: "…cắm cờ và biểu diễn những điệu" | "và có thể biểu diễn…")
            if (shared >= SUSPECT_MIN and shared >= SUSPECT_SHARE * len(ca)
                    and not (na and nb and na != nb)):
                # like a retake, whatever was said in between is part of the stumble
                between = [m.i for m in kept if a.end <= m.start and m.end <= b.start]
                out.append({"i": a.i, "by": b.i, "at": round(b.start, 2), "shared": shared, "between": between})
                break
    return out


# --------------------------------------------------------------------------- probe (Vbee) step

def probe_candidates(decisions: list[Decision], pauses: list[tuple[float, float]]) -> list[dict]:
    """Short first/last voiced pieces of kept spans that might be "à", a throat sound or a
    restarted word. `piece` is what Vbee should hear; `rest` the span without it."""
    out = []
    for d in decisions:
        for s, e in kept_spans(d):
            pieces = voiced(s, e, pauses)
            if len(pieces) < 2 or e - s < 1.0:
                continue
            first, second = pieces[0], pieces[1]
            if (PROBE_MIN_PIECE <= first[1] - first[0] <= PROBE_MAX_PIECE
                    and second[0] - first[1] >= PROBE_MIN_GAP):
                out.append({"i": d.i, "side": "start", "piece": list(first), "rest": [second[0], e], "span": [s, e]})
            last, prev = pieces[-1], pieces[-2]
            if (PROBE_MIN_PIECE <= last[1] - last[0] <= PROBE_MAX_PIECE
                    and last[0] - prev[1] >= PROBE_MIN_GAP):
                out.append({"i": d.i, "side": "end", "piece": list(last), "rest": [s, prev[1]], "span": [s, e]})
    return out


def piece_verdict(piece_text: str | None, rest_text: str | None, side: str, aliases=None) -> str | None:
    """Why the piece should go, or None to keep it.

    rest_text is only consulted for the "said again" check (None = not transcribed).
    """
    al = parse_aliases(aliases)
    piece = norm_tokens(piece_text, al)
    if is_filler(piece):
        return "Vbee không nghe ra chữ nào" if not piece else f"từ đệm “{piece_text}”"
    if rest_text is None:
        return None
    rest = norm_tokens(rest_text, al)
    # ≥ 2 words: Vbee fills in ONE missing word at a cut edge from context (measured 10×),
    # so a one-word match is no evidence that the speaker said it twice.
    n = len(piece)
    if n >= 2 and (side == "start" and rest[:n] == piece or side == "end" and rest[-n:] == piece):
        return f"“{piece_text}” được nói lại ngay sau"
    return None


def needs_rest(piece_text: str | None, aliases=None) -> bool:
    """The rest is worth transcribing only when the piece has words (it may be a restart)."""
    return not is_filler(norm_tokens(piece_text, parse_aliases(aliases)))


def span_words(d: Decision, span, pauses, aliases=None) -> list[str]:
    """Expected words of a kept span: island words whose estimated time falls inside it."""
    toks = norm_tokens(d.text, parse_aliases(aliases))
    out = []
    for k in range(len(toks)):
        mid = (time_at_token(d.start, d.end, toks, k, pauses) + time_at_token(d.start, d.end, toks, k + 1, pauses)) / 2
        if span[0] - 0.05 <= mid <= span[1] + 0.05 and not any(c[0] <= mid <= c[1] for c in d.cuts):
            out.append(toks[k])
    return out


def apply_probes(decisions: list[Decision], results: list[dict], pauses, aliases=None) -> list[Decision]:
    """results: probe_candidates() items + {"piece_text", "rest_text"?}. Mutates and returns decisions."""
    by_i = {d.i: d for d in decisions}
    for r in results:
        d = by_i[r["i"]]
        if not d.keep or "piece_text" not in r:
            continue
        why = piece_verdict(r["piece_text"], r.get("rest_text"), r["side"], aliases)
        if why is None:
            continue
        ps, pe = r["piece"]
        if r["side"] == "start":
            if abs(r["span"][0] - d.keep_start) < 1e-6:
                d.keep_start = r["rest"][0]
            else:
                d.cuts.append([ps - 0.001, r["rest"][0]])
            what = "đầu"
        else:
            if abs(r["span"][1] - d.keep_end) < 1e-6:
                d.keep_end = r["rest"][1]
            else:
                d.cuts.append([r["rest"][1], pe + 0.001])
            what = "cuối"
        note = f"bỏ mảnh ở {what} câu ({ps:.2f}-{pe:.2f}s): {why}"
        d.reason = note if d.reason in ("", "giữ") else d.reason + "; " + note
        if d.kind == "KEEP":
            d.kind = "PROBE"
    return decisions
