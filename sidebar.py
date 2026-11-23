"""Collections sidebar: "All icons" pinned on top, then the saved collections."""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

import dave_theme as ui
from dave_theme import C, GUTTER, RADIUS
from iconlib.collections import Collection, CollectionStore


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, store: CollectionStore, on_open: Callable[[Collection | None], None],
                 on_delete: Callable[[Collection], None], on_rename: Callable[[Collection], None],
                 on_delete_menu: Callable[[Collection], None]):
        super().__init__(master, fg_color="transparent", width=230)
        self.store, self.on_open = store, on_open
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        top = ui.Panel(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, GUTTER))
        top.grid_columnconfigure(0, weight=1)
        self.all_btn = ctk.CTkButton(top, text="All icons", anchor="w", font=ui.font(), fg_color="transparent",
                                     hover_color=C["hover"], corner_radius=RADIUS, command=lambda: self._open(None))
        self.all_btn.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.list = ui.ItemList(
            self, title=self._title, on_open=self._open, on_delete=on_delete,
            menu_items=lambda c: [("Rename…", lambda: on_rename(c)), ("Delete…", lambda: on_delete_menu(c))],
            placeholder="Search collections", empty_text="No collections yet.\nCtrl+N makes one.")
        self.list.grid(row=1, column=0, sticky="nsew")
        self.total = 0

    def _title(self, c: Collection) -> str:
        present, missing = self.store.members(c)
        return f"{c.name}  ({len(present)}{f', {len(missing)} missing' if missing else ''})"

    def _open(self, c):
        self.list.selected = c
        self._style_all()
        self.on_open(c)
        self.list.refresh()

    def refresh(self, total: int | None = None, selected: Collection | None = ...):
        """Re-read the store (after any change). `selected` None = All icons."""
        if total is not None:
            self.total = total
        if selected is not ...:
            self.list.selected = selected
        self.all_btn.configure(text=f"All icons  ({self.total})")
        self._style_all()
        self.list.set_items(self.store.all())

    def open_all(self):
        self._open(None)

    def _style_all(self):
        """The open view is always visible: 'All icons' gets a filled, bold row when it is the one shown."""
        on = self.list.selected is None
        self.all_btn.configure(fg_color=C["hover"] if on else "transparent",
                               text_color=C["text_strong"] if on else C["text"],
                               font=ui.font(weight="bold" if on else "normal"))
