"""Step 1: the dummy library is internally consistent."""
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.fixtures import library_dir

LIB = library_dir()
ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ALLOWED = {"svg", "path", "line", "polyline", "polygon", "circle", "ellipse", "rect"}
ROLE_COLORS = {"#000000", "#ff0000", "#0000ff", "none", "currentcolor"}


class DummyLibrary(unittest.TestCase):
    def setUp(self):
        self.index = json.loads((LIB / "index.json").read_text())["icons"]
        self.files = {p.stem: p for p in (LIB / "icons").glob("*.svg")}

    def test_index_matches_files(self):
        self.assertEqual(set(self.index), set(self.files))

    def test_ids_are_kebab_case(self):
        for name in self.files:
            self.assertRegex(name, ID)

    def test_svgs_use_allowed_subset_and_role_colors(self):
        for name, path in self.files.items():
            root = ET.parse(path).getroot()
            self.assertEqual(root.get("viewBox"), "0 0 24 24", name)
            for el in root.iter():
                self.assertIn(el.tag.split("}")[-1], ALLOWED, name)
                for attr in ("stroke", "fill"):
                    v = el.get(attr)
                    if v:
                        self.assertIn(v.lower(), ROLE_COLORS, f"{name}: {attr}={v}")

    def test_collections_reference_existing_icons(self):
        for c in (LIB / "collections").glob("*.json"):
            for icon in json.loads(c.read_text())["icons"]:
                self.assertIn(icon, self.files, f"{c.name}: {icon}")


if __name__ == "__main__":
    unittest.main()
