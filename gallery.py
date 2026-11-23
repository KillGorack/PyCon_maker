"""UI pieces for the icon workflow, built from dave_theme components:
Thumbs (cached theme-aware images), Flow (wrapping layout), Gallery (view header, search, tiles),
Detail (preview, tags, notes, depth flag, replace/remove) and ImportDialog (clean, review, confirm).
"""
from __future__ import annotations

import re
from typing import Callable

import customtkinter as ctk
from PIL import Image

import dave_theme as ui
from dave_theme import C, GUTTER, RADIUS
from iconlib.clean import CleanResult
from iconlib.library import Library, LibraryError
from iconlib.preview import flow_layout, suggest_id
from iconlib.style import Style, Theme, compose
from iconlib.svgrender import load, parse_svg
from iconlib.themes import ThemeStore
from stylepanel import APP_THEME

TILE_ICON = 48
TILE_W, TILE_H = 92, 88


def error_label(master, text: str = "", **kw):
    lbl = ui.label(master, text, **kw)
    lbl.configure(text_color=C["error"])
    return lbl


def _tok(token: str, dark: bool) -> str:
    return C[token][1 if dark else 0]


class Thumbs:
    """Theme-aware CTkImages of icons in the current style, cached per file version and style.
    The "App colors" theme follows the app's light/dark mode (two renders); any other theme is
    the same in both modes (one render)."""

    MAX_CACHE = 3000

    def __init__(self, lib: Library, store: ThemeStore):
        self.lib, self.store = lib, store
        self.style = Style()
        self.theme_name = APP_THEME
        self._cache: dict[tuple, ctk.CTkImage] = {}

    @property
    def dynamic(self) -> bool:
        return self.theme_name == APP_THEME

    def theme(self, dark: bool) -> Theme:
        if self.dynamic:
            return Theme.derived(APP_THEME, _tok("text_strong", dark), _tok("hover", dark), None)
        return self.store.get(self.theme_name)

    def stamp(self) -> tuple:
        """Changes whenever a re-render is needed (style or theme colors)."""
        return (self.style, self.theme_name if self.dynamic else self.theme(False))

    def from_icon(self, icon, size: int, guides: bool = False, allow_depth: bool = True) -> ctk.CTkImage:
        def one(dark):
            return compose(icon, size, self.style, self.theme(dark), allow_depth,
                           _tok("muted", dark) if guides else None, backdrop=True)

        light = one(False)
        dark = one(True) if (self.dynamic or guides) else light
        return ctk.CTkImage(light_image=light, dark_image=dark, size=(size, size))

    def image(self, icon_id: str, size: int, guides: bool = False) -> ctk.CTkImage:
        path = self.lib.path(icon_id)
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        allow = self.lib.records[icon_id].depth == "auto" if icon_id in self.lib.records else True
        key = (icon_id, size, guides, mtime, allow, self.stamp())
        if key not in self._cache:
            if len(self._cache) > self.MAX_CACHE:
                self._cache.clear()
            try:
                icon = load(path)
            except Exception:                       # unreadable file: show an empty tile, keep the app alive
                icon = parse_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>')
            self._cache[key] = self.from_icon(icon, size, guides, allow)
        return self._cache[key]

    def forget(self, icon_id: str | None = None):
        for k in [k for k in self._cache if icon_id is None or k[0] == icon_id]:
            del self._cache[k]


class Flow(ctk.CTkFrame):
    """Children placed left to right, wrapping to the container width (icon tiles)."""

    def __init__(self, master, gap: int = 6):
        super().__init__(master, fg_color="transparent", height=10)
        self.gap, self.items, self._h = gap, [], -1
        self.bind("<Configure>", lambda _e: self.after_idle(self.relayout))

    def set_items(self, items: list):
        for w in self.items:
            if w not in items:
                w.place_forget()
        self.items = list(items)
        self.relayout()

    def relayout(self):
        if not self.winfo_exists() or self.winfo_width() <= 1:
            return
        scale = self._get_widget_scaling()
        sizes = [(w.winfo_reqwidth() / scale, w.winfo_reqheight() / scale) for w in self.items]
        pos, h = flow_layout(sizes, self.winfo_width() / scale, self.gap)
        for w, (x, y) in zip(self.items, pos):
            w.place(x=x, y=y)
        if int(h) != self._h:
            self._h = int(h)
            self.configure(height=max(1, self._h))


class Gallery(ui.Panel):
    def __init__(self, master, thumbs: Thumbs, on_select: Callable[[str | None], None],
                 on_menu: Callable[[object, list[str]], None] | None = None):
        super().__init__(master)
        self.thumbs, self.on_select, self.on_menu = thumbs, on_select, on_menu
        self.lib: Library | None = None
        self.guides = False
        self.selected: str | None = None          # the icon shown in the detail panel
        self.selection: list[str] = []            # every selected icon (Ctrl+click adds)
        self.scope: set[str] | None = None        # None = all icons, else only these (a collection)
        self.tiles: dict[str, ctk.CTkButton] = {}
        self._stamps: dict[str, tuple] = {}
        self._job = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # which view am I in?  "All icons"  or  "<collection>" with a way back
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self.header.grid_remove()                    # only shown inside a collection
        self.title = ui.label(self.header, "All icons", bold=True, size=ui.FONT_SIZE + 3)
        self.title.pack(side="left")
        self.count = ui.label(self.header, "", muted=True)
        self.count.pack(side="left", padx=(8, 0))
        self._back: Callable | None = None
        self.back = ui.link(self.header, "Show all icons", lambda: self._back and self._back(), tone="link")
        self.back.pack(side="right")
        self.back.pack_forget()
        self.search = ui.search_entry(self, "Search icons or tags  (Ctrl+F)")
        self.search.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 6))
        self.search.bind("<KeyRelease>", self._debounce)
        self.search.bind("<Escape>", lambda _e: self.clear_search())
        self.banner = ctk.CTkFrame(self, fg_color="transparent")
        self.banner_text = ui.label(self.banner, "", muted=True, size=ui.FONT_SIZE - 1)
        self.banner_text.pack(side="left")
        self.banner_link = ui.link(self.banner, "", None, tone="link")
        self.banner_link.pack(side="left", padx=(8, 0))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                             scrollbar_button_color=C["scrollbar"],
                                             scrollbar_button_hover_color=C["scrollbar_hover"])
        self.scroll.grid(row=3, column=0, sticky="nsew", padx=(10, 0), pady=(0, 6))   # left edge = the search bar's
        self.scroll.grid_columnconfigure(0, weight=1)
        ui.autohide_scrollbar(self.scroll)
        self.flow = Flow(self.scroll, gap=4)
        self.flow.grid(row=0, column=0, sticky="ew")
        self.empty = ui.label(self.scroll, "", muted=True)

    # ------------------------------------------------------------------ data
    def set_library(self, lib: Library):
        self.lib = lib
        self.flow.set_items([])
        for w in self.tiles.values():
            w.destroy()
        self.tiles, self._stamps = {}, {}
        for i in lib.ids():
            b = ctk.CTkButton(self.flow, text=self._short(i), image=None,
                              compound="top", width=TILE_W, height=TILE_H, corner_radius=RADIUS,
                              fg_color="transparent", hover_color=C["hover"], text_color=C["muted"],
                              font=ui.font(ui.FONT_SIZE - 3), command=lambda i=i: self.select(i))
            ui.Tooltip(b, i)
            b.bind("<Button-3>", lambda e, i=i: self._context(e, i), add="+")
            b.bind("<Control-Button-1>", lambda _e, i=i: self.toggle_select(i), add="+")
            self.tiles[i] = b
        self.selection = [i for i in self.selection if i in self.tiles]
        if self.selected not in self.tiles:
            self.selected = self.selection[-1] if self.selection else None
        self.apply_filter()

    @staticmethod
    def _short(name: str, n: int = 13) -> str:
        return name if len(name) <= n else name[: n - 1] + "…"

    def visible_ids(self) -> list[str]:
        if not self.lib:
            return []
        ids = self.lib.search(self.search.get())
        return ids if self.scope is None else [i for i in ids if i in self.scope]

    def set_scope(self, scope: set[str] | None, banner: str = "", link: str = "", on_link=None):
        """Show only these icons (a collection) or everything (None). The banner is a one-line note
        with an optional action, e.g. about collection members that no longer exist."""
        self.scope = scope
        if banner:
            self.banner_text.configure(text=banner)
            self.banner_link.configure(text=link)
            self.banner_link.unbind("<Button-1>")
            if on_link:
                self.banner_link.bind("<Button-1>", lambda _e: on_link())
            self.banner.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        else:
            self.banner.grid_forget()
        self.apply_filter()

    def apply_filter(self):
        ids = self.visible_ids()
        self._sync_images(ids)
        self.flow.set_items([self.tiles[i] for i in ids])
        if ids:
            self.empty.grid_forget()
        else:
            if not self.tiles:
                msg = "The library is empty.\nImport an SVG with the + button (Ctrl+O)."
            elif self.scope is not None and not self.scope:
                msg = "This collection is empty.\nRight-click icons in All icons to add them,\nor tick the collection in the Icon tab."
            else:
                msg = "No icons match."
            self.empty.configure(text=msg)
            self.empty.grid(row=1, column=0, sticky="w", padx=8, pady=12)
        self._style_tiles()

    def set_view(self, title: str, count: int, back: Callable | None = None):
        """Say which view the grid shows. `back` (a callable) adds a 'Show all icons' link."""
        self._back = back
        if back is None:                             # All icons: no header, the grid speaks for itself
            self.header.grid_remove()
            self.search.grid_configure(pady=(10, 6))
            return
        self.title.configure(text=title)
        self.count.configure(text=f"{count} icon{'s' if count != 1 else ''}")
        self.back.pack(side="right")
        self.header.grid()
        self.search.grid_configure(pady=(8, 6))

    def _debounce(self, _e=None):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(150, self.apply_filter)

    def clear_search(self):
        self.search.delete(0, "end")
        self.apply_filter()

    def focus_search(self):
        self.search.focus_set()
        self.search.select_range(0, "end")

    # ------------------------------------------------------------- selection
    def select(self, icon_id: str | None):
        self.selection = [icon_id] if icon_id else []
        self.selected = icon_id
        self._style_tiles()
        self.on_select(icon_id)

    def toggle_select(self, icon_id: str):
        """Ctrl+click: add or remove one icon from the selection."""
        if icon_id in self.selection:
            self.selection.remove(icon_id)
            self.selected = self.selection[-1] if self.selection else None
        else:
            self.selection.append(icon_id)
            self.selected = icon_id
        self._style_tiles()
        self.on_select(self.selected)

    def select_all(self):
        """Ctrl+A: every icon currently shown."""
        self.selection = self.visible_ids()
        self.selected = self.selection[-1] if self.selection else None
        self._style_tiles()
        self.on_select(self.selected)

    def _context(self, event, icon_id: str):
        if icon_id not in self.selection:
            self.select(icon_id)
        if self.on_menu:
            self.on_menu(event, list(self.selection))

    def _style_tiles(self):
        chosen = set(self.selection)
        for i, b in self.tiles.items():
            on = i in chosen
            b.configure(fg_color=C["bubble"] if on else "transparent",
                        text_color=C["text"] if on else C["muted"])

    def _sync_images(self, ids):
        """Bring the images of the given tiles up to date with the current style (others stay stale
        until they become visible, so dragging a slider only re-renders what is on screen)."""
        stamp = (self.thumbs.stamp(), self.guides)
        for i in ids:
            if self._stamps.get(i) != stamp:
                self.tiles[i].configure(image=self.thumbs.image(i, TILE_ICON, self.guides))
                self._stamps[i] = stamp

    def set_guides(self, on: bool):
        self.guides = on
        self.restyle()

    def restyle(self):
        self._sync_images(self.visible_ids())

    def refresh_icon(self, icon_id: str):
        self.thumbs.forget(icon_id)
        self._stamps.pop(icon_id, None)
        if icon_id in self.tiles:
            self._sync_images([icon_id])


class Detail(ctk.CTkScrollableFrame):
    """Right-hand panel. Top: the selected icon in the current style, at several sizes. Below, two
    tabs: Icon (tags, notes, depth flag, replace/remove) and Style (theme, box, depth, stroke)."""

    def __init__(self, master, thumbs: Thumbs, actions: dict[str, Callable],
                 make_style_panel: Callable[[ctk.CTkFrame], ctk.CTkFrame]):
        super().__init__(master, fg_color=C["surface"], corner_radius=RADIUS, width=290,
                         scrollbar_button_color=C["scrollbar"], scrollbar_button_hover_color=C["scrollbar_hover"])
        ui.autohide_scrollbar(self)
        self.thumbs, self.act = thumbs, actions
        self.icon_id: str | None = None
        self.guides = False
        self._arm_job = None
        self._used: list[str] = []
        self.grid_columnconfigure(0, weight=1)

        # --- preview block
        self.preview = ctk.CTkFrame(self, fg_color="transparent")
        self.preview.grid_columnconfigure(0, weight=1)
        self.big = ctk.CTkLabel(self.preview, text="")
        self.big.grid(row=0, column=0, pady=(14, 6))
        row = ctk.CTkFrame(self.preview, fg_color="transparent")
        row.grid(row=1, column=0, pady=(0, 8))
        self.smalls = [ctk.CTkLabel(row, text="") for _ in range(4)]
        for k, lbl in enumerate(self.smalls):
            lbl.grid(row=0, column=k, padx=8)
        self.name = ui.label(self.preview, "", bold=True, size=ui.FONT_SIZE + 3)
        self.name.grid(row=2, column=0, sticky="w", padx=14)
        self.aliases = ui.label(self.preview, "", muted=True, size=ui.FONT_SIZE - 2)

        # --- tabs
        self.tabs = ctk.CTkSegmentedButton(
            self, values=["Icon", "Style"], command=self.set_tab, font=ui.font(), corner_radius=RADIUS,
            fg_color=C["hover"], selected_color=C["button"], selected_hover_color=C["button_hover"],
            unselected_color=C["hover"], unselected_hover_color=C["scrollbar"], text_color=C["text"])
        self.tabs.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 4))
        self.tabs.set("Icon")
        self.icon_tab = ctk.CTkFrame(self, fg_color="transparent")
        self.icon_tab.grid_columnconfigure(0, weight=1)
        self.style_tab = make_style_panel(self)
        self.tab = "Icon"
        self.icon_tab.grid(row=2, column=0, sticky="ew")

        self.hint = ui.label(self.icon_tab, "Select an icon.", muted=True)
        self.hint.grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.fields = ctk.CTkFrame(self.icon_tab, fg_color="transparent")
        self.fields.grid_columnconfigure(0, weight=1)
        f = self.fields
        ui.label(f, "Tags", muted=True, size=ui.FONT_SIZE - 2).grid(row=0, column=0, sticky="w", padx=14, pady=(6, 2))
        self.tags = ui.entry(f, "tags, separated by spaces")
        self.tags.grid(row=1, column=0, sticky="ew", padx=14)
        self.tags.bind("<Return>", lambda _e: self._save_tags())
        self.tags.bind("<FocusOut>", lambda _e: self._save_tags())
        ui.label(f, "Collections", muted=True, size=ui.FONT_SIZE - 2).grid(row=3, column=0, sticky="w", padx=14, pady=(14, 2))
        self.coll_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.coll_frame.grid(row=4, column=0, sticky="w", padx=14)
        links = ctk.CTkFrame(f, fg_color="transparent")
        links.grid(row=5, column=0, sticky="w", padx=14, pady=(14, 14))
        ui.link(links, "Rename…", lambda: self.icon_id and self.act["rename"](self.icon_id)).pack(side="left", padx=(0, 14))
        ui.link(links, "Replace artwork…", lambda: self.icon_id and self.act["replace"](self.icon_id)).pack(side="left", padx=(0, 14))
        self.remove_link = ui.link(links, "Remove", self._remove_click, tone="muted")
        self.remove_link.pack(side="left")

    # --- tabs
    def set_tab(self, name: str):
        self.tab = name
        self.tabs.set(name)
        if name == "Icon":
            self.style_tab.grid_remove()
            self.icon_tab.grid(row=2, column=0, sticky="ew")
        else:
            self.icon_tab.grid_remove()
            self.style_tab.grid(row=2, column=0, sticky="ew")
        if self.act.get("tab"):
            self.act["tab"](name)

    # --- showing an icon
    def show(self, icon_id: str | None, lib: Library | None = None, guides: bool | None = None):
        self._disarm()
        if guides is not None:
            self.guides = guides
        self.icon_id = icon_id
        if icon_id is None or lib is None:
            self.style_tab.set_icon(None, True)
            self.preview.grid_forget()
            self.fields.grid_forget()
            self.hint.grid(row=0, column=0, sticky="w", padx=14, pady=10)
            return
        rec = lib.get(icon_id)
        self.preview.grid(row=0, column=0, sticky="ew")
        self.hint.grid_forget()
        self.fields.grid(row=1, column=0, sticky="ew")
        self.refresh_previews()
        self.name.configure(text=icon_id)
        used = lib.collections_using(icon_id)
        text = "Also known as: " + ", ".join(rec.aliases) if rec.aliases else ""
        self.aliases.configure(text=text)
        self.aliases.grid(row=3, column=0, sticky="w", padx=14) if text else self.aliases.grid_remove()
        self.tags.delete(0, "end")
        self.tags.insert(0, " ".join(rec.tags))
        self.style_tab.set_icon(icon_id, rec.depth == "auto")
        self._used = used
        self.refresh_collections()

    def refresh_collections(self):
        """One checkbox per collection: ticked = this icon is in it."""
        for w in self.coll_frame.winfo_children():
            w.destroy()
        if not self.icon_id:
            return
        names, member = self.act["collections_for"](self.icon_id)
        if not names:
            ui.label(self.coll_frame, "None yet. Ctrl+N makes one.", muted=True, size=ui.FONT_SIZE - 2).pack(anchor="w")
        for n in names:
            cb = ui.checkbox(self.coll_frame, n, n in member)
            cb.configure(command=lambda n=n, cb=cb: self.act["membership"](self.icon_id, n, bool(cb.get())))
            cb.pack(anchor="w", pady=2)

    def refresh_previews(self):
        """Re-render the previews (after a style/theme/guides change); leaves the fields alone."""
        if not self.icon_id:
            return
        self.big.configure(image=self.thumbs.image(self.icon_id, 160, self.guides))
        for lbl, px in zip(self.smalls, (16, 24, 32, 48)):
            lbl.configure(image=self.thumbs.image(self.icon_id, px, False))

    # --- edits
    def _save_tags(self):
        if self.icon_id:
            self.act["tags"](self.icon_id, [t for t in re.split(r"[,\s]+", self.tags.get()) if t])

    def _remove_click(self):
        if not self.icon_id:
            return
        if self._arm_job:                                   # second click
            icon_id = self.icon_id
            self._disarm()
            self.act["remove"](icon_id)
            return
        text = "Used in " + ", ".join(self._used) + ". Click again to remove" if self._used else "Click again to remove"
        self.remove_link.configure(text=text, text_color=C["error"])
        self._arm_job = self.after(3000, self._disarm)

    def _disarm(self):
        if self._arm_job:
            self.after_cancel(self._arm_job)
            self._arm_job = None
        self.remove_link.configure(text="Remove", text_color=C["muted"])


class ImportDialog(ctk.CTkToplevel):
    """Shows the cleaned artwork and any warnings, then asks for the ID and tags (add) or just
    confirms (replace). `on_confirm(icon_id, tags)` returns an error message, or None when done."""

    def __init__(self, master, thumbs: Thumbs, result: CleanResult, mode: str, filename: str,
                 on_confirm: Callable[[str, list[str]], str | None], target: str = ""):
        super().__init__(master, fg_color=C["window"])
        self.on_confirm = on_confirm
        self.title("Import icon" if mode == "add" else f"Replace {target}")
        self.resizable(False, False)
        self.transient(master)
        self.bind("<Escape>", lambda _e: self.destroy())
        p = ui.Panel(self)
        p.pack(fill="both", expand=True, padx=GUTTER, pady=(GUTTER, 0))
        p.grid_columnconfigure(1, weight=1)
        ui.label(p, f"{'Import' if mode == 'add' else 'Replace ' + target}: {filename}", bold=True).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 4))
        row = 1
        self.id_entry = self.tag_entry = None
        if result.errors:
            for e in result.errors:
                error_label(p, "• " + e, wraplength=340).grid(
                    row=row, column=0, columnspan=2, sticky="w", padx=14, pady=2)
                row += 1
        else:
            img = thumbs.from_icon(parse_svg(result.svg), 96, guides=True)
            ctk.CTkLabel(p, text="", image=img).grid(row=row, column=0, columnspan=2, pady=6)
            row += 1
            for w in result.warnings:
                ui.label(p, "! " + w, muted=True, wraplength=340, size=ui.FONT_SIZE - 2).grid(
                    row=row, column=0, columnspan=2, sticky="w", padx=14, pady=1)
                row += 1
            if mode == "add":
                ui.label(p, "ID").grid(row=row, column=0, sticky="w", padx=(14, 10), pady=(8, 2))
                self.id_entry = ui.entry(p, "e.g. arrow-left", width=220)
                self.id_entry.insert(0, suggest_id(filename))
                self.id_entry.grid(row=row, column=1, sticky="w", padx=(0, 14), pady=(8, 2))
                ui.label(p, "Tags").grid(row=row + 1, column=0, sticky="w", padx=(14, 10), pady=2)
                self.tag_entry = ui.entry(p, "optional", width=220)
                self.tag_entry.grid(row=row + 1, column=1, sticky="w", padx=(0, 14), pady=2)
                row += 2
        self.error = error_label(p, "", wraplength=340)
        self.error.grid(row=row, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 10))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(anchor="e", padx=GUTTER, pady=GUTTER)
        ui.button(bar, "Close" if result.errors else "Cancel", self.destroy).pack(side="left", padx=(0, 6))
        if not result.errors:
            ui.button(bar, "Add" if mode == "add" else "Replace", self._confirm).pack(side="left")
            self.bind("<Return>", lambda _e: self._confirm())
        self.after(150, lambda: (self.id_entry or self).focus())

    def _confirm(self):
        icon_id = self.id_entry.get().strip() if self.id_entry else ""
        tags = re.split(r"[,\s]+", self.tag_entry.get()) if self.tag_entry else []
        try:
            err = self.on_confirm(icon_id, [t for t in tags if t])
        except LibraryError as e:
            err = str(e)
        if err:
            self.error.configure(text=err)
        else:
            self.destroy()
