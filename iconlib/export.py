"""Export: write a set of icons to a folder in a chosen style (SPEC.md section 5).

Reads the master library, never writes to it. The same Style/Theme the preview uses.

Formats
  svg     one file per icon: svg/<id>.svg
  sprite  one icons-sprite.svg with a <symbol id="icon-<id>"> per icon (use with <use href=...>)
  png     baked colors, transparent: png/[<theme>/]<size>px/<id>.png
Color modes
  themed  CSS variables (style="...var(--icon-main,#fallback)") on top of plain color attributes, so viewers
          that don't know CSS variables still show the default theme; plus icons-theme.css (one block per
          theme: [data-theme="<name>"]). Variables: --icon-main, --icon-shade, --icon-light, --icon-box.
  baked   fixed hex colors (for tools that don't understand CSS variables). With several themes
          the files go to svg/<theme>/...
Every export folder gets manifest.json (what/how) and README.txt (how to use it).
"""
from __future__ import annotations

import io
import json
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .clean import clean_svg
from .collections import slugify
from .library import Library
from .style import Style, Theme, compose
from .svgrender import ROLE_OF, load, parse_svg

MANIFEST = "manifest.json"
ROLE_VAR = {"main": "--icon-main", "shade": "--icon-shade", "light": "--icon-light"}
_STRIP = {"fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin"}


class ExportError(ValueError):
    pass


@dataclass
class ExportOptions:
    name: str = "icons"
    svg: bool = True
    sprite: bool = True
    png: bool = False
    mode: str = "themed"                  # themed | baked
    svg_size: int = 48                    # width/height of the standalone SVG files (px)
    png_sizes: tuple[int, ...] = (32, 64)
    current_color: bool = False           # themed mode: main falls back to currentColor, not the theme color

    def validate(self):
        if self.mode not in ("themed", "baked"):
            raise ExportError("mode must be themed or baked")
        if not (self.svg or self.sprite or self.png):
            raise ExportError("pick at least one format")
        if not 8 <= self.svg_size <= 2048:
            raise ExportError("SVG size must be 8-2048 px")
        if self.png and not self.png_sizes:
            raise ExportError("give at least one PNG size")
        if any(not 8 <= s <= 2048 for s in self.png_sizes):
            raise ExportError("PNG sizes must be 8-2048 px")


@dataclass
class ExportResult:
    out_dir: Path
    files: list[str]
    icons: list[str]
    flat: list[str] = field(default_factory=list)       # icons that stay flat although depth is on
    skipped: list[str] = field(default_factory=list)    # icons that could not be exported (with the reason)


# ----------------------------------------------------------------------------- svg building
def _n(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def _paint(color: str, theme: Theme, themed: bool, current_color: bool) -> tuple[str, str | None]:
    """(plain color, CSS-variable form or None). The plain color goes in an attribute that every viewer
    understands; the variable form goes in style="" for browsers, which prefer it (themeable)."""
    role = ROLE_OF.get(color)
    if color == "none" or role is None:
        return color, None                              # off-role colors stay exactly as drawn
    base = getattr(theme, role)
    if not themed:
        return base, None
    return base, f"var({ROLE_VAR[role]},{'currentColor' if role == 'main' and current_color else base})"


def _shape(tag: str, attrs: dict, fill: tuple[str, str | None], stroke: tuple[str, str | None],
           width: str | None) -> str:
    """Plain attributes always; a style="" with var() on top only where a variable applies. Viewers that
    don't know CSS variables (Inkscape, librsvg, many image viewers) ignore the style and use the plain color."""
    geo = "".join(f" {k}={quoteattr(v)}" for k, v in attrs.items() if k not in _STRIP)
    stroked = stroke[0] != "none"
    paint = f' fill="{fill[0]}"' + (f' stroke="{stroke[0]}" stroke-width="{width}"' if stroked else "")
    css = ";".join([f"fill:{fill[1]}"] * bool(fill[1]) + [f"stroke:{stroke[1]}"] * (stroked and bool(stroke[1])))
    return f"<{tag}{geo}{paint}" + (f' style="{css}"' if css else "") + "/>"


def _body(svg_text: str, style: Style, theme: Theme, themed: bool, allow_depth: bool,
          current_color: bool) -> tuple[str, float]:
    """The drawing (box + icon [+ depth ghosts]) as SVG elements, and the output side length in units."""
    cleaned = clean_svg(svg_text)
    if cleaned.errors:
        raise ExportError("; ".join(cleaned.errors))
    g = style.geometry()
    root = ET.fromstring(cleaned.svg)
    shapes = [(el.tag.split("}")[-1], dict(el.attrib)) for el in root]
    parts: list[str] = []

    def paint(c: str) -> tuple[str, str | None]:
        return _paint(c, theme, themed, current_color)

    if g.boxed:
        corner = f' rx="{_n(g.corner)}"' if g.corner else ""
        css = f' style="fill:var(--icon-box,{theme.box})"' if themed else ""
        parts.append(f'<rect width="{_n(g.side)}" height="{_n(g.side)}"{corner} fill="{theme.box}"{css}/>')

    def group(dx: float, dy: float, ghost: str | None) -> list[str]:
        out = []
        for tag, a in shapes:
            fill, stroke = a.get("fill", "none"), a.get("stroke", "none")
            width = _n(style.stroke) if style.stroke is not None else a.get("stroke-width", "1")
            if ghost:
                fill = paint(ghost) if fill != "none" else ("none", None)
                stroke = paint(ghost) if stroke != "none" else ("none", None)
            else:
                fill, stroke = paint(fill), paint(stroke)
            out.append(_shape(tag, a, fill, stroke, width))
        x, y = g.pad + dx, g.pad + dy
        if x or y:
            return [f'<g transform="translate({_n(x)} {_n(y)})">', *("  " + o for o in out), "</g>"]
        return out

    explicit = parse_svg(cleaned.svg).has_explicit_tones
    if style.depth > 0 and allow_depth and not explicit:
        parts += group(style.depth, style.depth, "#ff0000")         # shade: down-right, behind
        parts += group(-style.depth, -style.depth, "#0000ff")       # light: up-left, behind
    parts += group(0, 0, None)
    return "\n  ".join(parts), g.side


def _flat_when_depth_on(svg_text: str, style: Style, allow_depth: bool) -> bool:
    return style.depth > 0 and (not allow_depth or parse_svg(clean_svg(svg_text).svg).has_explicit_tones)


def svg_document(svg_text: str, style: Style, theme: Theme, themed: bool, allow_depth: bool = True,
                 size: int | None = 48, current_color: bool = False) -> str:
    body, side = _body(svg_text, style, theme, themed, allow_depth, current_color)
    wh = f' width="{size}" height="{size}"' if size else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg"{wh} viewBox="0 0 {_n(side)} {_n(side)}" '
            f'stroke-linecap="round" stroke-linejoin="round">\n  {body}\n</svg>\n')


def symbol(icon_id: str, svg_text: str, style: Style, theme: Theme, themed: bool, allow_depth: bool,
           current_color: bool) -> str:
    body, side = _body(svg_text, style, theme, themed, allow_depth, current_color)
    return (f'<symbol id="icon-{icon_id}" viewBox="0 0 {_n(side)} {_n(side)}" '
            f'stroke-linecap="round" stroke-linejoin="round">\n  {body}\n</symbol>')


def theme_css(themes: list[Theme]) -> str:
    lines = ['/* Generated by Icon Library. Put data-theme="<name>" on <html> (or any ancestor) to pick a theme.',
             '   Inline the SVG or use the sprite; an <img> tag cannot see these variables and shows the default theme. */']
    for i, t in enumerate(themes):
        sel = f'[data-theme="{slugify(t.name)}"]'
        lines.append(f"{':root,' + chr(10) if i == 0 else ''}{sel} {{")
        for var, val in (("main", t.main), ("shade", t.shade), ("light", t.light), ("box", t.box)):
            lines.append(f"  --icon-{var}: {val};")
        lines.append("}")
    return "\n".join(lines) + "\n"


def _readme(ids: list[str], style: Style, themes: list[Theme], o: ExportOptions) -> str:
    t0 = slugify(themes[0].name)
    L = [f"{o.name}: {len(ids)} icons, exported by Icon Library.", "",
         f"Style: box={style.box}, padding={style.padding:g}, depth={'off' if not style.depth else style.depth}"
         + (f", stroke={style.stroke:g}" if style.stroke is not None else "") + ".",
         "Themes: " + ", ".join(t.name for t in themes) + f"  (default: {themes[0].name}).", ""]
    if o.mode == "themed" and (o.svg or o.sprite):
        L += ["THEMING", f'  Link icons-theme.css, then set data-theme="{t0}" (or another theme name) on <html>.',
              "  Colors come from CSS variables --icon-main / --icon-shade / --icon-light / --icon-box.",
              "  Override any of them in your own CSS to recolor icons without re-exporting.", ""]
    if o.svg:
        L += ["SVG FILES  (svg/)",
              "  Inline the file's <svg> in your HTML to theme it. As <img src>, or in an image viewer or editor, it shows",
              "  the default theme.", ""]
    if o.sprite:
        L += ["SPRITE  (icons-sprite.svg)",
              '  <svg width="24" height="24"><use href="icons-sprite.svg#icon-' + (ids[0] if ids else "name") + '"/></svg>',
              "  Serve it from the same origin as the page.", ""]
    if o.png:
        L += [f"PNG  (png/)  sizes: {', '.join(str(s) for s in o.png_sizes)} px, transparent, colors baked in.", ""]
    L += ["Re-exporting to this folder replaces the files listed in manifest.json."]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- planning + writing
def build_files(lib: Library, ids: list[str], style: Style, themes: list[Theme], opts: ExportOptions
                ) -> tuple[dict[str, bytes], ExportResult]:
    """Everything that would be written, in memory. Reads the library; changes nothing."""
    opts.validate()
    if not themes:
        raise ExportError("pick at least one theme")
    slugs = [slugify(t.name) for t in themes]
    if len(set(slugs)) != len(slugs):
        raise ExportError("two of the chosen themes have the same name once simplified")
    for t in themes:
        t.validate()
    ids = sorted(dict.fromkeys(lib.resolve(i) for i in ids))
    if not ids:
        raise ExportError("there are no icons to export")
    themed = opts.mode == "themed"
    files: dict[str, bytes] = {}
    result = ExportResult(Path(), [], [], [], [])
    sprites: dict[str, dict[str, str]] = {slug: {} for slug in slugs}       # theme -> {icon id: <symbol>}
    multi = len(themes) > 1

    for icon_id in ids:
        text = lib.read_svg(icon_id)
        allow = lib.get(icon_id).depth == "auto"
        try:
            if _flat_when_depth_on(text, style, allow):
                result.flat.append(icon_id)
            for theme, slug in zip(themes, slugs):
                if themed and theme is not themes[0]:
                    continue                                    # themed files are theme-independent (variables)
                if opts.svg:
                    folder = f"svg/{slug}/" if (multi and not themed) else "svg/"
                    files[f"{folder}{icon_id}.svg"] = svg_document(
                        text, style, theme, themed, allow, opts.svg_size, opts.current_color).encode()
                if opts.sprite:
                    sprites[slug][icon_id] = symbol(icon_id, text, style, theme, themed, allow, opts.current_color)
            if opts.png:
                icon = load(lib.path(icon_id))
                for theme, slug in zip(themes, slugs):
                    for size in opts.png_sizes:
                        buf = io.BytesIO()
                        compose(icon, size, style, theme, allow).save(buf, "PNG", optimize=True)
                        folder = f"png/{slug}/{size}px/" if multi else f"png/{size}px/"
                        files[f"{folder}{icon_id}.png"] = buf.getvalue()
            result.icons.append(icon_id)
        except (ExportError, ValueError) as e:
            result.skipped.append(f"{icon_id}: {e}")
            for k in [k for k in files if k.rsplit("/", 1)[-1].startswith(icon_id + ".")]:
                del files[k]
    if not result.icons:
        raise ExportError("none of the icons could be exported: " + "; ".join(result.skipped))

    if opts.sprite:
        for theme, slug in zip(themes, slugs):
            if themed and theme is not themes[0]:
                continue
            symbols = [sprites[slug][i] for i in result.icons if i in sprites[slug]]
            name = f"icons-sprite-{slug}.svg" if (multi and not themed) else "icons-sprite.svg"
            files[name] = ('<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n'
                           + "\n".join(symbols) + "\n</svg>\n").encode()
    if themed and (opts.svg or opts.sprite):
        files["icons-theme.css"] = theme_css(themes).encode()
    files["README.txt"] = _readme(result.icons, style, themes, opts).encode()
    return files, result


def _inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child == parent or parent in child.parents


def export(lib: Library, ids: list[str], style: Style, themes: list[Theme], opts: ExportOptions,
           out_dir: str | Path) -> ExportResult:
    out = Path(out_dir)
    if _inside(out, lib.root):
        raise ExportError("choose a folder outside the library (exporting must not touch the master library)")
    files, result = build_files(lib, ids, style, themes, opts)
    old: list[str] = []
    if out.exists():
        if not out.is_dir():
            raise ExportError(f"{out} is not a folder")
        if (out / MANIFEST).exists():
            try:
                old = json.loads((out / MANIFEST).read_text(encoding="utf-8")).get("files", [])
            except (OSError, ValueError):
                raise ExportError(f"{out / MANIFEST} is unreadable; pick another folder")
        elif any(out.iterdir()):
            raise ExportError("that folder isn't empty and wasn't created by Icon Library; pick an empty one")
    manifest = {
        "tool": "Icon Library", "version": 1, "name": opts.name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": opts.mode, "style": style.to_json(), "themes": [vars(t) for t in themes],
        "icons": result.icons, "files": sorted([*files, MANIFEST]),
    }
    for rel in old:                                              # re-export: drop what the last export wrote
        p = out / rel
        if p.is_file() and _inside(p, out):
            p.unlink()
    for rel, data in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for d in sorted((p for p in out.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()                                            # tidy folders a smaller re-export emptied
    result.out_dir, result.files = out, sorted(manifest["files"])
    return result
