"""UI-independent preview helpers: tone palettes, safe-area guides, flow layout, ID suggestion."""
from __future__ import annotations

import re

from PIL import Image, ImageDraw


SAFE_MARGIN = 2          # units on the 24x24 canvas (SPEC.md section 3)


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Blend hex color a toward b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


def tone_palette(main: str, strength: float = 0.45) -> dict[str, str]:
    """Three related tones from one theme color: shade toward black, light toward white.
    (Step 5 turns this into named, user-editable themes.)"""
    return {"main": main, "shade": mix(main, "#000000", strength), "light": mix(main, "#ffffff", strength)}


def guides(size: int, color: str, side: float = 24.0, pad: float = 0.0) -> Image.Image:
    """Transparent overlay marking the 24-unit canvas, its safe area and its center cross.
    `side` is the total span in units and `pad` the space around the canvas (box padding)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, g, b = _rgb(color)
    faint, strong = (r, g, b, 70), (r, g, b, 150)
    u = size / side
    lo, hi = pad * u, (pad + 24) * u - 1
    m = SAFE_MARGIN * u
    d.rectangle((lo, lo, hi, hi), outline=faint)
    d.rectangle((lo + m, lo + m, hi - m, hi - m), outline=strong)
    c = (lo + hi) / 2
    d.line((c, lo, c, hi), fill=faint)
    d.line((lo, c, hi, c), fill=faint)
    return img


def suggest_id(filename: str) -> str:
    """'Arrow Left (1).SVG' -> 'arrow-left-1'. Empty string if nothing usable."""
    stem = re.sub(r"\.svg$", "", filename.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def flow_layout(sizes: list[tuple[int, int]], width: int, gap: int = 6) -> tuple[list[tuple[int, int]], int]:
    """Left-to-right wrapping layout. Returns (top-left position per item, total height).
    An item wider than `width` still gets its own row."""
    pos, x, y, row_h = [], 0, 0, 0
    for w, h in sizes:
        if x > 0 and x + w > width:
            x, y, row_h = 0, y + row_h + gap, 0
        pos.append((x, y))
        x += w + gap
        row_h = max(row_h, h)
    return pos, (y + row_h if sizes else 0)
