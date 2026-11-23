"""Step 6: collections store."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from iconlib.collections import CollectionError, CollectionStore, slugify
from iconlib.library import Library
from iconlib.style import Style

from tests.fixtures import library_dir

DUMMY = library_dir()


class Collections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "lib"
        shutil.copytree(DUMMY, self.root)
        self.lib = Library(self.root)
        self.store = CollectionStore(self.lib)

    def tearDown(self):
        self.tmp.cleanup()

    def test_loads_existing_collection(self):
        self.assertEqual(self.store.names(), ["UI basics"])
        ids, missing = self.store.members(self.store.get("ui basics"))       # case-insensitive
        self.assertEqual((ids, missing), (["arrow-left", "arrow-right", "check", "home", "plus"], []))

    def test_create_add_remove_roundtrip(self):
        c = self.store.create("Pirate  Game", ["sword", "shield"])
        self.assertEqual(c.name, "Pirate Game")                              # whitespace collapsed
        self.assertEqual(self.store.add("pirate game", ["sword", "heart", "star"]), 2)   # sword already in
        self.assertEqual(self.store.remove("Pirate Game", ["shield", "nope"]), 1)
        again = CollectionStore(self.lib)
        self.assertEqual(again.members(again.get("Pirate Game"))[0], ["heart", "star", "sword"])
        self.assertTrue((self.root / "collections" / "pirate-game.json").exists())

    def test_names_must_be_valid_and_unique(self):
        for bad in ("", "   ", "x" * 61, "ui BASICS"):
            with self.assertRaises(CollectionError, msg=bad):
                self.store.create(bad)
        with self.assertRaises(CollectionError):
            self.store.get("nope")

    def test_adding_unknown_icon_is_refused(self):
        from iconlib.library import LibraryError
        with self.assertRaises(LibraryError):
            self.store.add("UI basics", ["no-such-icon"])

    def test_slug_collisions_get_a_suffix(self):
        a = self.store.create("A+B")
        b = self.store.create("A B")
        self.assertEqual((a.slug, b.slug), ("a-b", "a-b-2"))
        self.assertEqual(slugify("!!!"), "collection")

    def test_rename_moves_the_file_and_keeps_contents(self):
        self.store.rename("UI basics", "Core UI")
        self.assertFalse((self.root / "collections" / "ui-basics.json").exists())
        again = CollectionStore(self.lib)
        self.assertEqual(again.names(), ["Core UI"])
        self.assertEqual(len(again.members(again.get("Core UI"))[0]), 5)
        with self.assertRaises(CollectionError):
            self.store.create("core ui")

    def test_rename_to_a_different_case_of_itself_is_fine(self):
        self.store.rename("UI basics", "ui BASICS")
        self.assertEqual(self.store.names(), ["ui BASICS"])

    def test_delete_goes_to_trash(self):
        dest = self.store.delete("UI basics")
        self.assertTrue(dest.exists())
        self.assertEqual(CollectionStore(self.lib).names(), [])

    def test_renamed_icon_still_resolves_and_is_found(self):
        self.lib.rename("home", "house")
        ids, missing = self.store.members(self.store.get("UI basics"))
        self.assertIn("house", ids)
        self.assertNotIn("home", ids)
        self.assertEqual(missing, [])
        self.assertEqual(self.store.containing("house"), ["UI basics"])
        self.assertEqual(self.store.remove("UI basics", ["house"]), 1)       # removes by alias entry too
        self.assertEqual(self.store.containing("plus"), ["UI basics"])

    def test_removed_icon_shows_as_missing_and_can_be_dropped(self):
        self.lib.remove("check")
        c = self.store.get("UI basics")
        ids, missing = self.store.members(c)
        self.assertEqual(missing, ["check"])
        self.assertNotIn("check", ids)
        self.assertEqual(self.store.drop_missing("UI basics"), ["check"])
        self.assertEqual(self.store.members(c)[1], [])
        self.assertEqual(self.store.add("UI basics", ["star"]), 1)

    def test_style_is_remembered_with_the_collection(self):
        self.store.set_style("UI basics", Style(box="rounded", padding=3, depth=0.3), "Ocean")
        again = CollectionStore(self.lib)
        c = again.get("UI basics")
        self.assertEqual((Style.from_json(c.style).box, c.theme), ("rounded", "Ocean"))

    def test_damaged_file_is_skipped_and_left_alone(self):
        bad = self.root / "collections" / "broken.json"
        bad.write_text("{ nope")
        self.assertEqual(CollectionStore(self.lib).names(), ["UI basics"])
        self.assertEqual(bad.read_text(), "{ nope")

    def test_collection_files_hold_only_ids_never_artwork(self):
        self.store.create("Tiny", ["star"])
        data = json.loads((self.root / "collections" / "tiny.json").read_text())
        self.assertEqual(data["icons"], ["star"])
        self.assertNotIn("<svg", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
