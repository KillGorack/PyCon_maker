"""Draw the application icon (icons/icon.png, 256x256) with the library's own renderer.
    python tools/make_app_icon.py
A rounded teal box holding a small set of shapes: the "library of icons" idea, no external artwork."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from iconlib.style import BUILTIN_THEMES, Style, compose  # noqa: E402
from iconlib.svgrender import parse_svg  # noqa: E402

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000000" '
       'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
       '<rect x="3" y="3" width="8" height="8" rx="2"/><circle cx="17" cy="7" r="4"/>'
       '<path d="M7 21l-4-7h8z"/><path d="M17 13.5l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4z"/></svg>')
ocean = next(t for t in BUILTIN_THEMES if t.name == "Ocean")
img = compose(parse_svg(SVG), 256, Style(box="rounded", padding=5, radius=0.24, stroke=1.6), ocean)
img.save(ROOT / "icons" / "icon.png")
print("wrote icons/icon.png", img.size)
