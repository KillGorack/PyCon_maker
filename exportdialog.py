"""Export dialog: pick what to export, the formats and themes, and a folder; shows the result."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

import dave_theme as ui
from dave_theme import C, GUTTER
from iconlib.collections import slugify
from iconlib.export import ExportError, ExportOptions, ExportResult, export
from iconlib.library import Library, LibraryError
from iconlib.style import Style
from iconlib.themes import ThemeStore

MODES = {"Themed: CSS variables (web)": "themed", "Baked: fixed colors": "baked"}


def open_folder(path: Path):
    """Show a folder in the system file manager (Linux, Windows or macOS)."""
    try:
        if sys.platform == "win32":
            os.startfile(path)                       # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def style_summary(style: Style) -> str:
    box = "no box" if style.box == "none" else f"{style.box} box, padding {style.padding:g}" + (
        f", roundness {style.radius * 100:.0f}%" if style.box == "rounded" else "")
    return (f"{box} · depth {'off' if not style.depth else f'{style.depth:g}'}"
            + (f" · stroke {style.stroke:g}" if style.stroke is not None else " · stroke as drawn"))


class ExportDialog(ctk.CTkToplevel):
    def __init__(self, master, lib: Library, store: ThemeStore, style: Style, current_theme: str,
                 sources: list[tuple[str, list[str]]], saved: dict, on_saved: Callable[[dict], None]):
        super().__init__(master, fg_color=C["window"])
        self.lib, self.store, self.style, self.sources = lib, store, style, dict(sources)
        self.saved, self.on_saved = dict(saved), on_saved
        self.title("Export icons")
        self.resizable(False, False)
        self.transient(master)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._thread: threading.Thread | None = None
        self._outcome: tuple | None = None
        self.done = False                                          # set when an export finished (for tests)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        self._build_form(current_theme, [s[0] for s in sources])
        self.after(150, self.focus)

    # ---------------------------------------------------------------- form
    def _panel(self, title: str) -> ui.Panel:
        p = ui.Panel(self.form)
        p.pack(fill="x", padx=GUTTER, pady=(GUTTER, 0))
        p.grid_columnconfigure(1, weight=1)
        ui.label(p, title, bold=True).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 2))
        return p

    def _build_form(self, current_theme: str, source_names: list[str]):
        sv = self.saved
        self.form = ctk.CTkFrame(self.body, fg_color="transparent")
        self.form.pack(fill="both", expand=True)

        p = self._panel("What to export")
        self.source = ui.quiet_select(p, source_names, self._source_changed, width=330)
        self.source.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(2, 10))

        p = self._panel("Formats")
        self.svg = ui.checkbox(p, "SVG files (one per icon)", sv.get("svg", True))
        self.sprite = ui.checkbox(p, "SVG sprite (one file, use with <use href>)", sv.get("sprite", True))
        self.png = ui.checkbox(p, "PNG images (colors baked in, transparent)", sv.get("png", False))
        for r, cb in enumerate((self.svg, self.sprite, self.png), start=1):
            cb.grid(row=r, column=0, columnspan=2, sticky="w", padx=14, pady=3)
        ui.label(p, "Colors").grid(row=4, column=0, sticky="w", padx=(14, 10), pady=(8, 3))
        self.mode = ui.quiet_select(p, list(MODES), None, width=250)
        self.mode.set(next(k for k, v in MODES.items() if v == sv.get("mode", "themed")))
        self.mode.grid(row=4, column=1, sticky="w", pady=(8, 3))
        self.cc = ui.checkbox(p, "Main color follows the page's text color (currentColor)", sv.get("current_color", False))
        self.cc.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=3)
        ui.label(p, "SVG size (px)").grid(row=6, column=0, sticky="w", padx=(14, 10), pady=3)
        self.svg_size = ui.entry(p, "48", width=90)
        self.svg_size.insert(0, str(sv.get("svg_size", 48)))
        self.svg_size.grid(row=6, column=1, sticky="w", pady=3)
        ui.label(p, "PNG sizes (px)").grid(row=7, column=0, sticky="w", padx=(14, 10), pady=(3, 10))
        self.png_sizes = ui.entry(p, "32, 64", width=160)
        self.png_sizes.insert(0, ", ".join(str(s) for s in sv.get("png_sizes", (32, 64))))
        self.png_sizes.grid(row=7, column=1, sticky="w", pady=(3, 10))

        p = self._panel("Themes")
        from stylepanel import APP_THEME
        names = [n for n in self.store.names() if n != APP_THEME]
        want = sv.get("themes") or [current_theme if current_theme != APP_THEME else names[0]]
        self.theme_boxes: dict[str, ctk.CTkCheckBox] = {}
        for r, n in enumerate(names, start=1):
            cb = ui.checkbox(p, n, n in want)
            cb.grid(row=r, column=0, columnspan=2, sticky="w", padx=14, pady=2)
            self.theme_boxes[n] = cb
        ui.info(p, "The first ticked theme is the default: the :root block in the CSS, and the colors used "
                "when a file is shown without your CSS.").grid(row=0, column=1, sticky="e", padx=14, pady=(8, 2))
        p.grid_rowconfigure(len(names) + 1, minsize=8)

        p = self._panel("Style (as previewed)")
        ui.label(p, style_summary(self.style), muted=True).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 10))

        p = self._panel("Folder")
        self.folder = ui.entry(p, "choose a folder", width=300)
        self.folder.grid(row=1, column=0, sticky="w", padx=(14, 6), pady=(2, 10))
        ui.button(p, "Browse…", self._browse, width=80).grid(row=1, column=1, sticky="w", pady=(2, 10))

        self.error = ui.label(self.form, "", wraplength=420)
        self.error.configure(text_color=C["error"])
        self.error.pack(anchor="w", padx=GUTTER + 4, pady=(8, 0))
        bar = ctk.CTkFrame(self.form, fg_color="transparent")
        bar.pack(fill="x", padx=GUTTER, pady=GUTTER)
        self.go = ui.button(bar, "Export", self._start, width=90)
        self.go.pack(side="right")
        ui.button(bar, "Cancel", self.destroy, width=80).pack(side="right", padx=(0, 6))
        self.count = ui.label(bar, "", muted=True)
        self.count.pack(side="left", padx=4)
        self._auto_folder = ""
        self._source_changed(self.source.get())

    def _source_changed(self, name: str):
        """Update the icon count, and the suggested folder unless the user has typed their own."""
        self.count.configure(text=f"{len(self.sources[name])} icons")
        base = Path(self.saved.get("dir") or Path.home() / "icon-exports")
        suggestion = str(base / slugify(self._label(name)))
        if self.folder.get().strip() in ("", self._auto_folder):
            self.folder.delete(0, "end")
            self.folder.insert(0, suggestion)
        self._auto_folder = suggestion

    @staticmethod
    def _label(source_name: str) -> str:
        return source_name.split(":", 1)[-1].split("(")[0].strip() or "icons"

    def _browse(self):
        start = Path(self.folder.get()).parent
        d = filedialog.askdirectory(parent=self, title="Export to which folder?",
                                    initialdir=start if start.exists() else Path.home())
        if d:
            chosen = Path(d)
            reusable = not any(chosen.iterdir()) or (chosen / "manifest.json").exists()   # empty, or an earlier export
            self.folder.delete(0, "end")
            self.folder.insert(0, str(chosen if reusable else chosen / slugify(self._label(self.source.get()))))

    # -------------------------------------------------------------- running
    def _read(self) -> tuple[list[str], ExportOptions, list, Path]:
        try:
            sizes = tuple(int(x) for x in self.png_sizes.get().replace(",", " ").split())
            svg_size = int(self.svg_size.get())
        except ValueError:
            raise ExportError("sizes must be whole numbers (PNG sizes separated by commas)")
        chosen = [n for n, cb in self.theme_boxes.items() if cb.get()]
        themes = [self.store.get(n) for n in chosen]
        opts = ExportOptions(name=self._label(self.source.get()), svg=bool(self.svg.get()),
                             sprite=bool(self.sprite.get()), png=bool(self.png.get()),
                             mode=MODES[self.mode.get()], svg_size=svg_size, png_sizes=sizes or (32, 64),
                             current_color=bool(self.cc.get()))
        folder = self.folder.get().strip()
        if not folder:
            raise ExportError("choose a folder")
        return self.sources[self.source.get()], opts, themes, Path(folder).expanduser()

    def _start(self):
        if self._thread:
            return
        self.error.configure(text="")
        try:
            ids, opts, themes, out = self._read()
        except ExportError as e:
            self.error.configure(text=str(e))
            return
        self.go.configure(text="Exporting…", state="disabled")

        def work():
            try:
                self._outcome = ("ok", export(self.lib, ids, self.style, themes, opts, out))
            except (ExportError, LibraryError, OSError) as e:
                self._outcome = ("error", str(e))

        self._opts, self._themes = opts, themes
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self.after(100, self._poll)

    def _poll(self):
        if self._outcome is None:
            self.after(100, self._poll)
            return
        kind, value = self._outcome
        self._thread, self._outcome = None, None
        self.go.configure(text="Export", state="normal")
        if kind == "error":
            self.error.configure(text=value)
            return
        self.on_saved({"svg": self._opts.svg, "sprite": self._opts.sprite, "png": self._opts.png,
                       "mode": self._opts.mode, "svg_size": self._opts.svg_size, "png_sizes": list(self._opts.png_sizes),
                       "current_color": self._opts.current_color, "themes": [t.name for t in self._themes],
                       "dir": str(value.out_dir.parent)})
        self._show_result(value)

    def _show_result(self, r: ExportResult):
        self.form.pack_forget()
        box = ctk.CTkFrame(self.body, fg_color="transparent")
        box.pack(fill="both", expand=True)
        p = ui.Panel(box)
        p.pack(fill="x", padx=GUTTER, pady=(GUTTER, 0))
        ui.label(p, f"Exported {len(r.icons)} icons", bold=True).pack(anchor="w", padx=14, pady=(10, 2))
        ui.label(p, f"{len(r.files)} files in {r.out_dir}", muted=True, wraplength=420).pack(anchor="w", padx=14)
        notes = []
        if r.flat:
            notes.append(f"Kept flat (depth is on, but these are flagged off or hand-toned): {', '.join(r.flat)}")
        if r.skipped:
            notes.append("Skipped: " + "; ".join(r.skipped))
        for n in notes:
            lbl = ui.label(p, n, muted=True, wraplength=420, size=ui.FONT_SIZE - 2)
            lbl.pack(anchor="w", padx=14, pady=(6, 0))
        ui.link(p, "Open folder", lambda: open_folder(r.out_dir)).pack(anchor="w", padx=14, pady=(10, 12))
        ui.button(box, "Close", self.destroy, width=80).pack(anchor="e", padx=GUTTER, pady=GUTTER)
        self.result = r
        self.done = True
