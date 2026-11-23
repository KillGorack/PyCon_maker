"""Import cleaner: turn an Inkscape (or hand-written) SVG into the library's plain form.

Drops editor data (sodipodi/inkscape namespaces, metadata, defs, title, ids, layers' labels),
flattens groups into the shapes they contain, resolves inherited styling onto each shape and
writes explicit presentation attributes. Anything the renderer/exporters can't honor is reported:
  errors   -> the file cannot be imported as-is (e.g. transforms; ungroup / apply them in Inkscape)
  warnings -> imported, but check it (non-role colors, canvas not 24x24, opacity ...)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .svgrender import ROLE_OF, norm_color

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
_UNSUPPORTED = ("transform", "opacity", "fill-opacity", "stroke-opacity", "filter", "clip-path", "mask")


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
        if len(nums) == 4:
            vb = tuple(nums)
    else:
        res.warnings.append("no viewBox; assuming 0 0 24 24")
    if vb != CANVAS:
        res.warnings.append(f"canvas is {vb[2]:g}x{vb[3]:g} at {vb[0]:g},{vb[1]:g}; the library expects 0 0 24 24")

    shapes: list[tuple[str, dict[str, str]]] = []
    seen_colors: set[str] = set()
    seen_problem: set[str] = set()

    def walk(el: ET.Element, inherited: dict[str, str]):
        for child in el:
            tag = _local(child.tag)
            if tag in _IGNORED:
                continue
            st = _style(child)
            for bad in _UNSUPPORTED:
                if bad in st and f"{tag}:{bad}" not in seen_problem:
                    seen_problem.add(f"{tag}:{bad}")
                    msg = f"<{tag}> uses {bad}"
                    if bad == "transform":
                        res.errors.append(msg + " (ungroup and apply transforms in Inkscape, then re-export)")
                    else:
                        res.warnings.append(msg + " (not supported; ignored)")
            merged = {**inherited, **{k: v for k, v in st.items() if k in _INHERITED}}
            if tag == "g":
                walk(child, merged)
            elif tag in _SHAPES:
                attrs = {k: _num(st[k]) if k != "d" and k != "points" else st[k]
                         for k in _GEOMETRY[tag] if k in st}
                for k in _PAINT:
                    if k in merged:
                        attrs[k] = _num(merged[k]) if k == "stroke-width" else merged[k]
                shapes.append((tag, attrs))
            elif tag not in ("svg",):
                if f"<{tag}>" not in seen_problem:
                    seen_problem.add(f"<{tag}>")
                    res.errors.append(f"<{tag}> is not supported (convert text/images to paths)")

    root_paint = {k: v for k, v in _style(root).items() if k in _INHERITED}
    walk(root, root_paint)
    if not shapes and not res.errors:
        res.errors.append("no drawable shapes found")
    if res.errors:
        return res

    out = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": " ".join(f"{n:g}" for n in vb)})
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
        ET.SubElement(out, tag, attrs)
    ET.indent(out, space="  ")
    xml = ET.tostring(out, encoding="unicode")
    res.svg = xml + "\n"
    return res
