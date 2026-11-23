"""A pristine dummy library for tests, generated into a temp folder (never the user's live library)."""
import atexit
import contextlib
import io
import importlib.util
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_dir: Path | None = None


def make_library(dest: Path) -> Path:
    spec = importlib.util.spec_from_file_location("make_dummy_icons", ROOT / "tools" / "make_dummy_icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LIB = Path(dest)
    with contextlib.redirect_stdout(io.StringIO()):
        mod.main(force=True)
    return Path(dest)


def library_dir() -> Path:
    """One shared read-only copy per test run. Tests that modify things copy it first."""
    global _dir
    if _dir is None:
        _dir = Path(tempfile.mkdtemp(prefix="iconlib-fixture-"))
        make_library(_dir)
        atexit.register(shutil.rmtree, _dir, True)
    return _dir
