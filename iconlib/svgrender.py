"""Minimal renderer for the icon SVG subset (SPEC.md section 3), built on Pillow only.

Supported: path (M L H V C S Q T A Z, absolute + relative), line, polyline, polygon, circle,
ellipse, rect (with rx/ry); fill / stroke / stroke-width as attributes or in style="...";
inherited from the root <svg>. Not supported (by design): transforms, gradients, opacity,
filters, text, groups' own styling, markers.

Known simplifications:
  * Strokes always use round caps and round joins (the Lucide-style convention).
  * Fills use even-odd for shapes with several sub-paths (same as nonzero for normal icons).

Roles: #000000 = main, #FF0000 = shade, #0000FF = light. Any other color is left as drawn.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageColor, ImageDraw

ROLE_OF = {"#000000": "main", "#ff0000": "shade", "#0000ff": "light"}
ROLES = ("main", "shade", "light")
Point = tuple[float, float]


# ----------------------------------------------------------------------------- model
@dataclass
class Shape:
    subpaths: list[list[Point]]
    closed: list[bool]
    fill: str | None            # normalized "#rrggbb" or None
    stroke: str | None
    stroke_width: float


@dataclass
class Icon:
    shapes: list[Shape]
    viewbox: tuple[float, float, float, float] = (0, 0, 24, 24)
    warnings: list[str] = field(default_factory=list)

    @property
    def roles_used(self) -> set[str]:
        out = set()
        for s in self.shapes:
            for c in (s.fill, s.stroke):
                if c in ROLE_OF:
                    out.add(ROLE_OF[c])
        return out

    @property
    def has_explicit_tones(self) -> bool:
        """True when the artist assigned shade/light roles by hand (auto depth is skipped)."""
        return bool(self.roles_used & {"shade", "light"})


# ----------------------------------------------------------------------------- colors
def norm_color(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("", "none", "transparent"):
        return None
    if v == "currentcolor":
        return "#000000"
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        v = "#" + "".join(ch * 2 for ch in v[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return v
    try:
        r, g, b = ImageColor.getrgb(v)[:3]
        return f"#{r:02x}{g:02x}{b:02x}"
    except ValueError:
        return "#000000"


# ----------------------------------------------------------------------------- path parsing
_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARGS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}


class _Scanner:
    def __init__(self, d: str):
        self.d, self.i = d, 0

    def skip(self):
        while self.i < len(self.d) and self.d[self.i] in " \t\r\n,":
            self.i += 1

    def more_numbers(self) -> bool:
        self.skip()
        return self.i < len(self.d) and (self.d[self.i] in "+-." or self.d[self.i].isdigit())

    def command(self) -> str | None:
        self.skip()
        if self.i < len(self.d) and self.d[self.i].isalpha():
            c = self.d[self.i]
            self.i += 1
            return c
        return None

    def number(self) -> float:
        self.skip()
        m = _NUM.match(self.d, self.i)
        if not m:
            raise ValueError(f"bad path data near {self.d[self.i:self.i + 12]!r}")
        self.i = m.end()
        return float(m.group())

    def flag(self) -> int:
        self.skip()
        ch = self.d[self.i]
        if ch not in "01":
            raise ValueError("bad arc flag")
        self.i += 1
        return int(ch)


def _cubic(p0, p1, p2, p3) -> list[Point]:
    length = sum(math.dist(a, b) for a, b in ((p0, p1), (p1, p2), (p2, p3)))
    n = max(8, int(length * 4))
    out = []
    for k in range(1, n + 1):
        t = k / n
        u = 1 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


def _arc(p0: Point, rx: float, ry: float, phi_deg: float, large: int, sweep: int, p1: Point) -> list[Point]:
    """SVG endpoint arc -> points (implementation notes F.6.5)."""
    (x1, y1), (x2, y2) = p0, p1
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p**2 / rx**2 + y1p**2 / ry**2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(8, int(abs(dth) * max(rx, ry) * 2))
    out = []
    for k in range(1, n + 1):
        t = th1 + dth * k / n
        x = cp * rx * math.cos(t) - sp * ry * math.sin(t) + cx
        y = sp * rx * math.cos(t) + cp * ry * math.sin(t) + cy
        out.append((x, y))
    out[-1] = p1
    return out


def parse_path(d: str) -> tuple[list[list[Point]], list[bool]]:
    sc = _Scanner(d)
    subs: list[list[Point]] = []
    closed: list[bool] = []
    cur: Point = (0.0, 0.0)
    start: Point = cur
    pts: list[Point] = []
    last_ctrl: Point | None = None     # for S
    last_q: Point | None = None        # for T
    cmd = None

    def finish(is_closed: bool):
        nonlocal pts
        if len(pts) > 1 or (pts and is_closed):
            subs.append(pts)
            closed.append(is_closed)
        pts = []

    while True:
        c = sc.command()
        if c is None:
            if cmd is None or not sc.more_numbers():
                break
            c = cmd if cmd not in "Mm" else ("L" if cmd == "M" else "l")   # implicit repeat
        cmd = c
        lo, rel = c.lower(), c.islower()
        if lo not in _ARGS:
            raise ValueError(f"unsupported path command {c!r}")
        if lo == "z":
            finish(True)
            cur = start
            last_ctrl = last_q = None
            continue
        first = True
        while first or sc.more_numbers():
            first = False
            ox, oy = cur if rel else (0.0, 0.0)
            if lo == "m":
                finish(False)
                cur = (sc.number() + ox, sc.number() + oy)
                start = cur
                pts = [cur]
                cmd = "l" if rel else "L"   # following pairs are lineto
                lo, rel = "l", rel
                last_ctrl = last_q = None
                continue
            if lo == "l":
                cur = (sc.number() + ox, sc.number() + oy)
                pts.append(cur)
                last_ctrl = last_q = None
            elif lo == "h":
                cur = (sc.number() + ox, cur[1])
                pts.append(cur)
                last_ctrl = last_q = None
            elif lo == "v":
                cur = (cur[0], sc.number() + oy)
                pts.append(cur)
                last_ctrl = last_q = None
            elif lo == "c":
                p1 = (sc.number() + ox, sc.number() + oy)
                p2 = (sc.number() + ox, sc.number() + oy)
                p3 = (sc.number() + ox, sc.number() + oy)
                pts += _cubic(cur, p1, p2, p3)
                cur, last_ctrl, last_q = p3, p2, None
            elif lo == "s":
                p1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                p2 = (sc.number() + ox, sc.number() + oy)
                p3 = (sc.number() + ox, sc.number() + oy)
                pts += _cubic(cur, p1, p2, p3)
                cur, last_ctrl, last_q = p3, p2, None
            elif lo in "qt":
                if lo == "q":
                    q = (sc.number() + ox, sc.number() + oy)
                else:
                    q = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
                p3 = (sc.number() + ox, sc.number() + oy)
                p1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
                p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
                pts += _cubic(cur, p1, p2, p3)
                cur, last_q, last_ctrl = p3, q, None
            elif lo == "a":
                rx, ry, rot = sc.number(), sc.number(), sc.number()
                large, sweep = sc.flag(), sc.flag()
                p3 = (sc.number() + ox, sc.number() + oy)
                pts += _arc(cur, rx, ry, rot, large, sweep, p3)
                cur, last_ctrl, last_q = p3, None, None
    finish(False)
    return subs, closed


# ----------------------------------------------------------------------------- svg parsing
def _attrs(el: ET.Element) -> dict[str, str]:
    a = dict(el.attrib)
    for part in a.pop("style", "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            a[k.strip()] = v.strip()
    return a


def _f(a: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(re.match(_NUM, a.get(key, "")).group())
    except (AttributeError, ValueError):
        return default


def _ellipse_d(cx, cy, rx, ry) -> str:
    return (f"M{cx - rx} {cy}A{rx} {ry} 0 1 0 {cx + rx} {cy}A{rx} {ry} 0 1 0 {cx - rx} {cy}Z")


def _rect_d(x, y, w, h, rx, ry) -> str:
    if rx <= 0 and ry <= 0:
        return f"M{x} {y}H{x + w}V{y + h}H{x}Z"
    rx = min(rx or ry, w / 2)
    ry = min(ry or rx, h / 2)
    return (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}V{y + h - ry}"
            f"A{rx} {ry} 0 0 1 {x + w - rx} {y + h}H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
            f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")


def _points(s: str) -> list[Point]:
    nums = [float(n) for n in _NUM.findall(s)]
    return list(zip(nums[0::2], nums[1::2]))


_SHAPES = {"path", "line", "polyline", "polygon", "circle", "ellipse", "rect"}


def parse_svg(text: str) -> Icon:
    root = ET.fromstring(text)
    vb = (0.0, 0.0, 24.0, 24.0)
    if root.get("viewBox"):
        nums = [float(n) for n in _NUM.findall(root.get("viewBox"))]
        if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            vb = tuple(nums)
    base = _attrs(root)
    icon = Icon(shapes=[], viewbox=vb)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "svg" or tag not in _SHAPES:
            if tag not in ("svg", "title", "desc") and el is not root:
                icon.warnings.append(f"ignored <{tag}>")
            continue
        a = {**base, **_attrs(el)}
        if tag == "path":
            subs, closed = parse_path(a.get("d", ""))
        elif tag == "line":
            subs, closed = [[(_f(a, "x1"), _f(a, "y1")), (_f(a, "x2"), _f(a, "y2"))]], [False]
        elif tag in ("polyline", "polygon"):
            subs, closed = [_points(a.get("points", ""))], [tag == "polygon"]
        elif tag == "circle":
            r = _f(a, "r")
            subs, closed = parse_path(_ellipse_d(_f(a, "cx"), _f(a, "cy"), r, r))
        elif tag == "ellipse":
            subs, closed = parse_path(_ellipse_d(_f(a, "cx"), _f(a, "cy"), _f(a, "rx"), _f(a, "ry")))
        else:
            subs, closed = parse_path(_rect_d(_f(a, "x"), _f(a, "y"), _f(a, "width"), _f(a, "height"),
                                              _f(a, "rx"), _f(a, "ry")))
        fill = norm_color(a["fill"]) if "fill" in a else "#000000"     # SVG default is black
        stroke = norm_color(a.get("stroke"))
        icon.shapes.append(Shape(subs, closed, fill, stroke, _f(a, "stroke-width", 1.0)))
        for key in ("transform", "opacity", "fill-opacity", "stroke-opacity", "filter"):
            if key in a:
                icon.warnings.append(f"<{tag}> {key} is not supported")
    return icon


# ----------------------------------------------------------------------------- rendering
def _rgba(color: str) -> tuple[int, int, int, int]:
    r, g, b = ImageColor.getrgb(color)[:3]
    return r, g, b, 255


def _resolve(color: str | None, palette: dict[str, str] | None) -> str | None:
    if color is None or palette is None:
        return color
    role = ROLE_OF.get(color)
    return palette.get(role, color) if role else color


def _layer(canvas: Image.Image, color: str, mask: Image.Image):
    layer = Image.new("RGBA", canvas.size, _rgba(color))
    layer.putalpha(mask)
    canvas.alpha_composite(layer)


def _draw_shape(canvas, shape: Shape, fill, stroke, s, ox, oy, dx, dy, sw_override):
    def tx(p):
        return ((p[0] + dx - ox) * s, (p[1] + dy - oy) * s)

    if fill:
        mask = None
        for sub in shape.subpaths:
            if len(sub) < 3:
                continue
            m = Image.new("L", canvas.size, 0)
            ImageDraw.Draw(m).polygon([tx(p) for p in sub], fill=255)
            mask = m if mask is None else ImageChops.difference(mask, m)    # even-odd
        if mask is not None:
            _layer(canvas, fill, mask)
    if stroke:
        width = max(1.0, (sw_override or shape.stroke_width) * s)
        mask = Image.new("L", canvas.size, 0)
        d = ImageDraw.Draw(mask)
        for sub, closed in zip(shape.subpaths, shape.closed):
            pts = [tx(p) for p in sub]
            if closed and len(pts) > 2:
                pts = pts + [pts[0]]
            _stroke_polyline(d, pts, width / 2)
        _layer(canvas, stroke, mask)


def _stroke_polyline(d: ImageDraw.ImageDraw, pts: list[Point], r: float):
    """Round-capped, round-joined stroke: one quad per segment plus a disc wherever the path
    turns (and at both ends); even gentle turns need one, or thick curves show streaks. Pillow's own wide lines leave ticks on dense curves."""
    def disc(p):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=255)

    segs = [(a, b) for a, b in zip(pts, pts[1:]) if a != b]
    if not segs:
        if pts:
            disc(pts[0])
        return
    disc(segs[0][0])
    prev_dir = None
    for a, b in segs:
        length = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = -uy * r, ux * r
        d.polygon([(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)],
                  fill=255)
        if prev_dir is not None and (ux * prev_dir[0] + uy * prev_dir[1]) < 0.99999:    # any turn above ~0.25 degrees
            disc(a)
        prev_dir = (ux, uy)
    disc(segs[-1][1])


def render(icon: Icon, size: int = 48, palette: dict[str, str] | None = None, depth: float = 0.0,
           stroke_width: float | None = None, supersample: int = 4, pad: float = 0.0,
           box: tuple[float, str] | None = None) -> Image.Image:
    """Render to a transparent RGBA image of size x size.

    palette: {"main": "#rrggbb", "shade": ..., "light": ...}; None keeps colors as drawn.
    depth:   automatic three-tone offset in icon units (0 = off, ~0.5 typical). Ignored when the
             icon has explicit shade/light roles. Needs palette shade/light (else role colors).
    stroke_width: overrides every shape's stroke width (icon units).
    pad:     extra space around the icon canvas, in icon units (the output grows to fit it).
    box:     (corner radius in icon units, fill color): a background box behind the icon, filling
             the whole output; a radius of half the side makes a circle.
    """
    vx, vy, vw, vh = icon.viewbox
    n = size * supersample
    s = n / (max(vw, vh) + 2 * pad)
    vx, vy = vx - pad, vy - pad
    canvas = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    if box is not None:
        corner, color = box
        ImageDraw.Draw(canvas).rounded_rectangle((0, 0, n - 1, n - 1), radius=min(corner * s, (n - 1) / 2),
                                                 fill=_rgba(color))
    pal = palette or {}

    if depth > 0 and not icon.has_explicit_tones:
        for role, sign in (("shade", 1), ("light", -1)):
            color = pal.get(role, {"shade": "#ff0000", "light": "#0000ff"}[role])
            for sh in icon.shapes:
                _draw_shape(canvas, sh, color if sh.fill else None, color if sh.stroke else None,
                            s, vx, vy, sign * depth, sign * depth, stroke_width)
    for sh in icon.shapes:
        _draw_shape(canvas, sh, _resolve(sh.fill, palette), _resolve(sh.stroke, palette),
                    s, vx, vy, 0, 0, stroke_width)
    return canvas.resize((size, size), Image.BOX) if supersample > 1 else canvas


def load(path) -> Icon:
    from pathlib import Path
    return parse_svg(Path(path).read_text(encoding="utf-8"))
