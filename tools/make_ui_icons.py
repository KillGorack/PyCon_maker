"""Draw the app's own toolbar icons (96x96 white PNG masks, the Dave-Standard icon format)
with the library's renderer, so no external icon pack is needed.
    python tools/make_ui_icons.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from iconlib.svgrender import parse_svg, render  # noqa: E402

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000000" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{}</svg>')
ICONS = {
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    # safe-area toggle: canvas box with an inner dashed-looking guide box and a center cross
    "grid": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/><path d="M15 3v18"/>'
            '<path d="M3 9h18"/><path d="M3 15h18"/>',
    # export: arrow leaving a tray
    "export": '<path d="M12 15V3"/><path d="M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
}

for name, body in ICONS.items():
    img = render(parse_svg(HEAD.format(body)), 96, {"main": "#ffffff"})
    img.save(ROOT / "icons" / f"{name}.png")
    print("wrote", name)
