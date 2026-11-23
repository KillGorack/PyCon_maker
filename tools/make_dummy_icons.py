"""Generate the dummy development library: library/icons/*.svg, index.json, one collection.

All artwork is original and hand-written here (no external icon packs). Re-run any time:
    python tools/make_dummy_icons.py          (refuses if the library already has icons)
    python tools/make_dummy_icons.py --force  (reset to the dummy data; overwrites index + collections)

Role colors (see SPEC.md section 3): main #000000, shade #FF0000, light #0000FF.
"""
import json
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "library"
MAIN, SHADE, LIGHT = "#000000", "#FF0000", "#0000FF"

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">')


def mono(*shapes: str) -> str:
    return "\n".join([HEAD.format(c=MAIN), *("  " + s for s in shapes), "</svg>\n"])


def roles(**layers: list[str]) -> str:
    """Explicit-role icon: layers keyed main/shade/light, each a list of shape strings
    (shapes may carry their own fill/stroke attributes)."""
    out = [HEAD.format(c=MAIN)]
    colors = {"shade": SHADE, "light": LIGHT, "main": MAIN}
    for role in ("shade", "light", "main"):        # drawn back to front
        for s in layers.get(role, []):
            if "fill=" not in s and "stroke=" not in s:
                s = s.replace("/>", f' stroke="{colors[role]}"/>', 1)
            out.append("  " + s)
    out.append("</svg>\n")
    return "\n".join(out)


ICONS: dict[str, tuple[str, list[str], str, str]] = {
    # id: (svg, tags, notes, depth)
    "arrow-left": (mono('<path d="M19 12H5"/>', '<path d="M12 19l-7-7 7-7"/>'),
                   ["arrow", "navigation", "ui"], "", "auto"),
    "arrow-right": (mono('<path d="M5 12h14"/>', '<path d="M12 5l7 7-7 7"/>'),
                    ["arrow", "navigation", "ui"], "", "auto"),
    "check": (mono('<path d="M20 6 9 17l-5-5"/>'), ["ui", "status"], "", "auto"),
    "plus": (mono('<path d="M12 5v14"/>', '<path d="M5 12h14"/>'), ["ui", "action"], "", "auto"),
    "home": (mono('<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>'),
             ["ui", "building"], "Uses arc commands: renderer test.", "auto"),
    "star": (mono('<polygon points="12 2 15 8.6 22 9.4 16.8 14.2 18.2 21.2 12 17.7 5.8 21.2 7.2 14.2 2 9.4 9 8.6"/>'),
             ["shape", "rating"], "", "auto"),
    "heart": (mono('<path d="M12 20.5C5 15 3 11.5 3 8.5A4.5 4.5 0 0 1 12 6.6 4.5 4.5 0 0 1 21 8.5c0 3-2 6.5-9 12z"/>'),
              ["shape", "love"], "Cubic + arc curves.", "auto"),
    "shape-mix": (mono('<circle cx="8" cy="8" r="4"/>', '<rect x="13" y="13" width="7" height="7" rx="1.5"/>',
                       '<ellipse cx="17" cy="7" rx="3.5" ry="2.5"/>', '<line x1="4" y1="20" x2="10" y2="14"/>',
                       '<polyline points="4 14 7 17 10 20"/>'),
                  ["test", "shape"], "One of every allowed element.", "auto"),
    "shield": (mono('<path d="M12 3 4 6v6c0 4.5 3.2 7.8 8 9 4.8-1.2 8-4.5 8-9V6z"/>'),
               ["combat", "ui", "defense"], "", "auto"),
    "sword": (mono('<path d="M14 5 19 3l-2 5L8 17"/>', '<path d="M6 15l3 3"/>', '<path d="M4 20l3-3"/>'),
              ["combat", "weapon"], "", "auto"),
    # explicit three-tone: shade lower-right edge, light upper-left edge, main outline
    "shield-tone": (roles(
        shade=['<path d="M17 8.5V12c0 3-1.8 5.2-5 6.5"/>'],
        light=['<path d="M7 8.5V12c0 1.2.3 2.2.8 3.1"/>'],
        main=['<path d="M12 3 4 6v6c0 4.5 3.2 7.8 8 9 4.8-1.2 8-4.5 8-9V6z"/>']),
        ["combat", "ui", "defense", "tone"], "Explicit roles: depth drawn by hand.", "auto"),
    "gem-tone": (roles(
        shade=['<path d="M12 21 21 9.5H12z" fill="#FF0000" stroke="none"/>'],
        light=['<path d="M3 9.5 7 4l5 5.5z" fill="#0000FF" stroke="none"/>'],
        main=['<path d="M7 4h10l4 5.5L12 21 3 9.5z"/>', '<path d="M3 9.5h18"/>']),
        ["gem", "tone"], "Explicit roles, filled shapes.", "auto"),
    # deliberately busy: automatic depth would smudge it
    "rune-dense": (mono(
        '<circle cx="12" cy="12" r="9.5" stroke-width="1"/>', '<circle cx="12" cy="12" r="6.5" stroke-width="1"/>',
        '<path d="M12 2.5v19M2.5 12h19" stroke-width="1"/>', '<path d="M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7" stroke-width="1"/>',
        '<path d="M9 9l3-3 3 3-3 3z" stroke-width="1"/>', '<path d="M9 15l3-3 3 3-3 3z" stroke-width="1"/>'),
        ["test", "detailed", "magic"], "Too detailed for automatic depth.", "off"),
}

COLLECTION = {"name": "UI basics", "icons": ["arrow-left", "arrow-right", "check", "plus", "home"], "style": None}


def main(force: bool = False):
    if not force and any((LIB / "icons").glob("*.svg")):
        raise SystemExit(f"{LIB} already has icons; this script would overwrite your index and collections.\n"
                         "Run with --force if you really want to reset it to the dummy data.")
    (LIB / "icons").mkdir(parents=True, exist_ok=True)
    (LIB / "collections").mkdir(parents=True, exist_ok=True)
    index = {"version": 1, "icons": {}}
    for name, (svg, tags, notes, depth) in ICONS.items():
        (LIB / "icons" / f"{name}.svg").write_text(svg, encoding="utf-8")
        index["icons"][name] = {"tags": tags, "notes": notes, "depth": depth, "aliases": []}
    (LIB / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (LIB / "collections" / "ui-basics.json").write_text(json.dumps(COLLECTION, indent=2), encoding="utf-8")
    print(f"wrote {len(ICONS)} icons to {LIB}")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
