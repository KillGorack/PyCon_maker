"""Import cleaner: turn an Inkscape (or hand-written) SVG into the library's plain form.

Drops editor data (sodipodi/inkscape namespaces, metadata, defs, title, ids, layers' labels),
flattens groups into the shapes they contain, resolves inherited styling onto each shape and
writes explicit presentation attributes.

Transforms (Inkscape puts them on layers and objects even if you never grouped anything) are baked
into the coordinates, so the library only ever holds plain shapes. A page that is not 24x24 is
placed on the 24x24 canvas: centered at 1:1 if it is smaller, scaled down to fit if it is larger.

Anything the renderer/exporters can't honor is reported:
  errors   -> the file cannot be imported (not SVG, text/images, nothing to draw ...)
  warnings -> imported, but check it (non-role colors, canvas moved, opacity ...)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .pathdata import (IDENTITY, Matrix, is_identity, is_uniform, mul, parse_segments, parse_transform,
                       points_to_segments, scale_factor, to_d, transform_segments)
from .pathdata import fmt as _fmt
from .svgrender import ROLE_OF, _ellipse_d, _f, _points, _rect_d, norm_color

SVG_NS = "http://www.w3.org/2000/svg"
CANVAS = (0.0, 0.0, 24.0, 24.0)
_SHAPES = {"path", "line", "polyline", "polygon", "circle", "ellipse", "rect"}
_GEOMETRY = {
    "path": ("d",), "line": ("x1", "y1", "x2", "y2"), "polyline": ("points",), "polygon": ("points",),
    "circle": ("cx", "cy", "r"), "ellipse": ("cx", "cy", "rx", "ry"),
    "rect": ("x", "y", "width", "height", "rx", "ry"),
}
_PAINT = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin")
_INHERITED = _PAINT + ("opacity", "fill-opacity", "stroke-opacity")
_IGNORED = {"metadata", "defs", "title", "desc", "namedview"}
_UNSUPPORTED = ("opacity", "fill-opacity", "stroke-opacity", "filter", "clip-path", "mask")


class CleanError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class CleanResult:
    svg: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _local(name: str) -> str:
    return name.split("}")[-1]


def _style(el: ET.Element) -> dict[str, str]:
    out = {_local(k): v for k, v in el.attrib.items() if "}" not in k}
    for part in out.pop("style", "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _num(v: str) -> str:
    try:
        f = float(re.match(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", v).group())
    except (AttributeError, ValueError):
        return v
    return f"{f:.4f}".rstrip("0").rstrip(".") or "0"


def clean_svg(text: str) -> CleanResult:
    res = CleanResult()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        res.errors.append(f"not valid SVG/XML ({e})")
        return res
    if _local(root.tag) != "svg":
        res.errors.append("root element is not <svg>")
        return res

    vb = CANVAS
    if root.get("viewBox"):
        nums = [float(n) for n in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", root.get("viewBox"))]
        if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            vb = tuple(nums)
    else:
        res.warnings.append("no viewBox; assuming 0 0 24 24")
    base: Matrix = IDENTITY
    if any(abs(x - y) > 1e-6 for x, y in zip(vb, CANVAS)):
        # smaller page: keep the drawn size, centered. Larger page: scale down to fit.
        vx, vy, vw, vh = vb
        k = 1.0 if max(vw, vh) <= CANVAS[2] else CANVAS[2] / max(vw, vh)
        base = (k, 0.0, 0.0, k, (CANVAS[2] - vw * k) / 2 - vx * k, (CANVAS[3] - vh * k) / 2 - vy * k)
        how = "centered on" if k == 1.0 else f"scaled by {k:.3g} to fit"
        res.warnings.append(f"canvas was {vw:g}x{vh:g}; {how} the 24x24 canvas")

    shapes: list[tuple[str, dict[str, str]]] = []
    seen_colors: set[str] = set()
    seen_problem: set[str] = set()

    def shape_segments(tag: str, st: dict[str, str]):
        if tag == "path":
            return parse_segments(st.get("d", ""))
        if tag == "line":
            return points_to_segments([(_f(st, "x1"), _f(st, "y1")), (_f(st, "x2"), _f(st, "y2"))], False)
        if tag in ("polyline", "polygon"):
            return points_to_segments(_points(st.get("points", "")), tag == "polygon")
        if tag == "rect":
            d = _rect_d(_f(st, "x"), _f(st, "y"), _f(st, "width"), _f(st, "height"), _f(st, "rx"), _f(st, "ry"))
        else:
            r = _f(st, "r")
            rx, ry = (r, r) if tag == "circle" else (_f(st, "rx"), _f(st, "ry"))
            d = _ellipse_d(_f(st, "cx"), _f(st, "cy"), rx, ry)
        return parse_segments(d)

    def walk(el: ET.Element, inherited: dict[str, str], ctm: Matrix):
        for child in el:
            tag = _local(child.tag)
            if tag in _IGNORED:
                continue
            st = _style(child)
            for bad in _UNSUPPORTED:
                if bad.endswith("opacity") and _num(st.get(bad, "1")) == "1":
                    continue                                   # fully opaque is the default: nothing to warn about
                if bad in st and f"{tag}:{bad}" not in seen_problem:
                    seen_problem.add(f"{tag}:{bad}")
                    res.warnings.append(f"<{tag}> uses {bad} (not supported; ignored)")
            try:
                m = mul(ctm, parse_transform(st.get("transform", "")))
            except ValueError as e:
                if "transform" not in seen_problem:
                    seen_problem.add("transform")
                    res.errors.append(f"<{tag}>: {e}")
                continue
            merged = {**inherited, **{k: v for k, v in st.items() if k in _INHERITED}}
            if tag == "g":
                walk(child, merged, m)
            elif tag in _SHAPES:
                if is_identity(m):
                    attrs = {k: _num(st[k]) if k != "d" and k != "points" else st[k]
                             for k in _GEOMETRY[tag] if k in st}
                else:                                           # bake the transform into the coordinates
                    try:
                        attrs = {"d": to_d(transform_segments(shape_segments(tag, st), m))}
                    except (ValueError, ZeroDivisionError) as e:
                        res.errors.append(f"<{tag}>: cannot read its shape ({e})")
                        continue
                    tag = "path"
                    if not is_uniform(m) and "uniform" not in seen_problem:
                        seen_problem.add("uniform")
                        res.warnings.append("a shape was stretched unevenly; its line thickness is approximate")
                for k in _PAINT:
                    if k in merged:
                        attrs[k] = _num(merged[k]) if k == "stroke-width" else merged[k]
                if not is_identity(m) and norm_color(attrs.get("stroke")):
                    width = float(_num(attrs.get("stroke-width", "1")) or 1)
                    attrs["stroke-width"] = _fmt(width * scale_factor(m))      # thickness scales with the drawing
                shapes.append((tag, attrs))
            elif tag not in ("svg",):
                if f"<{tag}>" not in seen_problem:
                    seen_problem.add(f"<{tag}>")
                    res.errors.append(f"<{tag}> is not supported (convert text/images to paths)")

    root_paint = {k: v for k, v in _style(root).items() if k in _INHERITED}
    walk(root, root_paint, base)
    if not shapes and not res.errors:
        res.errors.append("no drawable shapes found")
    if res.errors:
        return res

    out = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": " ".join(f"{n:g}" for n in CANVAS)})
    for tag, attrs in shapes:
        for key in ("fill", "stroke"):
            if key in attrs:
                col = norm_color(attrs[key])
                attrs[key] = col or "none"
                if col and col not in ROLE_OF and col not in seen_colors:
                    seen_colors.add(col)
                    res.warnings.append(f"color {col} is not a role color (main #000000, shade #ff0000, "
                                        f"light #0000ff); it will not follow themes")
        if "fill" not in attrs:
            attrs["fill"] = "none" if "stroke" in attrs else "#000000"
        if attrs.get("stroke", "none") != "none":
            attrs.setdefault("stroke-width", "1")
        # canonical attribute order (geometry, then paint), so cleaning twice gives identical text
        attrs = {**{k: v for k, v in attrs.items() if k not in _PAINT}, **{k: attrs[k] for k in _PAINT if k in attrs}}
        ET.SubElement(out, tag, attrs)
    ET.indent(out, space="  ")
    xml = ET.tostring(out, encoding="unicode")
    res.svg = xml + "\n"
    return res
