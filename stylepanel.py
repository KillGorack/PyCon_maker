"""Style tab (theme, box, padding, radius, depth, thickness) and the theme editor dialog."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser
from typing import Callable

import customtkinter as ctk

import dave_theme as ui
from dave_theme import C, GUTTER
from iconlib.preview import tone_palette
from iconlib.style import DEFAULT_DEPTH, Style, Theme, is_hex
from iconlib.themes import ThemeError, ThemeStore

DEFAULT_STROKE = 2.0              # line thickness every style starts with; drawn thickness is never used in the UI
APP_THEME = "App colors"          # special entry: follows the app's own light/dark colors


def app_default_style() -> Style:
    return Style(stroke=DEFAULT_STROKE)


def with_thickness(style: Style) -> Style:
    """Older saved styles may say 'as drawn' (no thickness); the UI always sets one."""
    return style if style.stroke is not None else style.with_(stroke=DEFAULT_STROKE)


BOX_LABELS = {"None": "none", "Square": "square", "Rounded": "rounded", "Circle": "circle"}


def swatch(master, color: str, size: int = 18, command: Callable | None = None) -> tk.Frame:
    f = tk.Frame(master, width=size, height=size, bg=color, highlightthickness=1,
                 highlightbackground=ui.cur("rule"), cursor="hand2" if command else "")
    if command:
        f.bind("<Button-1>", lambda _e: command())
    return f


class StylePanel(ui.Form):
    """Live style controls, grouped as Colors / Box / Effects (a `Form`: label | control rows). Controls
    that don't apply to the current choices are hidden (no box: no padding or corners; circle or square:
    no corner roundness). `on_change(style)` and `on_theme(name)` are called (debounced) as the user adjusts
    them; the owner re-renders. `edit(name|None)` opens the theme editor."""

    SLIDER_W = 100

    def __init__(self, master, store: ThemeStore, on_change: Callable[[Style], None],
                 on_theme: Callable[[str], None], edit: Callable[[str | None], None],
                 on_flag: Callable[[bool], None]):
        super().__init__(master)
        self.store, self.on_change, self.on_theme, self.edit = store, on_change, on_theme, edit
        self.on_flag = on_flag
        self.icon_id: str | None = None
        self.style = app_default_style()
        self.where_text = ""
        self._job = None

        # ---- colors
        self.heading("Colors")
        self.theme_menu = ui.quiet_select(self, [APP_THEME], self._theme_picked, width=150)
        self.row("Theme", self.theme_menu, key="theme")
        line = ctk.CTkFrame(self, fg_color="transparent")
        self.swatches = ctk.CTkFrame(line, fg_color="transparent")
        self.swatches.pack(side="left", padx=(0, 10))
        ui.link(line, "Edit", lambda: self.edit(self.theme_menu.get())).pack(side="left", padx=(0, 10))
        ui.link(line, "New", lambda: self.edit(None)).pack(side="left")
        self.row("", line, key="swatches")

        # ---- box
        self.heading("Box")
        self.box_menu = ui.quiet_select(self, list(BOX_LABELS), self._changed, width=150)
        self.row("Shape", self.box_menu, key="shape")
        self.pad_box, self.pad = ui.slider(self, 0, 8, 16, 3, lambda v: f"{v:.1f}", width=self.SLIDER_W)
        self.row("Padding", self.pad_box, "Space between the icon and the edge of the box.", key="padding")
        self.rad_box, self.rad = ui.slider(self, 0, 50, 50, 25, lambda v: f"{v:.0f}%", width=self.SLIDER_W)
        self.row("Corners", self.rad_box, "How rounded the box corners are.", key="corners")

        # ---- effects
        self.heading("Effects")
        self.depth_box, self.depth = ui.slider(self, 0, 0.6, 12, 0, lambda v: "off" if v < 0.01 else f"{v:.2f}",
                                               width=self.SLIDER_W)
        self.row("Depth", self.depth_box, "Adds a shade and a highlight copy of the lines behind them. Looks best at medium and large sizes. "
            "Icons flagged 'no automatic depth', or drawn with their own tones, stay flat.", key="depth")
        self.flag = ui.checkbox(self, "Allow depth", True, command=lambda: self.on_flag(bool(self.flag.get())))
        self.row("This icon", self.flag, "Untick for an icon too detailed for the shade and highlight effect. It then stays flat, even when "
            "an export has depth turned on.", key="flag")
        self.stroke_box, self.stroke = ui.slider(self, 0.5, 3.5, 12, DEFAULT_STROKE, lambda v: f"{v:.2f}",
                                                 width=self.SLIDER_W)
        self.row("Thickness", self.stroke_box, "Line thickness for every icon in the export. The thickness an icon was drawn with is ignored, so "
            "the whole set stays consistent.", key="width")

        foot = ctk.CTkFrame(self, fg_color="transparent")
        ui.link(foot, "Reset style", self.reset, tone="muted").pack(side="left")
        ui.info(foot, lambda: self.where_text).pack(side="left", padx=(8, 0))
        foot.grid(row=self._r, column=0, columnspan=2, sticky="w", padx=ui.INSET, pady=(16, 14))
        for sl in (self.pad, self.rad, self.depth, self.stroke):
            sl.configure(command=self._slid(sl))
        self._enable()

    # ------------------------------------------------------------------ plumbing
    def _fmt(self, s, v):
        return {self.pad: f"{v:.1f}", self.rad: f"{v:.0f}%", self.depth: "off" if v < 0.01 else f"{v:.2f}",
                self.stroke: f"{v:.2f}"}[s]

    def _slid(self, slider):
        label = slider.master.winfo_children()[0]

        def cmd(v):
            label.configure(text=self._fmt(slider, v))
            self._changed()
        return cmd

    def _enable(self, *_):
        """Show only the controls that matter for the current choices."""
        box = BOX_LABELS[self.box_menu.get()]
        self.show("padding", box != "none")
        self.show("corners", box == "rounded")
        self.show("flag", self.icon_id is not None)           # a per-icon setting: only with an icon selected

    def _theme_picked(self, name):
        self._swatches(name)
        self.on_theme(name)

    def _changed(self, *_):
        self._enable()
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(120, self._emit)

    def _emit(self):
        self._job = None
        self.style = self.read()
        self.on_change(self.style)

    def read(self) -> Style:
        return Style(box=BOX_LABELS[self.box_menu.get()], padding=round(self.pad.get(), 2),
                     radius=round(self.rad.get() / 100, 3), depth=round(self.depth.get(), 2),
                     stroke=round(self.stroke.get(), 2))

    def load(self, style: Style, theme_name: str):
        """Show `style` / `theme_name` in the controls without notifying the owner."""
        style = with_thickness(style)
        self.style = style
        self.refresh_themes(theme_name)
        self.box_menu.set(next(k for k, v in BOX_LABELS.items() if v == style.box))
        for s, v in ((self.pad, style.padding), (self.rad, style.radius * 100), (self.depth, style.depth),
                     (self.stroke, style.stroke)):
            s.set(v)
            s.master.winfo_children()[0].configure(text=self._fmt(s, v))
        self._enable()

    def refresh_themes(self, current: str):
        self.theme_menu.configure(values=[APP_THEME, *self.store.names()])
        self.theme_menu.set(current)
        self._swatches(current)

    def _swatches(self, name: str):
        for w in self.swatches.winfo_children():
            w.destroy()
        if name == APP_THEME:
            return
        t = self.store.get(name)
        for col in (t.main, t.shade, t.light, t.box):
            swatch(self.swatches, col).pack(side="left", padx=(0, 3))

    def set_icon(self, icon_id: str | None, allowed: bool):
        """Tell the panel which icon is selected, so its own depth setting can be shown."""
        self.icon_id = icon_id
        self.flag.select() if allowed else self.flag.deselect()
        self._enable()

    def set_where(self, collection_name: str | None):
        self.where_text = (f"Style changes are saved with the collection \u201c{collection_name}\u201d." if collection_name
                           else "Style changes apply to the whole app. Open a collection to save a style with it.")

    def reset(self):
        self.load(app_default_style(), self.theme_menu.get())
        self._emit()


class ThemeEditor(ctk.CTkToplevel):
    """Edit or create a user theme. Built-in themes open as a copy. `on_saved(name)` / `on_deleted()`."""

    FIELDS = (("main", "Main"), ("shade", "Shade"), ("light", "Highlight"), ("box", "Box fill"), ("bg", "Preview page"))

    def __init__(self, master, store: ThemeStore, base: Theme, is_new: bool,
                 on_saved: Callable[[str], None], on_deleted: Callable[[], None]):
        super().__init__(master, fg_color=C["window"])
        self.store, self.on_saved, self.on_deleted = store, on_saved, on_deleted
        self.title("New theme" if is_new else f"Theme: {base.name}")
        self.resizable(False, False)
        self.transient(master)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.original = None if (is_new or base.name in store.builtin_names) else base.name
        p = ui.Panel(self)
        p.pack(fill="both", expand=True, padx=GUTTER, pady=(GUTTER, 0))
        p.grid_columnconfigure(1, weight=1)
        ui.label(p, "Name").grid(row=0, column=0, sticky="w", padx=(14, 10), pady=(12, 4))
        self.name = ui.entry(p, "theme name", width=170)
        self.name.insert(0, base.name if self.original or is_new else f"{base.name} copy")
        self.name.grid(row=0, column=1, sticky="w", padx=(0, 14), pady=(12, 4))
        self.entries: dict[str, ctk.CTkEntry] = {}
        self.sw: dict[str, tk.Frame] = {}
        for i, (key, text) in enumerate(self.FIELDS, start=1):
            ui.label(p, text).grid(row=i, column=0, sticky="w", padx=(14, 10), pady=4)
            line = ctk.CTkFrame(p, fg_color="transparent")
            line.grid(row=i, column=1, sticky="w", padx=(0, 14), pady=4)
            e = ui.entry(line, "#rrggbb", width=100)
            e.insert(0, getattr(base, key) or "")
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda _e, k=key: self._sync(k))
            s = swatch(line, getattr(base, key) or ui.cur("surface"), 24, lambda k=key: self._pick(k))
            s.pack(side="left", padx=(8, 0))
            self.entries[key], self.sw[key] = e, s
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.grid(row=len(self.FIELDS) + 1, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 2))
        ui.link(row, "Derive shade and highlight from main", self._derive).pack(side="left")
        self.error = ui.label(p, "", wraplength=300)
        self.error.configure(text_color=C["error"])
        self.error.grid(row=len(self.FIELDS) + 2, column=0, columnspan=2, sticky="w", padx=14, pady=(2, 10))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=GUTTER, pady=GUTTER)
        if self.original:
            ui.link(bar, "Delete theme", self._delete, tone="error").pack(side="left", padx=4)
        ui.button(bar, "Save", self._save).pack(side="right")
        ui.button(bar, "Cancel", self.destroy).pack(side="right", padx=(0, 6))
        self.after(150, self.focus)

    def _sync(self, key):
        v = self.entries[key].get().strip()
        if is_hex(v):
            self.sw[key].configure(bg=v)

    def _pick(self, key):
        cur = self.entries[key].get().strip()
        _rgb, hexv = colorchooser.askcolor(color=cur if is_hex(cur) else None, parent=self, title=f"{key} color")
        if hexv:
            self.entries[key].delete(0, "end")
            self.entries[key].insert(0, hexv)
            self._sync(key)

    def _derive(self):
        main = self.entries["main"].get().strip()
        if not is_hex(main):
            self.error.configure(text="Enter a valid main color first (like #2dd4bf).")
            return
        self.error.configure(text="")
        pal = tone_palette(main)
        for k in ("shade", "light"):
            self.entries[k].delete(0, "end")
            self.entries[k].insert(0, pal[k])
            self._sync(k)

    def _save(self):
        vals = {k: e.get().strip() or None for k, e in self.entries.items()}
        theme = Theme(self.name.get().strip(), vals["main"] or "", vals["shade"] or "", vals["light"] or "",
                      vals["box"] or "", vals["bg"])
        try:
            theme.validate()
            self.store.save_theme(theme)
        except (ValueError, ThemeError) as e:
            self.error.configure(text=str(e))
            return
        self.on_saved(theme.name)
        self.destroy()

    def _delete(self):
        if ui.ask(self, "Delete theme", f"Delete “{self.original}”? Exports that use it fall back to the default.",
                  "Delete", danger=True):
            self.store.delete(self.original)
            self.on_deleted()
            self.destroy()
