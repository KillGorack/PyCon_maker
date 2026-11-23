"""Dev tool: launch the app against a THROWAWAY copy of the library, optionally select an icon,
grab the window to a PNG and exit.   python tools/snapshot.py OUT.png [dark|light] [icon-id] [guides]
Settings are redirected to a temp folder, so nothing in your real settings or library changes."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp())
os.environ["XDG_DATA_HOME"] = str(tmp / "data")
if (ROOT / "library" / "icons").is_dir():
    shutil.copytree(ROOT / "library", tmp / "library")           # a COPY of your library; nothing is changed
else:                                                              # fresh clone: use the dummy data
    import make_dummy_icons
    make_dummy_icons.LIB = tmp / "library"
    make_dummy_icons.main(force=True)

import app as appmod  # noqa: E402
import dave_theme as ui  # noqa: E402
from PIL import ImageGrab  # noqa: E402

out = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "dark"
pick = sys.argv[3] if len(sys.argv) > 3 else None
guides = "guides" in sys.argv[4:]
ui.setup(mode)
appmod.DEFAULT_LIBRARY = tmp / "library"
a = appmod.App()
a.geometry("1100x700+60+60")


def shoot():
    if pick:
        a.gallery.select(pick)
    if guides:
        a.toggle_guides()
    a.after(900, grab)


def grab():
    a.update()
    x, y, w, h = a.winfo_rootx(), a.winfo_rooty(), a.winfo_width(), a.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
    a.destroy()


a.after(1200, shoot)
a.mainloop()
shutil.rmtree(tmp, ignore_errors=True)
print("saved", out)
