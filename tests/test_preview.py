"""Step 4: UI-independent helpers (layout, id suggestion, tones, guides)."""
import unittest

from iconlib.preview import flow_layout, guides, mix, suggest_id, tone_palette



class FlowLayout(unittest.TestCase):
    def test_wraps_when_row_is_full(self):
        pos, h = flow_layout([(40, 20)] * 5, width=100, gap=5)       # 2 per row (40+5+40=85; a third needs 130)
        self.assertEqual(pos, [(0, 0), (45, 0), (0, 25), (45, 25), (0, 50)])
        self.assertEqual(h, 70)

    def test_wide_item_gets_its_own_row_and_empty_is_zero(self):
        pos, h = flow_layout([(10, 10), (500, 30), (10, 10)], width=100, gap=4)
        self.assertEqual(pos, [(0, 0), (0, 14), (0, 48)])
        self.assertEqual(flow_layout([], 100), ([], 0))

    def test_row_height_is_tallest_item(self):
        pos, h = flow_layout([(30, 10), (30, 50), (30, 10)], width=70, gap=0)
        self.assertEqual(pos[2], (0, 50))
        self.assertEqual(h, 60)


class SuggestId(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(suggest_id("Arrow Left (1).SVG"), "arrow-left-1")
        self.assertEqual(suggest_id("sword_crossed.svg"), "sword-crossed")
        self.assertEqual(suggest_id("---.svg"), "")


class Tones(unittest.TestCase):
    def test_mix(self):
        self.assertEqual(mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(mix("#123456", "#ffffff", 0), "#123456")

    def test_tone_palette_orders_dark_to_light(self):
        p = tone_palette("#808080")
        lum = lambda h: sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(lum(p["shade"]), lum(p["main"]))
        self.assertLess(lum(p["main"]), lum(p["light"]))


class Guides(unittest.TestCase):
    def test_overlay_is_transparent_inside_and_draws_the_safe_box(self):
        g = guides(240, "#ff0000")
        self.assertEqual(g.size, (240, 240))
        self.assertEqual(g.getpixel((60, 60))[3], 0)                  # empty interior
        self.assertGreater(g.getpixel((20, 120))[3], 100)             # safe-area edge at 2/24 * 240 = 20

    def test_guides_follow_box_padding(self):
        g = guides(300, "#ff0000", side=30, pad=3)                    # 10px per unit; canvas starts at 30px
        self.assertGreater(g.getpixel((30, 150))[3], 50)              # canvas edge
        self.assertEqual(g.getpixel((10, 150))[3], 0)                 # padding area has no guide
        self.assertGreater(g.getpixel((50, 150))[3], 100)             # safe-area edge, 3 + 2 units in


if __name__ == "__main__":
    unittest.main()
