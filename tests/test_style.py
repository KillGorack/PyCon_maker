"""Step 5: Style, Theme, compose() and theme storage."""
import json
import tempfile
import unittest
from pathlib import Path

from iconlib.style import BUILTIN_THEMES, DEFAULT_DEPTH, Style, Theme, compose
from iconlib.svgrender import load
from iconlib.themes import ThemeError, ThemeStore

from tests.fixtures import library_dir

LIB = library_dir() / "icons"
T = Theme("test", main="#00ff00", shade="#101010", light="#f0f0f0", box="#0000aa", bg="#202020")


def alpha(img, xy):
    return img.getpixel(xy)[3]


class StyleModel(unittest.TestCase):
    def test_geometry(self):
        g = Style(box="rounded", padding=3, radius=0.25).geometry()
        self.assertEqual((g.pad, g.side, g.corner, g.boxed), (3, 30, 7.5, True))
        self.assertEqual(Style(box="circle", padding=3).geometry().corner, 15)
        self.assertEqual(Style(box="square", padding=3).geometry().corner, 0)

    def test_padding_ignored_without_a_box(self):
        g = Style(box="none", padding=6).geometry()
        self.assertEqual((g.pad, g.side, g.boxed), (0, 24, False))

    def test_validation_and_tolerant_load(self):
        for bad in ({"box": "hexagon"}, {"padding": -1}, {"radius": 0.9}, {"depth": 5}, {"stroke": 0.01}):
            with self.assertRaises(ValueError):
                Style(**bad)
        self.assertEqual(Style.from_json({"box": "hexagon"}), Style())          # bad value -> default
        self.assertEqual(Style.from_json({"box": "circle", "junk": 1}).box, "circle")
        s = Style(box="rounded", padding=2, depth=0.4, stroke=1.5)
        self.assertEqual(Style.from_json(json.loads(json.dumps(s.to_json()))), s)

    def test_theme_validation(self):
        with self.assertRaises(ValueError):
            Theme("x", "red", "#000000", "#ffffff", "#123456").validate()
        with self.assertRaises(ValueError):
            Theme(" ", "#000000", "#000000", "#ffffff", "#123456").validate()
        Theme.derived("ok", "#808080", "#123456").validate()


class Compose(unittest.TestCase):
    def setUp(self):
        self.icon = load(LIB / "plus.svg")

    def test_no_box_is_transparent_everywhere_but_the_icon(self):
        img = compose(self.icon, 96, Style(), T)
        self.assertEqual(alpha(img, (2, 2)), 0)
        self.assertEqual(img.getpixel((48, 48))[:3], (0, 255, 0))

    def test_box_shapes_at_the_corner(self):
        self.assertEqual(alpha(compose(self.icon, 96, Style(box="square", padding=3), T), (1, 1)), 255)
        self.assertEqual(alpha(compose(self.icon, 96, Style(box="rounded", padding=3, radius=0.3), T), (1, 1)), 0)
        self.assertEqual(alpha(compose(self.icon, 96, Style(box="circle", padding=3), T), (1, 1)), 0)
        self.assertEqual(alpha(compose(self.icon, 96, Style(box="circle", padding=3), T), (48, 3)), 255)

    def test_box_uses_theme_box_color_and_icon_stays_on_top(self):
        img = compose(self.icon, 96, Style(box="square", padding=4), T)
        self.assertEqual(img.getpixel((2, 2))[:3], (0, 0, 0xaa))
        self.assertEqual(img.getpixel((48, 48))[:3], (0, 255, 0))

    def test_padding_shrinks_the_icon_inside_the_box(self):
        def arm(img):                                   # horizontal arm of the plus, in pixels
            row = [img.getpixel((x, 48))[:3] == (0, 255, 0) for x in range(96)]
            return sum(row)
        tight = compose(self.icon, 96, Style(box="square", padding=0), T)
        roomy = compose(self.icon, 96, Style(box="square", padding=6), T)
        self.assertLess(arm(roomy), arm(tight) * 0.7)

    def test_backdrop_and_guides_are_preview_only_layers(self):
        plain = compose(self.icon, 96, Style(), T)
        back = compose(self.icon, 96, Style(), T, backdrop=True)
        self.assertEqual(alpha(plain, (30, 30)), 0)
        self.assertEqual(back.getpixel((30, 30))[:3], (0x20, 0x20, 0x20))
        self.assertNotEqual(compose(self.icon, 96, Style(), T, guide_color="#ff0000").tobytes(), plain.tobytes())

    def test_backdrop_is_not_drawn_around_a_box(self):
        """Regression: a circle box showed the theme's page color in the four corners (two colors)."""
        for box in ("circle", "rounded"):
            img = compose(self.icon, 96, Style(box=box, padding=0, radius=0.5), T, backdrop=True)
            self.assertEqual(alpha(img, (0, 0)), 0, box)
            self.assertEqual(alpha(img, (95, 95)), 0, box)
        sq = compose(self.icon, 96, Style(box="square"), T, backdrop=True)
        self.assertEqual(sq.getpixel((0, 0))[:3], (0, 0, 0xaa))              # the box color, not the page color
        flat = compose(self.icon, 96, Style(), T, backdrop=True)
        self.assertEqual(flat.getpixel((30, 30))[:3], (0x20, 0x20, 0x20))    # un-boxed icons still get the page behind

    def test_depth_respects_the_icon_flag_and_explicit_roles(self):
        deep = Style(depth=DEFAULT_DEPTH)
        shield = load(LIB / "shield.svg")
        flat = compose(shield, 64, Style(), T).tobytes()
        self.assertNotEqual(compose(shield, 64, deep, T).tobytes(), flat)
        self.assertEqual(compose(shield, 64, deep, T, allow_depth=False).tobytes(), flat)   # flagged off
        tone = load(LIB / "shield-tone.svg")
        self.assertEqual(compose(tone, 64, deep, T).tobytes(), compose(tone, 64, Style(), T).tobytes())

    def test_stroke_override_thickens(self):
        thin = compose(self.icon, 96, Style(stroke=1), T).getchannel("A").getbbox()
        thick_px = sum(1 for a in compose(self.icon, 96, Style(stroke=4), T).getchannel("A").tobytes() if a)
        thin_px = sum(1 for a in compose(self.icon, 96, Style(stroke=1), T).getchannel("A").tobytes() if a)
        self.assertGreater(thick_px, thin_px * 2)
        self.assertIsNotNone(thin)

    def test_compose_never_changes_the_icon(self):
        icon = load(LIB / "star.svg")
        n = len(icon.shapes[0].subpaths[0])
        compose(icon, 64, Style(box="circle", padding=3, depth=0.4, stroke=2), T)
        self.assertEqual(len(icon.shapes[0].subpaths[0]), n)

    def test_every_builtin_theme_composes_every_icon(self):
        for theme in BUILTIN_THEMES:
            theme.validate()
            for p in LIB.glob("*.svg"):
                img = compose(load(p), 32, Style(box="rounded", padding=3, depth=0.3), theme, backdrop=True)
                self.assertEqual(img.size, (32, 32))


class Themes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "themes.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_and_builtins(self):
        store = ThemeStore(self.path)
        self.assertEqual(store.names()[:4], [t.name for t in BUILTIN_THEMES])
        store.save_theme(Theme.derived("Mine", "#ff8800", "#220a00"))
        again = ThemeStore(self.path)
        self.assertEqual(again.get("Mine").main, "#ff8800")
        self.assertIn("Mine", again.names())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_builtins_are_protected(self):
        store = ThemeStore(self.path)
        with self.assertRaises(ThemeError):
            store.save_theme(Theme.derived("Ocean", "#ffffff", "#000000"))
        with self.assertRaises(ThemeError):
            store.delete("Ocean")

    def test_delete_and_unknown_name_falls_back(self):
        store = ThemeStore(self.path)
        store.save_theme(Theme.derived("Mine", "#ff8800", "#220a00"))
        store.delete("Mine")
        self.assertNotIn("Mine", ThemeStore(self.path).names())
        self.assertEqual(store.get("nope").name, BUILTIN_THEMES[0].name)

    def test_damaged_file_and_damaged_entry_are_survivable(self):
        self.path.write_text("{ nope")
        self.assertEqual(ThemeStore(self.path).user, {})
        self.path.write_text(json.dumps({"themes": {"Good": {"main": "#111111", "shade": "#000000", "light": "#ffffff",
                                                             "box": "#222222"}, "Bad": {"main": "blue"}}}))
        self.assertEqual(list(ThemeStore(self.path).user), ["Good"])


if __name__ == "__main__":
    unittest.main()
