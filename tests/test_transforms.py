"""Import cleaner: transforms are baked into the shapes; pages that aren't 24x24 are placed on the canvas."""
import math
import unittest

from iconlib.clean import clean_svg
from iconlib.pathdata import mul, parse_segments, parse_transform, scale_factor, transform_segments
from iconlib.svgrender import parse_svg

NS = 'xmlns="http://www.w3.org/2000/svg"'


def svg(body, viewbox="0 0 24 24"):
    return f'<svg {NS} viewBox="{viewbox}">{body}</svg>'


def bbox(svg_text):
    icon = parse_svg(svg_text)
    pts = [p for s in icon.shapes for sub in s.subpaths for p in sub]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def assert_box(case, got, want, tol=0.02):
    for g, w, name in zip(got, want, ("left", "top", "right", "bottom")):
        case.assertAlmostEqual(g, w, delta=tol, msg=f"{name}: {got} != {want}")


class Matrices(unittest.TestCase):
    def apply(self, m, x, y):
        return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])

    def test_order_is_left_to_right_like_svg(self):
        m = parse_transform("translate(10 0) scale(2)")          # scale first, then translate
        self.assertEqual(self.apply(m, 1, 1), (12, 2))

    def test_rotate_skew_and_matrix(self):
        x, y = self.apply(parse_transform("rotate(90)"), 1, 0)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, 1)
        x, y = self.apply(parse_transform("rotate(180 5 5)"), 4, 5)
        self.assertAlmostEqual(x, 6)
        self.assertAlmostEqual(y, 5)
        self.assertAlmostEqual(self.apply(parse_transform("skewX(45)"), 0, 1)[0], 1)
        self.assertEqual(self.apply(parse_transform("matrix(1 0 0 1 3 4)"), 0, 0), (3, 4))
        self.assertEqual(parse_transform(""), (1, 0, 0, 1, 0, 0))

    def test_bad_transforms_raise(self):
        for bad in ("scale(", "wobble(1)", "translate(1 2 3)", "matrix(1 2 3)"):
            with self.assertRaises(ValueError, msg=bad):
                parse_transform(bad)

    def test_scale_factor(self):
        self.assertAlmostEqual(scale_factor(parse_transform("scale(2)")), 2)
        self.assertAlmostEqual(scale_factor(mul(parse_transform("rotate(33)"), parse_transform("scale(3 3)"))), 3)

    def test_every_path_command_survives_a_shift_exactly(self):
        d = "m 2,2 h 4 v 4 c 1,0 2,1 2,2 s 2,2 3,0 q 1,-2 2,0 t 2,0 a 3 2 30 0 1 2,2 l 1 1 1 -2 z"
        moved = transform_segments(parse_segments(d), (1, 0, 0, 1, 3, 2))
        a = bbox(svg(f'<path d="{d}" stroke="#000" fill="none"/>'))
        from iconlib.pathdata import to_d
        b = bbox(svg(f'<path d="{to_d(moved)}" stroke="#000" fill="none"/>'))
        assert_box(self, b, (a[0] + 3, a[1] + 2, a[2] + 3, a[3] + 2), 0.05)


class CleanerTransforms(unittest.TestCase):
    def test_inkscape_layer_plus_object_transform_and_small_page(self):
        """The real-world shape: a layer translate, an object matrix, relative path data, a page that is
        not 24x24. Corner (0,0) -> object matrix -> (5,5) -> layer -> (3,2) -> centered page -> (5,4)."""
        src = svg('<g inkscape:label="Layer 1" transform="translate(-2,-3)" '
                  'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
                  '<path d="m 0,0 h 10 v 10 h -10 z" style="fill:none;stroke:#000000;stroke-width:1" '
                  'transform="matrix(1.5,0,0,1.5,5,5)"/></g>', viewbox="0 0 20 20")
        res = clean_svg(src)
        self.assertEqual(res.errors, [])
        self.assertNotIn("transform", res.svg)
        self.assertNotIn("<g", res.svg)
        self.assertIn('viewBox="0 0 24 24"', res.svg)
        assert_box(self, bbox(res.svg), (5, 4, 20, 19))
        self.assertTrue(any("20x20" in w and "centered" in w for w in res.warnings))

    def test_rotation(self):
        res = clean_svg(svg('<rect x="4" y="4" width="8" height="4" transform="rotate(90 12 12)" '
                            'fill="#000000" stroke="none"/>'))
        self.assertEqual(res.errors, [])
        assert_box(self, bbox(res.svg), (16, 4, 20, 12))

    def test_a_rotated_circle_stays_round_so_the_arcs_were_converted_accurately(self):
        d = "M 4 12 a 8 8 0 1 0 16 0 a 8 8 0 1 0 -16 0 z"
        res = clean_svg(svg(f'<path d="{d}" transform="rotate(30 12 12)" fill="none" stroke="#000000"/>'))
        assert_box(self, bbox(res.svg), (4, 4, 20, 20), 0.03)
        icon = parse_svg(res.svg)
        radii = [math.hypot(x - 12, y - 12) for sub in icon.shapes[0].subpaths for x, y in sub]
        self.assertLess(max(radii) - min(radii), 0.03)

    def test_every_shape_kind_can_carry_a_transform(self):
        """A shape under translate(6 3) must equal the same shape without it, shifted by (6, 3)."""
        for body in ('<circle cx="6" cy="6" r="3"/>', '<ellipse cx="6" cy="6" rx="3" ry="1"/>',
                     '<line x1="0" y1="0" x2="4" y2="2"/>', '<polyline points="0,0 4,0 4,4"/>',
                     '<polygon points="0,0 4,0 4,4"/>', '<rect x="0" y="0" width="4" height="4" rx="1"/>'):
            plain = bbox(svg(f'<g fill="none" stroke="#000000">{body}</g>'))
            res = clean_svg(svg(f'<g transform="translate(6 3)" fill="none" stroke="#000000">{body}</g>'))
            self.assertEqual(res.errors, [], body)
            self.assertNotIn("transform", res.svg, body)
            assert_box(self, bbox(res.svg), (plain[0] + 6, plain[1] + 3, plain[2] + 6, plain[3] + 3), 0.03)

    def test_uneven_scaling_warns_and_changes_the_shape(self):
        res = clean_svg(svg('<circle cx="12" cy="12" r="4" transform="translate(-12 0) scale(2 1)" '
                            'fill="none" stroke="#000000"/>'))
        assert_box(self, bbox(res.svg), (4, 8, 20, 16), 0.03)                       # an ellipse 16 wide, 8 tall
        self.assertTrue(any("unevenly" in w for w in res.warnings))

    def test_stroke_width_follows_the_scale(self):
        res = clean_svg(svg('<g transform="scale(0.5)"><path d="M 2 2 L 20 20" stroke="#000000" '
                            'stroke-width="2" transform="scale(4)"/></g>'))
        self.assertEqual(parse_svg(res.svg).shapes[0].stroke_width, 4.0)            # 2 x 0.5 x 4

    def test_a_transformed_fill_only_shape_gets_no_stroke(self):
        res = clean_svg(svg('<path d="M 0 0 H 4 V 4 z" transform="translate(2 2)" fill="#000000"/>'))
        shape = parse_svg(res.svg).shapes[0]
        self.assertEqual((shape.fill, shape.stroke), ("#000000", None))

    def test_opacity_only_warns_when_it_is_actually_see_through(self):
        opaque = clean_svg(svg('<path d="M0 0L5 5" style="stroke:#000000;stroke-opacity:1;fill-opacity:1;opacity:1"/>'))
        self.assertEqual(opaque.warnings, [])                                     # what Inkscape writes on everything
        faded = clean_svg(svg('<path d="M0 0L5 5" style="stroke:#000000;stroke-opacity:0.5"/>'))
        self.assertTrue(any("stroke-opacity" in w for w in faded.warnings))

    def test_unreadable_transform_is_reported_as_an_error(self):
        res = clean_svg(svg('<path d="M0 0L5 5" stroke="#000" transform="wobble(3)"/>'))
        self.assertTrue(any("wobble" in e for e in res.errors))


class CleanerPages(unittest.TestCase):
    def test_a_bigger_page_is_scaled_down_to_fit(self):
        res = clean_svg(svg('<path d="M 0 0 L 48 48" stroke="#000000" stroke-width="4"/>', viewbox="0 0 48 48"))
        assert_box(self, bbox(res.svg), (0, 0, 24, 24))
        self.assertEqual(parse_svg(res.svg).shapes[0].stroke_width, 2.0)
        self.assertTrue(any("48x48" in w and "scaled by 0.5" in w for w in res.warnings))

    def test_a_non_square_small_page_is_centered_both_ways(self):
        res = clean_svg(svg('<path d="M 0 0 L 20 10" stroke="#000000"/>', viewbox="0 0 20 10"))
        assert_box(self, bbox(res.svg), (2, 7, 22, 17))

    def test_a_page_with_an_offset_origin(self):
        res = clean_svg(svg('<path d="M 10 10 L 34 34" stroke="#000000"/>', viewbox="10 10 24 24"))
        assert_box(self, bbox(res.svg), (0, 0, 24, 24))

    def test_an_exact_24_page_is_left_completely_alone(self):
        d = "M 4,12 H 20 m 0,4 h -16"
        res = clean_svg(svg(f'<path d="{d}" stroke="#000000" fill="none"/>'))
        self.assertIn(f'd="{d}"', res.svg)                                         # not rewritten
        self.assertEqual(res.warnings, [])

    def test_cleaning_twice_changes_nothing(self):
        once = clean_svg(svg('<g transform="translate(1 1)"><path d="m 0,0 h 5 a 2 2 0 0 1 2,2 z" '
                             'stroke="#000000" transform="scale(1.3)"/></g>', viewbox="0 0 20 18")).svg
        self.assertEqual(clean_svg(once).svg, once)


if __name__ == "__main__":
    unittest.main()
