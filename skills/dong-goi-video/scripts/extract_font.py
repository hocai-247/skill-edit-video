"""Extract Helvetica Neue Condensed Black (macOS TTC index 9) to a standalone TTF with a UNIQUE
family name. libass ignores face/style names inside a TTC and silently falls back to regular
Helvetica Neue, so captions need this file + `fontsdir` (compose.py passes it).

Usage: python extract_font.py OUT_DIR   → OUT_DIR/VUCondBlack.ttf, family "VU Cond Black"
"""
import sys
from pathlib import Path
from fontTools.ttLib import TTCollection

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
font = TTCollection("/System/Library/Fonts/HelveticaNeue.ttc").fonts[9]
style = font["name"].getDebugName(2)
full = font["name"].getDebugName(4)
assert "Condensed Black" in (full or ""), f"index 9 is {full!r}, not Condensed Black"
name = font["name"]
for rec in list(name.names):
    if rec.nameID in (1, 16):
        rec.string = "VU Cond Black"
    elif rec.nameID == 4:
        rec.string = "VU Cond Black"
    elif rec.nameID == 6:
        rec.string = "VUCondBlack"
    elif rec.nameID in (2, 17):
        rec.string = "Regular"
font.save(out / "VUCondBlack.ttf")
print("wrote", out / "VUCondBlack.ttf", "(from", full, ")")
