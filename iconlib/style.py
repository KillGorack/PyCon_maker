"""Style + Theme: how an icon is presented, kept separate from the artwork (SPEC.md sections 5-7).

One engine for everything: the grid, the preview and PNG export call `compose()`; the SVG export
(step 7) uses the same `Style.geometry()` numbers, so what you preview is what you export.
Nothing here touches the master SVG files.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from PIL import Image, ImageDraw

from .preview import _rgb, guides, mix, tone_palette
from .svgrender import Icon, render

BOXES = ("none", "square", "rounded", "circle")
CANVAS = 24.0
DEFAULT_DEPTH = 0.30          # offset (icon units) used when depth is switched on


def is_hex(value) -> bool:
    return isinstance(value, str) and len(value) == 7 and value[0] == "#" and all(
        c in "0123456789abcdefABCDEF" for c in value[1:])


@dataclass(frozen=True)
class Theme:
    """Named colors: the three tonal roles, the box fill, and (preview only) the page color."""
    name: str
    main: str
    shade: str
    light: str
    box: str
    bg: str | None = None            # what the icon sits on, for previews; never exported

    @property
    def palette(self) -> dict[str, str]:
        return {"main": self.main, "shade": self.shade, "light": self.light}

    @classmethod
    def derived(cls, name: str, main: str, box: str, bg: str | None = None, strength: float = 0.45) -> "Theme":
        p = tone_palette(main, strength)
        return cls(name, main, p["shade"], p["light"], box, bg)

    def validate(self):
        for k in ("main", "shade", "light", "box"):
            if not is_hex(getattr(self, k)):
                raise ValueError(f"{k} must be a color like #1a2b3c")
        if self.bg is not None and not is_hex(self.bg):
            raise ValueError("bg must be a color like #1a2b3c")
        if not self.name.strip():
            raise ValueError("a theme needs a name")


@dataclass(frozen=True)
class Geometry:
    pad: float            # space around the 24-unit canvas, in units
    side: float           # total side length in units (canvas + 2 * pad)
    corner: float         # box corner radius in units (0 = square)
    boxed: bool


@dataclass(frozen=True)
class Style:
    box: str = "none"            # none | square | rounded | circle
    padding: float = 0.0         # units added around the icon (only with a box)
    radius: float = 0.25         # corner radius as a fraction of the box side (rounded only), 0..0.5
    depth: float = 0.0           # automatic three-tone offset in units; 0 = off
    stroke: float | None = None  # override every stroke width (units); None = as drawn

    def __post_init__(self):
        if self.box not in BOXES:
            raise ValueError(f"box must be one of {BOXES}")
        if not (0 <= self.padding <= 12 and 0 <= self.radius <= 0.5 and 0 <= self.depth <= 2):
            raise ValueError("padding 0-12, radius 0-0.5, depth 0-2")
        if self.stroke is not None and not (0.25 <= self.stroke <= 6):
            raise ValueError("stroke must be 0.25-6 units")

    def geometry(self, canvas: float = CANVAS) -> Geometry:
        boxed = self.box != "none"
        pad = self.padding if boxed else 0.0
        side = canvas + 2 * pad
        corner = {"none": 0.0, "square": 0.0, "rounded": self.radius * side, "circle": side / 2}[self.box]
        return Geometry(pad, side, corner, boxed)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Style":
        """Tolerant load: unknown keys are ignored, bad values fall back to the default style."""
        try:
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except (TypeError, ValueError):
            return cls()

    def with_(self, **kw) -> "Style":
        return replace(self, **kw)


def compose(icon: Icon, size: int, style: Style, theme: Theme, allow_depth: bool = True,
            guide_color: str | None = None, backdrop: bool = False) -> Image.Image:
    """The icon exactly as an export would draw it. `allow_depth` is the icon's own flag
    (depth: auto). `backdrop` puts the theme's page color behind an un-boxed icon (previews only);
    `guide_color` adds the safe-area guides on top (previews only)."""
    g = style.geometry()
    depth = style.depth if (allow_depth and style.depth > 0) else 0.0
    art = render(icon, size, theme.palette, depth, style.stroke, pad=g.pad,
                 box=(g.corner, theme.box) if g.boxed else None)
    if backdrop and theme.bg and not g.boxed:          # with a box, everything outside it stays transparent
        base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(base).rounded_rectangle((0, 0, size - 1, size - 1), radius=max(2, size // 12),
                                               fill=_rgb(theme.bg) + (255,))
        base.alpha_composite(art)
        art = base
    if guide_color:
        art.alpha_composite(guides(size, guide_color, g.side, g.pad))
    return art


BUILTIN_THEMES: tuple[Theme, ...] = (
    Theme.derived("Dave dark", "#d4d4d4", "#333333", "#171717"),
    Theme.derived("Dave light", "#332d24", "#cbc2ae", "#ded6c3"),
    Theme.derived("Ocean", "#2dd4bf", "#0f2b33", "#0b1c22"),
    Theme.derived("Amber", "#f59e0b", "#2b1d08", "#1a1206"),
)
