"""Render every library icon in several modes to one PNG, for eyeballing the renderer.
    python tools/contact_sheet.py OUT.png
Rows: as drawn | single tone (dark theme) | auto depth (dark theme) | auto depth (light theme).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from iconlib.svgrender import load, render  # noqa: E402

LIB = Path(__file__).resolve().parent.parent / "library" / "icons"
if not LIB.is_dir():                                               # fresh clone: use the dummy data
    import tempfile

    import make_dummy_icons
    make_dummy_icons.LIB = Path(tempfile.mkdtemp()) / "library"
    make_dummy_icons.main(force=True)
    LIB = make_dummy_icons.LIB / "icons"
DARK = {"main": "#d4d4d4", "shade": "#6e6e6e", "light": "#ffffff"}
LIGHT = {"main": "#332d24", "shade": "#000000", "light": "#8a7f6a"}
SIZE, PAD = 64, 12

icons = sorted(LIB.glob("*.svg"))
modes = [("as drawn", None, 0, "#ffffff"), ("flat dark", DARK, 0, "#171717"),
         ("depth dark", DARK, 0.6, "#171717"), ("depth light", LIGHT, 0.6, "#ded6c3")]
W = PAD + len(icons) * (SIZE + PAD)
H = PAD + len(modes) * (SIZE + PAD + 10)
sheet = Image.new("RGB", (W, H), "#888888")
d = ImageDraw.Draw(sheet)
for r, (label, pal, depth, bg) in enumerate(modes):
    y = PAD + r * (SIZE + PAD + 10)
    d.rectangle((0, y - 4, W, y + SIZE + 4), fill=bg)
    for c, p in enumerate(icons):
        x = PAD + c * (SIZE + PAD)
        im = render(load(p), SIZE, pal, depth)
        sheet.paste(im, (x, y), im)
sheet.save(sys.argv[1])
print([p.stem for p in icons])
