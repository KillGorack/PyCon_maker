"""Small modal dialogs in the Dave-Standard style."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

import dave_theme as ui
from dave_theme import C, GUTTER


def prompt(master, title: str, label: str, initial: str = "", ok: str = "OK",
           on_ok: Callable[[str], str | None] | None = None) -> str | None:
    """Ask for one line of text. `on_ok(text)` may return an error message (shown in the dialog,
    which stays open) or None to accept. Returns the accepted text, or None if cancelled."""
    result = {"text": None}
    win = ctk.CTkToplevel(master, fg_color=C["window"])
    win.title(title)
    win.resizable(False, False)
    win.transient(master)
    p = ui.Panel(win)
    p.pack(fill="both", expand=True, padx=GUTTER, pady=(GUTTER, 0))
    ui.label(p, title, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
    ui.label(p, label, muted=True, wraplength=320).pack(anchor="w", padx=14)
    entry = ui.entry(p, "", width=320)
    entry.insert(0, initial)
    entry.pack(padx=14, pady=(6, 2))
    err = ui.label(p, "", wraplength=320)
    err.configure(text_color=C["error"])
    err.pack(anchor="w", padx=14, pady=(0, 10))
    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(anchor="e", padx=GUTTER, pady=GUTTER)

    def accept(_e=None):
        text = entry.get().strip()
        msg = on_ok(text) if on_ok else None
        if msg:
            err.configure(text=msg)
            return
        result["text"] = text
        win.destroy()

    ui.button(row, "Cancel", win.destroy).pack(side="left", padx=(0, 6))
    ui.button(row, ok, accept).pack(side="left")
    win.bind("<Escape>", lambda _e: win.destroy())
    entry.bind("<Return>", accept)

    def ready():
        win.focus()
        win.grab_set()
        entry.focus_set()
        entry.select_range(0, "end")

    win.after(150, ready)
    master.wait_window(win)
    return result["text"]
