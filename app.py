"""
Icon Library: a master library of SVG icons, with per-project subset export.
Browse, tag, import, replace and remove icons; preview them in a chosen style and theme;
save subsets as collections; export to SVG / sprite / PNG with theme CSS.

Run:  python3 app.py [--library DIR] [--theme dark|light]      (installed: icon-library)
"""
import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import dave_theme as ui
from dave_theme import C, GUTTER
from dialogs import prompt
from exportdialog import ExportDialog
from gallery import Detail, Gallery, ImportDialog, Thumbs
from iconlib.clean import clean_svg
from iconlib.collections import Collection, CollectionError, CollectionStore
from iconlib.library import Library, LibraryError
from iconlib.style import Style, Theme
from iconlib.themes import ThemeStore
from sidebar import Sidebar
from stylepanel import APP_THEME, StylePanel, ThemeEditor, with_thickness

from version import APP_NAME as APP_TITLE, VERSION

APP_NAME = "IconLibrary"          # settings folder name; must be unique per app
COMMAND = "icon-library"


def default_library(base: Path | None = None) -> Path:
    """A source checkout that has a library/ folder next to this file uses it (development).
    An installed copy (pipx) keeps the library in the user's data folder."""
    local = (base or Path(__file__).resolve().parent) / "library"
    return local if (local / "icons").is_dir() else ui.app_dir(APP_NAME) / "library"


DEFAULT_LIBRARY = default_library()


class App(ctk.CTk):
    def __init__(self, library: Path | None = None):
        super().__init__()
        self.settings = ui.Settings(APP_NAME)
        # precedence: --library, then the saved setting, then the default location
        self.library = Path(library) if library else Path(self.settings.get("library", str(DEFAULT_LIBRARY)))
        self.title(APP_TITLE)
        self.geometry(self.settings.get("geometry", "1250x720"))
        self.minsize(900, 520)
        self.configure(fg_color=C["window"])
        try:
            self._icon = tk.PhotoImage(file=ui.ICON_DIR / "icon.png")
            self.iconphoto(True, self._icon)
        except Exception:
            pass

        self.lib = Library(self.library)
        self.collections = CollectionStore(self.lib)
        self.themes = ThemeStore(self.library / "themes.json")
        self.thumbs = Thumbs(self.lib, self.themes)
        self.current: Collection | None = None
        self.guides = bool(self.settings.get("guides", False))

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self, self.collections, self.open_collection, self.delete_collection,
                               self.rename_collection, lambda c: self.delete_collection(c, confirm=True))
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(GUTTER, 0), pady=(GUTTER, 0))
        self.gallery = Gallery(self, self.thumbs, self.on_select, self.icon_menu)
        self.gallery.grid(row=0, column=1, sticky="nsew", padx=GUTTER, pady=(GUTTER, 0))
        self.detail = Detail(self, self.thumbs, {
            "tags": self.save_tags,
            "replace": self.replace_icon, "remove": self.remove_icon, "rename": self.rename_icon,
            "collections_for": self.collections_for, "membership": self.set_membership,
            "tab": lambda t: self.settings.__setitem__("tab", t)},
            self.make_style_panel)
        self.detail.grid(row=0, column=2, sticky="ns", padx=(0, GUTTER), pady=(GUTTER, 0))

        bar = self.bar = ui.Toolbar(self)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=GUTTER, pady=GUTTER)
        bar.add(ui.icon_button(bar, "panel-left", self.toggle_sidebar,
                               lambda: "Show collections (Ctrl+B)" if not self.sidebar.winfo_ismapped()
                               else "Hide collections (Ctrl+B)"))
        bar.add(ui.icon_button(bar, "square-pen", self.new_collection, "New collection (Ctrl+N)"))
        bar.divider()
        bar.add(ui.icon_button(bar, "plus", self.import_icon, "Import SVG (Ctrl+O)"))
        self.guides_btn = ui.icon_button(bar, "grid", self.toggle_guides,
                                         lambda: "Hide safe-area guides (Ctrl+G)" if self.guides
                                         else "Show safe-area guides (Ctrl+G)")
        bar.add(self.guides_btn)
        bar.stretch()
        bar.add(ui.icon_button(bar, "export", self.export_icons, "Export… (Ctrl+E)"))
        bar.divider()
        self.theme_btn = ui.icon_button(bar, self.theme_icon(), self.toggle_theme,
                                        lambda: "Light theme" if self.is_dark() else "Dark theme")
        bar.add(self.theme_btn, last=True)

        self.bind("<Control-o>", lambda _e: self.import_icon())
        self.bind("<Control-n>", lambda _e: self.new_collection())
        self.bind("<Control-b>", lambda _e: self.toggle_sidebar())
        self.bind("<Control-f>", lambda _e: self.gallery.focus_search())
        self.bind("<Control-g>", lambda _e: self.toggle_guides())
        self.bind("<Control-e>", lambda _e: self.export_icons())
        self.bind("<Control-a>", self._select_all)
        self.protocol("WM_DELETE_WINDOW", self.close)
        if self.settings.get("sidebar_hidden"):
            self.sidebar.grid_remove()

        # restore: tab, guides, selection. Always start on "All icons" so nothing looks missing.
        self.current = None
        self._load_style_for(None)
        self.detail.set_tab(self.settings.get("tab", "Icon"))
        self.gallery.guides = self.guides
        self.reload()
        self._style_guides_btn()
        last = self.settings.get("selected")
        if last in self.gallery.tiles:
            self.gallery.select(last)
        if self.lib.index_was_rebuilt:
            self.bar.note("Index was missing or damaged and has been rebuilt", tone="error", ms=6000)

    # ------------------------------------------------------------------ data
    def reload(self):
        self.gallery.set_library(self.lib)
        self.apply_scope()
        self.sidebar.refresh(total=len(self.lib.ids()), selected=self.current)
        self.detail.show(self.gallery.selected, self.lib, self.guides)

    def on_select(self, icon_id):
        self.detail.show(icon_id, self.lib, self.guides)
        if icon_id:
            self.settings["selected"] = icon_id
        n = len(self.gallery.selection)
        if n > 1:
            self.bar.note(f"{n} icons selected  (right-click to add them to a collection)")

    def fail(self, e: Exception):
        self.bar.note(str(e), tone="error", ms=6000)

    def _select_all(self, _e):
        if self.focus_get().winfo_class() not in ("Entry", "Text"):      # leave text editing alone
            self.gallery.select_all()

    # ----------------------------------------------------------- collections
    def apply_scope(self):
        """Filter the grid to the open collection and report members that no longer exist."""
        c = self.current
        if c is None:
            self.gallery.set_scope(None)
            self.gallery.set_view("All icons", len(self.lib.ids()))
            return
        present, missing = self.collections.members(c)
        self.gallery.set_view(c.name, len(present), back=self.sidebar.open_all)
        banner = link = ""
        if missing:
            shown = ", ".join(missing[:3]) + ("…" if len(missing) > 3 else "")
            banner = f"{len(missing)} listed icon{'s' if len(missing) > 1 else ''} no longer in the library: {shown}"
            link = "Remove from collection"
        self.gallery.set_scope(set(present), banner, link, self.drop_missing)

    def open_collection(self, c):
        self.current = c
        self._load_style_for(c)
        self.apply_scope()
        self._restyled()
        self.detail.refresh_collections()

    def _load_style_for(self, c):
        """A collection with a saved style brings it back; otherwise the app-level style is used."""
        src_style, src_theme = (c.style, c.theme) if c and c.style is not None else (
            self.settings.get("style", {}), self.settings.get("style_theme", APP_THEME))
        self.thumbs.style = with_thickness(Style.from_json(src_style))
        self.thumbs.theme_name = src_theme if src_theme == APP_THEME or src_theme in self.themes.names() else APP_THEME
        self.style_panel.load(self.thumbs.style, self.thumbs.theme_name)
        self.style_panel.set_where(c.name if c else None)

    def new_collection(self, ids=()):
        made = []

        def ok(text):
            try:
                made.append(self.collections.create(text, ids))
            except (CollectionError, LibraryError) as e:
                return str(e)

        if prompt(self, "New collection", "Name it for a project or purpose (for example “Pirate game UI”).",
                  ok="Create", on_ok=ok):
            self.sidebar.refresh(selected=made[0])
            self.open_collection(made[0])
            self.bar.note(f"Created {made[0].name}" + (f" with {len(ids)} icons" if ids else ""))

    def rename_collection(self, c):
        def ok(text):
            try:
                self.collections.rename(c.name, text)
            except CollectionError as e:
                return str(e)

        if prompt(self, "Rename collection", "New name:", c.name, ok="Rename", on_ok=ok):
            self.sidebar.refresh()
            if c is self.current:
                self.style_panel.set_where(c.name)
                self.apply_scope()

    def delete_collection(self, c, confirm=False):
        if confirm and not ui.ask(self, "Delete collection",
                                  f"Delete “{c.name}”? The icons stay in the library.", "Delete", danger=True):
            return
        self.collections.delete(c.name)
        was_open = c is self.current
        self.sidebar.refresh(selected=None if was_open else self.current)
        if was_open:
            self.open_collection(None)
        self.detail.refresh_collections()
        self.bar.note(f"Deleted {c.name} (kept in .trash)")

    def drop_missing(self):
        if self.current:
            gone = self.collections.drop_missing(self.current.name)
            self.apply_scope()
            self.sidebar.refresh()
            self.bar.note(f"Removed {len(gone)} missing entr{'ies' if len(gone) != 1 else 'y'} from {self.current.name}")

    def collections_for(self, icon_id):
        return self.collections.names(), set(self.collections.containing(icon_id))

    def set_membership(self, icon_id, name, checked):
        try:
            (self.collections.add if checked else self.collections.remove)(name, [icon_id])
        except (CollectionError, LibraryError) as e:
            return self.fail(e)
        self._collections_changed(name)
        self.bar.note(f"{'Added to' if checked else 'Removed from'} {name}")

    def _collections_changed(self, name=None):
        self.sidebar.refresh()
        if self.current and (name is None or name == self.current.name):
            self.apply_scope()

    def icon_menu(self, event, ids):
        """Right-click on a tile: add the selection to a collection, or take it out of the open one."""
        m = ui.themed_menu(self)
        label = ids[0] if len(ids) == 1 else f"{len(ids)} icons"
        sub = ui.themed_menu(m)
        for name in self.collections.names():
            sub.add_command(label=name, command=lambda name=name: self.add_to_collection(name, ids))
        if self.collections.names():
            sub.add_separator()
        sub.add_command(label="New collection…", command=lambda: self.new_collection(ids))
        m.add_cascade(label=f"Add {label} to", menu=sub)
        if self.current:
            m.add_command(label=f"Remove from “{self.current.name}”", command=lambda: self.remove_from_current(ids))
        ui.popup(m, event)

    def add_to_collection(self, name, ids):
        try:
            n = self.collections.add(name, ids)
        except (CollectionError, LibraryError) as e:
            return self.fail(e)
        self._collections_changed(name)
        self.detail.refresh_collections()
        self.bar.note(f"Added {n} to {name}" if n else f"Already in {name}")

    def remove_from_current(self, ids):
        n = self.collections.remove(self.current.name, ids)
        self._collections_changed(self.current.name)
        self.gallery.selection = [i for i in self.gallery.selection if i not in ids]
        self.detail.refresh_collections()
        self.bar.note(f"Removed {n} from {self.current.name}")

    # --------------------------------------------------------------- editing
    def save_tags(self, icon_id, tags):
        try:
            before = self.lib.get(icon_id).tags
            self.lib.set_tags(icon_id, tags)
            if self.lib.get(icon_id).tags != before:
                self.bar.note("Tags saved")
                self.detail.tags.delete(0, "end")
                self.detail.tags.insert(0, " ".join(self.lib.get(icon_id).tags))
        except LibraryError as e:
            self.fail(e)

    def set_depth(self, icon_id, mode):
        self.lib.set_depth(icon_id, mode)
        self.gallery.refresh_icon(icon_id)                  # the flag changes how this icon renders
        self.detail.refresh_previews()
        self.bar.note("Automatic depth " + ("allowed" if mode == "auto" else "off for this icon"))

    def rename_icon(self, icon_id):
        def ok(text):
            try:
                self.lib.rename(icon_id, text)
            except LibraryError as e:
                return str(e)

        new = prompt(self, f"Rename {icon_id}", "Lowercase words joined by hyphens, general to specific "
                     "(arrow-left). The old name keeps working in collections.", icon_id, ok="Rename", on_ok=ok)
        if new and new != icon_id:
            self.thumbs.forget(icon_id)
            self.gallery.selected = None
            self.gallery.selection = []
            self.reload()
            self.gallery.select(new)
            self.bar.note(f"Renamed {icon_id} to {new}")

    # --------------------------------------------------- import / replace / remove
    def _pick_svg(self, title):
        path = filedialog.askopenfilename(parent=self, title=title, initialdir=self.settings.get("import_dir"),
                                          filetypes=[("SVG files", "*.svg"), ("All files", "*")])
        if not path:
            return None
        self.settings["import_dir"] = str(Path(path).parent)
        try:
            return Path(path), Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            self.fail(e)
            return None

    def import_icon(self):
        picked = self._pick_svg("Import SVG")
        if not picked:
            return
        path, text = picked

        def confirm(icon_id, tags):
            self.lib.add(icon_id, text, tags=tags)
            joined = ""
            if self.current:                                # importing while a collection is open adds it there
                self.collections.add(self.current.name, [icon_id])
                joined = f" to {self.current.name}"
            self.thumbs.forget(icon_id)
            self.reload()
            self.gallery.select(icon_id)
            self.bar.note(f"Added {icon_id}{joined}")

        ImportDialog(self, self.thumbs, clean_svg(text), "add", path.name, confirm)

    def replace_icon(self, icon_id):
        picked = self._pick_svg(f"New artwork for {icon_id}")
        if not picked:
            return
        path, text = picked

        def confirm(_id, _tags):
            self.lib.replace(icon_id, text)
            self.gallery.refresh_icon(icon_id)
            self.detail.show(icon_id, self.lib, self.guides)
            self.bar.note(f"Replaced {icon_id} (old file kept in .trash)")

        ImportDialog(self, self.thumbs, clean_svg(text), "replace", path.name, confirm, target=icon_id)

    def remove_icon(self, icon_id):
        try:
            self.lib.remove(icon_id)
        except LibraryError as e:
            return self.fail(e)
        self.thumbs.forget(icon_id)
        self.gallery.selected = None
        self.gallery.selection = [i for i in self.gallery.selection if i != icon_id]
        self.reload()
        self.bar.note(f"Removed {icon_id} (kept in .trash)")

    # ----------------------------------------------------------------- style
    def make_style_panel(self, parent):
        self.style_panel = StylePanel(parent, self.themes, self.set_style, self.set_theme, self.edit_theme,
                                      lambda allowed: self.detail.icon_id and self.set_depth(
                                          self.detail.icon_id, "auto" if allowed else "off"))
        return self.style_panel

    def _restyled(self):
        self.gallery.restyle()
        self.detail.refresh_previews()

    def _remember_style(self):
        """Style edits belong to the open collection, or to the app when none is open."""
        if self.current:
            self.collections.set_style(self.current.name, self.thumbs.style, self.thumbs.theme_name)
        else:
            self.settings["style"] = self.thumbs.style.to_json()
            self.settings["style_theme"] = self.thumbs.theme_name

    def set_style(self, style: Style):
        self.thumbs.style = style
        self._remember_style()
        self._restyled()

    def set_theme(self, name: str):
        self.thumbs.theme_name = name
        self._remember_style()
        self._restyled()

    def edit_theme(self, name):
        """Open the theme editor on a theme (None = a new one based on the current theme)."""
        if name in (None, APP_THEME):
            cur = self.thumbs.theme(self.is_dark())
            base = Theme(name="My theme", main=cur.main, shade=cur.shade, light=cur.light, box=cur.box, bg=cur.bg)
            is_new = True
        else:
            base, is_new = self.themes.get(name), False

        def saved(new_name):
            self.thumbs.forget()
            self.style_panel.refresh_themes(new_name)
            self.set_theme(new_name)
            self.bar.note(f"Theme {new_name} saved")

        def deleted():
            self.thumbs.forget()
            self.style_panel.refresh_themes(APP_THEME)
            self.set_theme(APP_THEME)

        ThemeEditor(self, self.themes, base, is_new, saved, deleted)

    # ---------------------------------------------------------------- export
    def export_icons(self):
        """Open the export dialog for the open collection, the selection, or everything."""
        sources = []
        if self.current:
            present, _missing = self.collections.members(self.current)
            if present:
                sources.append((f"Collection: {self.current.name} ({len(present)})", present))
        if len(self.gallery.selection) > 1:
            sources.append((f"Selected icons ({len(self.gallery.selection)})", list(self.gallery.selection)))
        if self.lib.ids():
            sources.append((f"All icons ({len(self.lib.ids())})", self.lib.ids()))
        if not sources:
            return self.bar.note("There are no icons to export yet", tone="error")
        ui.toggle_window(self, "export", lambda: ExportDialog(
            self, self.lib, self.themes, self.thumbs.style, self.thumbs.theme_name, sources,
            self.settings.get("export", {}), lambda opts: self.settings.__setitem__("export", opts)))

    # ---------------------------------------------------------------- guides
    def toggle_guides(self):
        self.guides = not self.guides
        self.settings["guides"] = self.guides
        self.gallery.set_guides(self.guides)
        self.detail.guides = self.guides
        self.detail.refresh_previews()
        self._style_guides_btn()

    def _style_guides_btn(self):
        self.guides_btn.configure(fg_color=C["hover"] if self.guides else "transparent")

    # ------------------------------------------------------------ sidebar/theme
    def toggle_sidebar(self):
        if self.sidebar.winfo_ismapped():
            self.sidebar.grid_remove()
        else:
            self.sidebar.grid()
        self.settings["sidebar_hidden"] = not self.sidebar.winfo_ismapped()

    def is_dark(self):
        return ctk.get_appearance_mode() == "Dark"

    def theme_icon(self):
        return "sun" if self.is_dark() else "moon"

    def toggle_theme(self):
        mode = "light" if self.is_dark() else "dark"
        ui.set_mode(mode)
        self.settings["theme"] = mode
        self.configure(fg_color=C["window"])
        ui.set_icon(self.theme_btn, self.theme_icon())

    def close(self):
        self.settings["geometry"] = self.geometry()
        self.destroy()


# ---------------------------------------------------------------- command line
def _menu_paths(size: int) -> tuple[Path, Path]:
    import os
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (data / "applications" / f"{COMMAND}.desktop",
            data / "icons" / "hicolor" / f"{size}x{size}" / "apps" / f"{COMMAND}.png")


def _app_icon() -> Path:
    return ui.ICON_DIR / "icon.png"


def install_menu() -> int:
    """Add (or refresh) the applications-menu entry for a pip/pipx install. Linux only, per user."""
    import shutil
    import subprocess

    from PIL import Image
    if not sys.platform.startswith("linux"):
        print("Menu entries are for Linux.")
        return 1
    exe = shutil.which(COMMAND) or str(Path(sys.argv[0]).resolve())
    with Image.open(_app_icon()) as im:
        size = im.width
    desktop, icon = _menu_paths(size)
    icon.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_app_icon(), icon)
    desktop.write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name={APP_TITLE}\nComment=A master library of SVG icons with themed exports\n"
        f"Exec={exe}\nIcon={icon}\nTerminal=false\nCategories=Graphics;\n")
    desktop.chmod(0o755)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop.parent)], capture_output=True)
    print(f"Menu entry added: {desktop}\nLaunches: {exe}")
    return 0


def remove_menu() -> int:
    from PIL import Image
    with Image.open(_app_icon()) as im:
        size = im.width
    removed = False
    for p in _menu_paths(size):
        if p.exists():
            p.unlink()
            removed = True
    print("Menu entry removed." if removed else "No menu entry was installed.")
    return 0


def selftest() -> int:
    """Check that this install is complete: icons, rendering, library, export. No display needed."""
    import tempfile

    from iconlib.export import ExportOptions, export
    from iconlib.style import BUILTIN_THEMES, Style
    problems = []
    for name in ("panel-left", "square-pen", "plus", "grid", "export", "info", "sun", "moon", "trash-2", "icon"):
        if not (ui.ICON_DIR / f"{name}.png").exists():
            problems.append(f"missing icon: {name}")
    try:
        from PIL import ImageTk  # noqa: F401
    except ImportError:
        problems.append("Pillow ImageTk missing")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 12h16" stroke="#000000" '
           'stroke-width="2" fill="none"/></svg>')
    folder = Path(tempfile.mkdtemp())
    try:
        lib = Library(folder / "lib")
        lib.add("selftest-line", svg, tags=["test"])
        res = export(lib, lib.ids(), Style(box="rounded", padding=3, stroke=2), [BUILTIN_THEMES[0]],
                     ExportOptions(png=True), folder / "out")
        needed = {"svg/selftest-line.svg", "icons-sprite.svg", "icons-theme.css", "png/32px/selftest-line.png"}
        if not needed <= set(res.files):
            problems.append("export is missing files: " + ", ".join(sorted(needed - set(res.files))))
    except Exception as e:                                   # a selftest reports, it doesn't crash
        problems.append(f"library/export round trip failed: {e}")
    print(f"{APP_TITLE} {VERSION} selftest: " + ("OK" if not problems else "FAILED"))
    for line in problems:
        print("  -", line)
    return 1 if problems else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{APP_TITLE} {VERSION}")
    ap.add_argument("--version", action="version", version=f"{APP_TITLE} {VERSION}")
    ap.add_argument("--library", metavar="DIR", help="icon library folder for this run "
                                                     f"(default: {DEFAULT_LIBRARY})")
    ap.add_argument("--theme", choices=("dark", "light"), help="app theme (remembered)")
    ap.add_argument("--selftest", action="store_true", help="check this install is complete, then exit")
    ap.add_argument("--install-menu", action="store_true", help="add an applications-menu entry (Linux, per user)")
    ap.add_argument("--remove-menu", action="store_true", help="remove that applications-menu entry")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.install_menu:
        sys.exit(install_menu())
    if a.remove_menu:
        sys.exit(remove_menu())
    settings = ui.Settings(APP_NAME)
    if a.theme:
        settings["theme"] = a.theme
    ui.setup(settings.get("theme", "dark"))
    App(Path(a.library).expanduser() if a.library else None).mainloop()


if __name__ == "__main__":
    main()
