"""Packaging + command line: no display needed."""
import io
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app as appmod  # noqa: E402  (importing the module does not open a window)


class Packaging(unittest.TestCase):
    def setUp(self):
        self.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    def test_every_top_level_module_the_app_needs_is_packaged(self):
        listed = set(self.pyproject["tool"]["setuptools"]["py-modules"])
        on_disk = {p.stem for p in ROOT.glob("*.py") if p.stem not in {"setup", "conftest"}}
        self.assertEqual(listed, on_disk, "py-modules in pyproject.toml must match the .py files next to app.py")

    def test_packages_and_entry_point(self):
        t = self.pyproject["tool"]["setuptools"]
        self.assertEqual(set(t["packages"]), {"iconlib", "icons"})
        for pkg in t["packages"]:
            self.assertTrue((ROOT / pkg).is_dir())
        self.assertEqual(self.pyproject["project"]["scripts"]["icon-library"], "app:main")
        self.assertTrue(callable(appmod.main))

    def test_version_comes_from_version_py(self):
        import version
        self.assertRegex(version.VERSION, r"^\d+\.\d+\.\d+$")
        self.assertIn("version", self.pyproject["project"]["dynamic"])

    def test_window_icon_ships_with_the_icons(self):
        self.assertTrue((ROOT / "icons" / "icon.png").exists())
        self.assertIn("*.png", self.pyproject["tool"]["setuptools"]["package-data"]["icons"])

    def test_gitignore_keeps_personal_data_and_build_output_out(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        for must in ("library/", "build/", "dist/", "__pycache__/", "*.egg-info/"):
            self.assertIn(must, lines)


class CommandLine(unittest.TestCase):
    def test_default_library_prefers_a_checkout_library_else_the_data_folder(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(base / "data")}):
                self.assertEqual(appmod.default_library(base), base / "data" / "IconLibrary" / "library")
                (base / "library" / "icons").mkdir(parents=True)
                self.assertEqual(appmod.default_library(base), base / "library")

    def test_version_flag(self):
        r = subprocess.run([sys.executable, str(ROOT / "app.py"), "--version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Icon Library", r.stdout)

    def test_selftest_passes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = appmod.selftest()
        self.assertEqual(code, 0, buf.getvalue())
        self.assertIn("selftest: OK", buf.getvalue())

    def test_menu_entry_can_be_installed_and_removed(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Linux only")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(appmod.install_menu(), 0)
            desktop = Path(d) / "applications" / "icon-library.desktop"
            text = desktop.read_text()
            self.assertRegex(text, r"(?m)^Exec=.+")
            icon = Path(re.search(r"(?m)^Icon=(.+)$", text).group(1))
            self.assertTrue(icon.exists())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(appmod.remove_menu(), 0)
            self.assertFalse(desktop.exists() or icon.exists())


if __name__ == "__main__":
    unittest.main()
