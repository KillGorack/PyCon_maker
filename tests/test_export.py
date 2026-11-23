"""Step 7: export engine."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

from PIL import Image

from iconlib.export import ExportError, ExportOptions, build_files, export, svg_document
from iconlib.library import Library
from iconlib.style import BUILTIN_THEMES, DEFAULT_DEPTH, Style, compose
from iconlib.svgrender import load

from tests.fixtures import library_dir

DUMMY = library_dir()
DARK, LIGHT, OCEAN = BUILTIN_THEMES[0], BUILTIN_THEMES[1], BUILTIN_THEMES[2]
SVG_NS = "{http://www.w3.org/2000/svg}"


def tree_hash(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "lib"
        shutil.copytree(DUMMY, self.root)
        self.lib = Library(self.root)
        self.out = self.base / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def run_export(self, ids=None, style=None, themes=None, **opts):
        return export(self.lib, ids or self.lib.ids(), style or Style(), themes or [DARK],
                      ExportOptions(**opts), self.out)


class SvgOutput(Base):
    def doc(self, icon_id, style, themed, theme=DARK, **kw):
        return svg_document(self.lib.read_svg(icon_id), style, theme, themed, **kw)

    def test_plain_export_is_valid_xml_with_viewbox_and_size(self):
        root = ET.fromstring(self.doc("plus", Style(), themed=False, size=32))
        self.assertEqual((root.get("viewBox"), root.get("width"), root.get("height")), ("0 0 24 24", "32", "32"))
        self.assertEqual(len(list(root)), 2)                                   # the two strokes of the plus

    def test_box_geometry_matches_style(self):
        root = ET.fromstring(self.doc("plus", Style(box="rounded", padding=3, radius=0.25), themed=False))
        rect = root.find(SVG_NS + "rect")
        self.assertEqual((root.get("viewBox"), rect.get("width"), rect.get("rx")), ("0 0 30 30", "30", "7.5"))
        g = root.find(SVG_NS + "g")
        self.assertEqual(g.get("transform"), "translate(3 3)")                 # icon sits inside the padding
        circle = ET.fromstring(self.doc("plus", Style(box="circle", padding=2), themed=False))
        self.assertEqual(circle.find(SVG_NS + "rect").get("rx"), "14")
        square = ET.fromstring(self.doc("plus", Style(box="square", padding=2), themed=False))
        self.assertIsNone(square.find(SVG_NS + "rect").get("rx"))

    def test_baked_has_literal_colors_and_no_variables(self):
        s = self.doc("plus", Style(box="square", padding=2), themed=False, theme=OCEAN)
        self.assertNotIn("var(", s)
        self.assertIn(f'stroke="{OCEAN.main}"', s)
        self.assertIn(f'fill="{OCEAN.box}"', s)

    def test_themed_uses_variables_on_top_of_plain_colors(self):
        s = self.doc("plus", Style(box="square", padding=2), themed=True, theme=OCEAN)
        self.assertIn(f"var(--icon-main,{OCEAN.main})", s)
        self.assertIn(f"var(--icon-box,{OCEAN.box})", s)
        self.assertIn(f'stroke="{OCEAN.main}"', s)                              # plain colors are there too
        self.assertIn(f'fill="{OCEAN.box}"', s)

    def test_a_viewer_without_css_variables_sees_exactly_the_baked_file(self):
        """Regression: themed files used to carry colors ONLY as var(), so Inkscape, librsvg and most image viewers
        drew a black square (box) and no lines at all. Ignoring every style="" must leave the baked drawing."""
        for icon in ("plus", "shield", "shield-tone", "gem-tone", "home"):
            for style in (Style(), Style(box="rounded", padding=3, depth=0.3, stroke=1.5)):
                themed = self.doc(icon, style, themed=True, theme=OCEAN)
                baked = self.doc(icon, style, themed=False, theme=OCEAN)
                self.assertEqual(re.sub(r' style="[^"]*"', "", themed), baked, icon)

    def test_every_painted_element_has_a_plain_color(self):
        s = self.doc("gem-tone", Style(box="circle", padding=2, depth=0.3), themed=True)
        root = ET.fromstring(s)
        for el in root.iter():
            if el.tag.split("}")[-1] in ("rect", "path"):
                self.assertTrue(el.get("fill") is not None, ET.tostring(el, encoding="unicode"))

    def test_current_color_option_changes_only_the_main_fallback(self):
        s = self.doc("shield-tone", Style(), themed=True, current_color=True)
        self.assertIn("var(--icon-main,currentColor)", s)
        self.assertIn(f"var(--icon-shade,{DARK.shade})", s)
        self.assertIn(f"var(--icon-light,{DARK.light})", s)

    def test_explicit_roles_map_to_theme_roles_and_off_role_colors_survive(self):
        s = self.doc("gem-tone", Style(), themed=False)
        self.assertIn(f'fill="{DARK.shade}"', s)
        self.assertIn(f'fill="{DARK.light}"', s)
        off = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" '
               'fill="#c0392b" stroke="none"/></svg>')
        self.assertIn('fill="#c0392b"', svg_document(off, Style(), DARK, False))

    def test_depth_adds_offset_ghost_groups_behind_plain_icons(self):
        root = ET.fromstring(self.doc("shield", Style(depth=DEFAULT_DEPTH), themed=False))
        groups = root.findall(SVG_NS + "g")
        self.assertEqual([g.get("transform") for g in groups], ["translate(0.3 0.3)", "translate(-0.3 -0.3)"])
        self.assertEqual(groups[0][0].get("stroke"), DARK.shade)
        self.assertEqual(groups[1][0].get("stroke"), DARK.light)
        self.assertEqual(root[-1].get("stroke"), DARK.main)                    # the real icon is drawn last, on top

    def test_depth_skipped_for_flagged_and_hand_toned_icons(self):
        flat = self.doc("shield", Style(depth=0.3), themed=False, allow_depth=False)
        self.assertEqual(flat, self.doc("shield", Style(), themed=False))
        tone = self.doc("shield-tone", Style(depth=0.3), themed=False)
        self.assertEqual(tone, self.doc("shield-tone", Style(), themed=False))

    def test_stroke_override(self):
        s = self.doc("plus", Style(stroke=3.5), themed=False)
        self.assertEqual(set(re.findall(r'stroke-width="([^"]+)"', s)), {"3.5"})

    def test_every_dummy_icon_exports_in_every_mode_as_valid_xml(self):
        for themed in (True, False):
            for i in self.lib.ids():
                ET.fromstring(self.doc(i, Style(box="rounded", padding=3, depth=0.3, stroke=2), themed))


class Packages(Base):
    def test_default_export_layout_and_manifest(self):
        res = self.run_export()
        names = set(res.files)
        self.assertTrue({"svg/plus.svg", "icons-sprite.svg", "icons-theme.css", "README.txt", "manifest.json"} <= names)
        self.assertEqual(len([n for n in names if n.startswith("svg/")]), 13)
        self.assertFalse(any(n.startswith("png/") for n in names))
        m = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual((m["tool"], m["mode"], len(m["icons"])), ("Icon Library", "themed", 13))
        self.assertEqual(sorted(m["files"]), sorted(names))

    def test_sprite_has_one_symbol_per_icon_and_valid_ids(self):
        self.run_export(ids=["plus", "star"])
        root = ET.parse(self.out / "icons-sprite.svg").getroot()
        syms = root.findall(SVG_NS + "symbol")
        self.assertEqual([s.get("id") for s in syms], ["icon-plus", "icon-star"])
        self.assertTrue(all(s.get("viewBox") and not s.get("width") for s in syms))

    def test_theme_css_has_a_block_per_theme_and_root_default(self):
        self.run_export(themes=[OCEAN, LIGHT, DARK])
        css = (self.out / "icons-theme.css").read_text()
        self.assertIn(':root,\n[data-theme="ocean"] {', css)
        self.assertIn('[data-theme="dave-light"] {', css)
        self.assertIn(f"--icon-main: {LIGHT.main};", css)
        # themed files don't multiply by theme; the first theme is the baked fallback
        self.assertIn(f"var(--icon-main,{OCEAN.main})", (self.out / "svg" / "plus.svg").read_text())
        self.assertFalse((self.out / "svg" / "ocean").exists())

    def test_baked_with_several_themes_gets_a_folder_each(self):
        res = self.run_export(ids=["plus"], themes=[DARK, OCEAN], mode="baked", sprite=True)
        self.assertIn("svg/dave-dark/plus.svg", res.files)
        self.assertIn("svg/ocean/plus.svg", res.files)
        self.assertIn("icons-sprite-ocean.svg", res.files)
        self.assertNotIn("icons-theme.css", res.files)
        self.assertIn(OCEAN.main, (self.out / "svg/ocean/plus.svg").read_text())

    def test_png_matches_the_previews_pixels(self):
        style = Style(box="rounded", padding=3, depth=0.3)
        self.run_export(ids=["shield"], style=style, themes=[OCEAN], svg=False, sprite=False, png=True,
                        png_sizes=(32, 64))
        with Image.open(self.out / "png/32px/shield.png") as im:
            img = im.convert("RGBA")
        want = compose(load(self.root / "icons/shield.svg"), 32, style, OCEAN)
        self.assertEqual(img.tobytes(), want.tobytes())
        with Image.open(self.out / "png/64px/shield.png") as im64:
            self.assertEqual(im64.size, (64, 64))
        self.assertEqual(img.getpixel((0, 0))[3], 0)                           # transparent corner (rounded box)

    def test_png_with_several_themes_uses_theme_folders(self):
        res = self.run_export(ids=["plus"], themes=[DARK, LIGHT], svg=False, sprite=False, png=True, png_sizes=(16,))
        self.assertIn("png/dave-light/16px/plus.png", res.files)

    def test_depth_report_lists_icons_that_stay_flat(self):
        res = self.run_export(style=Style(depth=0.3))
        self.assertEqual(res.flat, ["gem-tone", "rune-dense", "shield-tone"])
        self.assertEqual(self.run_export(style=Style()).flat, [])

    def test_renamed_icons_export_under_the_new_name_once(self):
        self.lib.rename("home", "house")
        res = self.run_export(ids=["home", "house", "plus"])
        self.assertEqual(res.icons, ["house", "plus"])


class Safety(Base):
    def test_export_never_changes_the_master_library(self):
        before = tree_hash(self.root)
        self.run_export(style=Style(box="circle", padding=3, depth=0.3), themes=[DARK, OCEAN], png=True)
        self.run_export(mode="baked", themes=[DARK, OCEAN])
        self.assertEqual(tree_hash(self.root), before)

    def test_refuses_to_write_inside_or_over_the_library(self):
        for bad in (self.root, self.root / "icons", self.root / "newfolder", self.base):
            before = tree_hash(self.root)
            with self.assertRaises(ExportError, msg=str(bad)):
                export(self.lib, ["plus"], Style(), [DARK], ExportOptions(), bad)
            self.assertEqual(tree_hash(self.root), before)

    def test_refuses_a_foreign_non_empty_folder(self):
        self.out.mkdir()
        (self.out / "important.txt").write_text("keep me")
        with self.assertRaises(ExportError):
            self.run_export()
        self.assertEqual((self.out / "important.txt").read_text(), "keep me")

    def test_re_export_replaces_its_own_files_only(self):
        self.run_export(png=True)
        (self.out / "my-notes.txt").write_text("mine")
        res = self.run_export(ids=["plus", "star"], png=False)                 # smaller export, fewer formats
        files = {str(p.relative_to(self.out)) for p in self.out.rglob("*") if p.is_file()}
        self.assertEqual(files, {*res.files, "my-notes.txt"})
        self.assertFalse((self.out / "png").exists())                          # emptied folders are tidied
        self.assertFalse((self.out / "svg" / "shield.svg").exists())

    def test_bad_options_are_rejected_before_anything_is_written(self):
        for kw in ({"svg": False, "sprite": False}, {"svg_size": 2}, {"png": True, "png_sizes": ()},
                   {"png": True, "png_sizes": (4,)}, {"mode": "fancy"}):
            with self.assertRaises(ExportError, msg=str(kw)):
                self.run_export(**kw)
        with self.assertRaises(ExportError):
            export(self.lib, [], Style(), [DARK], ExportOptions(), self.out)
        with self.assertRaises(ExportError):
            export(self.lib, ["plus"], Style(), [], ExportOptions(), self.out)
        self.assertFalse(self.out.exists())

    def test_one_broken_icon_is_skipped_and_reported_not_fatal(self):
        (self.root / "icons" / "plus.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>x</text></svg>')
        res = self.run_export(ids=["plus", "star"])
        self.assertEqual(res.icons, ["star"])
        self.assertTrue(res.skipped and res.skipped[0].startswith("plus:"))
        self.assertNotIn("svg/plus.svg", res.files)

    def test_unknown_icon_raises_a_library_error(self):
        from iconlib.library import LibraryError
        with self.assertRaises(LibraryError):
            self.run_export(ids=["nope"])


@unittest.skipUnless(shutil.which("inkscape"), "Inkscape is not installed")
class RealViewer(Base):
    """A viewer that does not understand CSS variables must still show the icon (Inkscape is one)."""

    def render(self, svg_path, out_png):
        subprocess.run(["inkscape", str(svg_path), "--export-type=png", "--export-width=64", "--export-height=64",
                        "-o", str(out_png)], capture_output=True, timeout=90, check=True)
        with Image.open(out_png) as im:
            return im.convert("RGBA")

    def test_themed_export_is_visible_and_matches_the_baked_one_in_inkscape(self):
        style = Style(box="rounded", padding=3, radius=0.25, stroke=2)
        export(self.lib, ["star", "shield"], style, [OCEAN], ExportOptions(mode="themed", sprite=False), self.base / "t")
        export(self.lib, ["star", "shield"], style, [OCEAN], ExportOptions(mode="baked", sprite=False), self.base / "b")
        for icon in ("star", "shield"):
            themed = self.render(self.base / "t" / "svg" / f"{icon}.svg", self.base / f"t-{icon}.png")
            baked = self.render(self.base / "b" / "svg" / f"{icon}.svg", self.base / f"b-{icon}.png")
            colors = {themed.getpixel((x, y))[:3] for x in range(0, 64, 2) for y in range(0, 64, 2)
                      if themed.getpixel((x, y))[3] > 200}
            self.assertIn(tuple(int(OCEAN.main[i:i + 2], 16) for i in (1, 3, 5)), {c for c in colors},
                          f"{icon}: the lines are missing in a viewer without CSS variables")
            self.assertNotIn((0, 0, 0), colors, f"{icon}: black = a color the viewer threw away")
            diff = sum(abs(a - b) for a, b in zip(themed.tobytes(), baked.tobytes()))
            self.assertLess(diff / (64 * 64 * 4), 1.0)


if __name__ == "__main__":
    unittest.main()
