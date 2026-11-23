"""Step 3: import cleaner + library (index, add/replace/remove/rename, tags, search)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from iconlib.clean import CleanError, clean_svg
from iconlib.library import Library, LibraryError
from iconlib.svgrender import load, parse_svg

from tests.fixtures import library_dir

DUMMY = library_dir()
INKSCAPE = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
 xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" width="24mm" height="24mm"
 viewBox="0 0 24 24" inkscape:version="1.3">
 <sodipodi:namedview id="nv" inkscape:zoom="4"/><metadata><rdf/></metadata><defs id="d"/>
 <g inkscape:label="Layer 1" inkscape:groupmode="layer" style="stroke:#000000;stroke-width:2.0000;fill:none">
  <path id="p1" d="M 4,12 H 20" style="stroke-linecap:round"/>
  <circle id="c1" cx="12" cy="12" r="5.00" style="stroke:#FF0000"/></g></svg>'''
SIMPLE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000000" '
          'stroke-width="2"><path d="M4 12h16"/></svg>')


class Clean(unittest.TestCase):
    def test_inkscape_file_is_flattened_and_cleaned(self):
        res = clean_svg(INKSCAPE)
        self.assertEqual((res.errors, res.warnings), ([], []))
        for junk in ("inkscape", "sodipodi", "metadata", "defs", "<g", "id=", "style="):
            self.assertNotIn(junk, res.svg)
        icon = parse_svg(res.svg)
        self.assertEqual([(s.stroke, s.stroke_width, s.fill) for s in icon.shapes],
                         [("#000000", 2.0, None), ("#ff0000", 2.0, None)])

    def test_non_role_color_and_wrong_canvas_warn(self):
        res = clean_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
                        '<path d="M0 0L5 5" stroke="#abc" fill="none"/></svg>')
        self.assertEqual(res.errors, [])
        self.assertTrue(any("#aabbcc" in w for w in res.warnings))
        self.assertTrue(any("32x32" in w for w in res.warnings))

    def test_unsupported_elements_and_garbage(self):
        self.assertTrue(clean_svg('<svg xmlns="http://www.w3.org/2000/svg"><text>x</text></svg>').errors)
        self.assertTrue(clean_svg("not xml").errors)
        self.assertTrue(clean_svg('<svg xmlns="http://www.w3.org/2000/svg"/>').errors)

    def test_cleaning_is_idempotent(self):
        once = clean_svg(INKSCAPE).svg
        self.assertEqual(clean_svg(once).svg, once)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "lib"
        shutil.copytree(DUMMY, self.root)
        self.lib = Library(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # --- loading
    def test_loads_dummy_library(self):
        self.assertEqual(len(self.lib.ids()), 13)
        self.assertFalse(self.lib.index_was_rebuilt)
        self.assertEqual(self.lib.get("rune-dense").depth, "off")

    def test_missing_index_is_rebuilt_from_files(self):
        (self.root / "index.json").unlink()
        lib = Library(self.root)
        self.assertTrue(lib.index_was_rebuilt)
        self.assertEqual(len(lib.ids()), 13)
        self.assertTrue((self.root / "index.json").exists())

    def test_corrupt_index_is_kept_as_bad_and_rebuilt(self):
        (self.root / "index.json").write_text("{ nope")
        lib = Library(self.root)
        self.assertTrue((self.root / "index.json.bad").exists())
        self.assertEqual(len(lib.ids()), 13)

    def test_new_file_on_disk_gets_default_record_and_orphans_are_reported(self):
        shutil.copy(self.root / "icons" / "plus.svg", self.root / "icons" / "plus-two.svg")
        (self.root / "icons" / "star.svg").unlink()
        lib = Library(self.root)
        self.assertIn("plus-two", lib.ids())
        self.assertNotIn("star", lib.ids())
        self.assertEqual(lib.orphans(), ["star"])
        self.assertEqual(lib.prune(), ["star"])
        self.assertEqual(lib.orphans(), [])

    def test_loading_does_not_modify_svg_files(self):
        before = {p.name: p.read_bytes() for p in (self.root / "icons").glob("*.svg")}
        Library(self.root)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / "icons").glob("*.svg")})

    # --- add
    def test_add_cleans_and_records(self):
        warnings = self.lib.add("line-wave", INKSCAPE, tags=["Lines", "test thing"], notes="n")
        self.assertEqual(warnings, [])
        self.assertIn("line-wave", self.lib.ids())
        self.assertNotIn("inkscape", self.lib.read_svg("line-wave"))
        self.assertEqual(self.lib.get("line-wave").tags, ["lines", "test-thing"])
        self.assertEqual(Library(self.root).get("line-wave").notes, "n")     # persisted

    def test_add_rejects_bad_ids_duplicates_and_bad_svg(self):
        for bad in ("Bad Name", "under_score", "-x", "x-", "x--y", ""):
            with self.assertRaises(LibraryError, msg=bad):
                self.lib.add(bad, SIMPLE)
        with self.assertRaises(LibraryError):
            self.lib.add("plus", SIMPLE)
        with self.assertRaises(CleanError):
            self.lib.add("fresh", "<svg")
        self.assertNotIn("fresh", self.lib.ids())
        self.assertFalse((self.root / "icons" / "fresh.svg").exists())

    def test_no_temp_files_left_behind(self):
        self.lib.add("fresh", SIMPLE)
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    # --- replace
    def test_replace_keeps_metadata_and_backs_up_old_file(self):
        self.lib.set_tags("plus", ["action", "keep"])
        old = self.lib.read_svg("plus")
        self.lib.replace("plus", SIMPLE)
        self.assertNotEqual(self.lib.read_svg("plus"), old)
        self.assertEqual(self.lib.get("plus").tags, ["action", "keep"])
        backups = list((self.root / ".trash").glob("plus.*.svg"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), old)

    def test_failed_replace_changes_nothing(self):
        old = self.lib.read_svg("plus")
        with self.assertRaises(CleanError):
            self.lib.replace("plus", "<svg><text/></svg>")
        self.assertEqual(self.lib.read_svg("plus"), old)
        self.assertFalse((self.root / ".trash").exists())

    # --- remove
    def test_remove_moves_to_trash(self):
        trashed = self.lib.remove("star")
        self.assertTrue(trashed.exists())
        self.assertNotIn("star", self.lib.ids())
        self.assertNotIn("star", Library(self.root).records)

    def test_unknown_icon_raises(self):
        with self.assertRaises(LibraryError):
            self.lib.remove("nope")

    # --- rename
    def test_rename_keeps_old_name_as_alias(self):
        self.lib.set_tags("home", ["building"])
        self.lib.rename("home", "house")
        self.assertNotIn("home", self.lib.ids())
        self.assertEqual(self.lib.resolve("home"), "house")
        self.assertEqual(self.lib.get("house").aliases, ["home"])
        self.assertEqual(self.lib.get("house").tags, ["building"])
        self.assertEqual(Library(self.root).resolve("home"), "house")

    def test_rename_collisions_and_rename_back(self):
        with self.assertRaises(LibraryError):
            self.lib.rename("home", "star")
        self.lib.rename("home", "house")
        with self.assertRaises(LibraryError):
            self.lib.add("home", SIMPLE)               # old name is reserved as an alias
        self.lib.rename("house", "home")                # back again is fine
        self.assertEqual(self.lib.get("home").aliases, ["house"])

    def test_collections_found_by_alias_after_rename(self):
        self.assertEqual(self.lib.collections_using("home"), ["UI basics"])
        self.lib.rename("home", "house")
        self.assertEqual(self.lib.collections_using("house"), ["UI basics"])
        self.assertEqual(self.lib.collections_using("star"), [])

    # --- tags / search
    def test_tags_notes_depth(self):
        self.lib.set_tags("star", ["Rating Stars", "shape"])
        self.assertEqual(self.lib.get("star").tags, ["rating-stars", "shape"])
        self.lib.set_depth("star", "off")
        self.assertEqual(Library(self.root).get("star").depth, "off")
        with self.assertRaises(LibraryError):
            self.lib.set_depth("star", "maybe")

    def test_search_and_tag_filter(self):
        self.assertEqual(self.lib.search("arrow"), ["arrow-left", "arrow-right"])
        self.assertEqual(self.lib.search("left arrow"), ["arrow-left"])
        self.assertIn("sword", self.lib.search(tags=["weapon"]))
        self.assertEqual(self.lib.search("", tags=["combat", "tone"]), ["shield-tone"])
        self.assertEqual(len(self.lib.search()), 13)
        self.assertEqual(self.lib.search("zzz"), [])

    def test_search_finds_alias(self):
        self.lib.rename("home", "house")
        self.assertIn("house", self.lib.search("home"))

    def test_all_tags_counts(self):
        tags = self.lib.all_tags()
        self.assertEqual(tags["arrow"], 2)
        self.assertEqual(list(tags), sorted(tags))

    def test_every_library_icon_renders_after_cleaning(self):
        for i in self.lib.ids():
            self.assertEqual(clean_svg(self.lib.read_svg(i)).errors, [], i)
            load(self.lib.path(i))


if __name__ == "__main__":
    unittest.main()
