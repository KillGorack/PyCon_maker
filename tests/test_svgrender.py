"""Step 2: the SVG-subset renderer."""
import unittest
from pathlib import Path

from iconlib.svgrender import load, parse_path, parse_svg, render

from tests.fixtures import library_dir

LIB = library_dir() / "icons"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2">{}</svg>'


def bounds(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def opaque(img):
    return sum(1 for a in img.getchannel("A").tobytes() if a > 128)


class PathParsing(unittest.TestCase):
    def test_arc_circle_bounds(self):
        subs, closed = parse_path("M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z")
        x0, y0, x1, y1 = bounds(subs[0])
        for got, want in zip((x0, y0, x1, y1), (3, 3, 21, 21)):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertEqual(closed, [True])

    def test_compressed_arc_flags_and_implicit_lineto(self):
        subs, _ = parse_path("M0 0a1 1 0 0110 0")               # flags run into the next number
        self.assertAlmostEqual(subs[0][-1][0], 10, places=5)
        subs, _ = parse_path("m1 1 2 0 0 2")                     # relative moveto then implicit lineto
        self.assertEqual([tuple(p) for p in subs[0]], [(1, 1), (3, 1), (3, 3)])

    def test_cubic_smooth_and_quadratic(self):
        subs, _ = parse_path("M0 0C0 4 4 4 4 0S8-4 8 0Q10 4 12 0T16 0")
        self.assertAlmostEqual(subs[0][-1][0], 16, places=5)

    def test_multiple_subpaths(self):
        subs, closed = parse_path("M1 1h2v2zM10 10h2v2")
        self.assertEqual(len(subs), 2)
        self.assertEqual(closed, [True, False])

    def test_bad_command_raises(self):
        with self.assertRaises(ValueError):
            parse_path("M0 0 X 1 1")


class Parsing(unittest.TestCase):
    def test_roles(self):
        icon = parse_svg(SVG.format('<path d="M1 1L5 5" stroke="#FF0000"/><circle cx="5" cy="5" r="2" stroke="#0000ff"/>'
                                    '<line x1="0" y1="0" x2="3" y2="3"/>'))
        self.assertEqual(icon.roles_used, {"main", "shade", "light"})
        self.assertTrue(icon.has_explicit_tones)

    def test_plain_icon_has_no_explicit_tones(self):
        self.assertFalse(parse_svg(SVG.format('<path d="M2 2L20 20"/>')).has_explicit_tones)

    def test_style_attribute_overrides_and_inkscape_style(self):
        icon = parse_svg(SVG.format('<path d="M2 2L20 20" style="fill:none;stroke:#ff0000;stroke-width:3"/>'))
        sh = icon.shapes[0]
        self.assertEqual((sh.stroke, sh.stroke_width), ("#ff0000", 3.0))

    def test_unsupported_features_warn(self):
        icon = parse_svg(SVG.format('<g><path d="M2 2L9 9" transform="scale(2)"/></g>'))
        self.assertTrue(any("transform" in w for w in icon.warnings))
        self.assertTrue(any("<g>" in w for w in icon.warnings))

    def test_all_dummy_icons_parse_without_warnings(self):
        for p in LIB.glob("*.svg"):
            self.assertEqual(load(p).warnings, [], p.name)


class Rendering(unittest.TestCase):
    def test_transparent_corners_and_size(self):
        img = render(load(LIB / "home.svg"), 48)
        self.assertEqual(img.size, (48, 48))
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.getpixel((0, 0))[3], 0)

    def test_every_dummy_icon_draws_something(self):
        for p in LIB.glob("*.svg"):
            self.assertGreater(opaque(render(load(p), 32)), 20, p.name)

    def test_palette_recolors_main_and_leaves_other_colors(self):
        img = render(load(LIB / "plus.svg"), 32, {"main": "#00ff00"})
        r, g, b, a = img.getpixel((16, 16))
        self.assertEqual((r, g, b), (0, 255, 0))
        # an off-role color is kept even with a palette
        icon = parse_svg(SVG.format('<rect x="4" y="4" width="16" height="16" fill="#123456" stroke="none"/>'))
        self.assertEqual(render(icon, 24, {"main": "#00ff00"}).getpixel((12, 12))[:3], (0x12, 0x34, 0x56))

    def test_filled_shape_and_even_odd_hole(self):
        icon = parse_svg(SVG.format('<path d="M2 2h20v20H2zM8 8h8v8H8z" fill="#000000" stroke="none"/>'))
        img = render(icon, 48)
        self.assertGreater(img.getpixel((6, 6))[3], 250)
        self.assertEqual(img.getpixel((24, 24))[3], 0)          # hole

    def test_thick_gently_curving_stroke_has_no_streaks_on_its_outer_edge(self):
        """Regression: segments turning ~1.5 degrees (typical of flattened cubics) once left
        wedge-shaped gaps on the outer edge of thick strokes."""
        import math
        from PIL import Image, ImageDraw
        from iconlib.svgrender import _stroke_polyline
        mask = Image.new("L", (400, 400), 0)
        pts = [(200 + 100 * math.cos(math.radians(a / 2)), 200 + 100 * math.sin(math.radians(a / 2)))
               for a in range(0, 541, 3)]                                   # 1.5 degree steps, 270 degrees
        _stroke_polyline(ImageDraw.Draw(mask), pts, 40)                     # half-width 40: very thick
        for deg in range(2, 268, 2):
            x = 200 + 137 * math.cos(math.radians(deg))                     # 3px inside the outer edge (140); the last pixel is rasterization noise
            y = 200 + 137 * math.sin(math.radians(deg))
            self.assertEqual(mask.getpixel((round(x), round(y))), 255, f"hole at {deg} degrees")

    def test_stroke_width_override(self):
        icon = load(LIB / "plus.svg")
        self.assertGreater(opaque(render(icon, 48, stroke_width=4)), opaque(render(icon, 48, stroke_width=1)))

    def test_auto_depth_adds_tones_for_plain_icons(self):
        icon = load(LIB / "shield.svg")
        pal = {"main": "#808080", "shade": "#101010", "light": "#f0f0f0"}
        flat, deep = render(icon, 64, pal), render(icon, 64, pal, depth=0.6)
        self.assertGreater(opaque(deep), opaque(flat))
        data = deep.tobytes()
        colors = {tuple(data[i:i + 3]) for i in range(0, len(data), 4) if data[i + 3] == 255}
        self.assertTrue({(0x10,) * 3, (0xf0,) * 3, (0x80,) * 3} <= colors)

    def test_auto_depth_skipped_for_explicit_roles(self):
        icon = load(LIB / "shield-tone.svg")
        self.assertEqual(render(icon, 48, depth=0.6).tobytes(), render(icon, 48).tobytes())

    def test_render_does_not_change_the_icon_or_file(self):
        p = LIB / "star.svg"
        before = p.read_bytes()
        icon = load(p)
        n = len(icon.shapes[0].subpaths[0])
        render(icon, 48, {"main": "#fff"}, depth=0.5)
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(len(icon.shapes[0].subpaths[0]), n)


if __name__ == "__main__":
    unittest.main()
