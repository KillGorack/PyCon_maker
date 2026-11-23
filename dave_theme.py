"""
Dave-Standard theme for CustomTkinter  —  v0.1
===============================================
Personal look for side projects, taken from LULIM
(002_Software_Projects\\Python\\LULIM): quiet floating panels, flat icon buttons,
neutral charcoal dark theme and a warm parchment light theme.

Do not edit per app. Apps import from here so every side project shares one look.
Colors are (light, dark) tuples; ctk.set_appearance_mode() switches them, and icons
(CTkImage with a light and a dark tint) follow automatically.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

HERE = Path(__file__).resolve().parent
ICON_DIR = HERE / "icons"

# =============================================================================
# COLOR TOKENS  (light, dark), names and values from LULIM's THEMES dict
# =============================================================================
C = {
    "window":        ("#bdb5a3", "#262626"),   # window background, the gaps between panels
    "surface":       ("#ded6c3", "#171717"),   # panels: content, toolbar, sidebar, sections
    "text":          ("#332d24", "#b1b1b1"),   # normal text, icons
    "text_strong":   ("#252118", "#d4d4d4"),   # headings, emphasized content (LULIM ai_text)
    "muted":         ("#6b6252", "#8f8f8f"),   # hints, notes, placeholders, quiet icons
    "bubble":        ("#c9c0aa", "#2e2e2e"),   # raised chip / chat bubble
    "bubble_text":   ("#252118", "#b1b1b1"),
    "error":         ("#a33a2a", "#f87171"),   # errors, armed delete, recording
    "success":       ("#4d6a2c", "#a3b88a"),   # ok states (LULIM syn_string)
    "link":          ("#2f5d8a", "#8ab4f8"),   # text links / link-buttons
    "rule":          ("#b3a990", "#3a3a3a"),   # 1px dividers, tooltip border
    "button":        ("#8c806b", "#525252"),   # neutral filled buttons, checkbox fill
    "button_hover":  ("#756a58", "#737373"),
    "hover":         ("#cbc2ae", "#333333"),   # list/icon hover, quiet fills (LULIM list_hover)
    "scrollbar":     ("#a89e8a", "#404040"),
    "scrollbar_hover": ("#8c806b", "#525252"),
    # code blocks + syntax (for apps that show code)
    "code_bg":       ("#d1c8b2", "#262626"),
    "code_head":     ("#5c5344", "#9a9a9a"),
    "code_head_bg":  ("#c3b9a1", "#333333"),
    "syn_keyword":   ("#7a3d6c", "#c09bc8"),
    "syn_string":    ("#4d6a2c", "#a3b88a"),
    "syn_comment":   ("#7d725e", "#767676"),
    "syn_number":    ("#8a5220", "#d1a173"),
    "syn_builtin":   ("#2c6863", "#80b3ad"),
    "syn_func":      ("#2f5d8a", "#8eaed4"),
}

GUTTER = 10          # gap between panels and around the window edge
INSET = 14           # inner left/right margin of content inside a panel (use ONE inset per panel)
SLIDER_INSET = 6     # CTkSlider draws its track this far inside its widget (its border_width)
RADIUS = 6           # panel / control corners (CTk default, as in LULIM)
ICON_SIZE = 18       # toolbar icons
LIST_ICON_SIZE = 16  # icons inside list rows
BTN = 32             # square icon button size

FONT_SIZE = 13       # body text; Ctrl +/- zoom, Ctrl+0 resets
FONT_MIN, FONT_MAX = 9, 24


def cur(token: str) -> str:
    """Current-mode value of a color token, for plain Tk widgets (tk.Menu, tk.Frame, tooltips)."""
    light, dark = C[token]
    return dark if ctk.get_appearance_mode() == "Dark" else light


def ui_family() -> str:
    """The platform's UI font (Segoe UI on Windows, Cantarell/Noto on Linux...)."""
    return tkfont.nametofont("TkDefaultFont").actual("family")


def font(size: int | None = None, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=ui_family(), size=size or FONT_SIZE, weight=weight)


# =============================================================================
# THEME SWITCHING
# =============================================================================
_theme_listeners: list[Callable[[], None]] = []


def on_theme_change(fn: Callable[[], None]):
    """Register a callback for things CTk can't recolor itself (tk.Frame dividers, canvases)."""
    _theme_listeners.append(fn)


def set_mode(mode: str):
    """'dark' or 'light'."""
    ctk.set_appearance_mode(mode)
    for fn in list(_theme_listeners):
        try:
            fn()
        except tk.TclError:          # widget was destroyed
            _theme_listeners.remove(fn)


def setup(mode: str = "dark"):
    ctk.set_default_color_theme("blue")   # base only; every widget below sets its colors
    set_mode(mode)


# =============================================================================
# SETTINGS (JSON in the user's app-data folder)
# =============================================================================
def app_dir(app_name: str) -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / app_name


class Settings(dict):
    """dict that saves itself: settings["theme"] = "light" writes settings.json."""

    def __init__(self, app_name: str):
        self.path = app_dir(app_name) / "settings.json"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        super().__init__(data)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self, indent=2), encoding="utf-8")


# =============================================================================
# ICONS  — Lucide PNG masks (white, 96x96) tinted per theme
# =============================================================================
_mask_cache: dict[str, Image.Image] = {}


def _tint(name: str, color: str) -> Image.Image:
    if name not in _mask_cache:
        _mask_cache[name] = Image.open(ICON_DIR / f"{name}.png").convert("RGBA").getchannel("A")
    mask = _mask_cache[name]
    img = Image.new("RGBA", mask.size, color)
    img.putalpha(mask)
    return img


def icon(name: str, tone: str = "text", size: int = ICON_SIZE) -> ctk.CTkImage:
    """Icon from icons/<name>.png in the given color token; switches with the theme.
    To add icons: convert a Lucide SVG (lucide.dev) to a 96x96 white PNG in icons/."""
    light, dark = C[tone]
    return ctk.CTkImage(light_image=_tint(name, light), dark_image=_tint(name, dark), size=(size, size))


# =============================================================================
# TOOLTIP
# =============================================================================
class Tooltip:
    """Small label under a widget after the pointer rests on it. text may be a function
    (for toggles whose meaning changes). Polls instead of trusting <Leave>, because CTk
    widgets are several Tk widgets and send Leave while the pointer is still inside."""

    DELAY = 500

    def __init__(self, widget, text: str | Callable[[], str]):
        self.widget, self.text = widget, text
        self.tip = self.job = None
        self.waited, self.clicked = 0, False
        for w in (widget, *widget.winfo_children()):
            tk.Misc.bind(w, "<Enter>", self._enter, add="+")
            tk.Misc.bind(w, "<ButtonPress>", self._click, add="+")

    def _inside(self) -> bool:
        w = self.widget
        if not w.winfo_exists() or not w.winfo_ismapped():
            return False
        x, y = w.winfo_pointerxy()
        return (w.winfo_rootx() <= x < w.winfo_rootx() + w.winfo_width()
                and w.winfo_rooty() <= y < w.winfo_rooty() + w.winfo_height())

    def _enter(self, _e=None):
        if self.job is None:
            self.waited, self.clicked = 0, False
            self.job = self.widget.after(100, self._watch)

    def _click(self, _e=None):
        self.clicked = True
        self._hide()

    def _watch(self):
        self.job = None
        if not self._inside():
            self._hide()
            return
        self.waited += 100
        if self.tip is None and not self.clicked and self.waited >= self.DELAY:
            self._show()
        self.job = self.widget.after(100, self._watch)

    def _show(self):
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        w = self.widget
        self.tip = tk.Toplevel(w)
        self.tip.overrideredirect(True)
        tk.Label(self.tip, text=text, bg=cur("surface"), fg=cur("text"), padx=6, pady=2,
                 highlightthickness=1, highlightbackground=cur("rule"),
                 font=(ui_family(), 10)).pack()
        self.tip.update_idletasks()
        x = w.winfo_rootx() + (w.winfo_width() - self.tip.winfo_width()) // 2
        x = max(0, min(x, w.winfo_screenwidth() - self.tip.winfo_width()))
        self.tip.geometry(f"+{x}+{w.winfo_rooty() + w.winfo_height() + 4}")

    def _hide(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def info(master, text: str | Callable[[], str]) -> ctk.CTkLabel:
    """A small (i) that explains something on hover. This is the ONLY place explanations live:
    the UI has no note text under or beside controls. `text` may be a function (dynamic tips)."""
    lbl = ctk.CTkLabel(master, text="", image=icon("info", "muted", 14), width=18, height=18)
    Tooltip(lbl, lambda: "\n".join(textwrap.fill(line, 46) for line in
                                    (text() if callable(text) else text).split("\n")))
    return lbl


# =============================================================================
# BASIC COMPONENTS
# =============================================================================
class Panel(ctk.CTkFrame):
    """The building block: a rounded surface floating on the window color."""

    def __init__(self, master, **kw):
        kw.setdefault("fg_color", C["surface"])
        kw.setdefault("corner_radius", RADIUS)
        super().__init__(master, **kw)


def icon_button(master, name: str, command=None, tooltip: str | Callable[[], str] = "",
                tone: str = "text", size: int = ICON_SIZE) -> ctk.CTkButton:
    """Flat icon-only button: just the icon, hover fill. The everyday toolbar control."""
    b = ctk.CTkButton(master, text="", image=icon(name, tone, size), width=BTN, height=BTN,
                      corner_radius=RADIUS, fg_color="transparent", hover_color=C["hover"])
    b.configure(command=command)
    if tooltip:
        Tooltip(b, tooltip)
    return b


def set_icon(button: ctk.CTkButton, name: str, tone: str = "text", size: int = ICON_SIZE):
    """Swap a button's icon (toggles: sun/moon, volume-2/volume-x, mic red while on)."""
    button.configure(image=icon(name, tone, size))


def button(master, text: str, command=None, width: int = 80, **kw) -> ctk.CTkButton:
    """Neutral filled button (Save, Cancel, Test). There is no loud accent color on purpose."""
    return ctk.CTkButton(master, text=text, command=command, width=width, corner_radius=RADIUS,
                         fg_color=C["button"], hover_color=C["button_hover"],
                         text_color=C["text"], font=font(), **kw)


def link(master, text: str, command=None, tone: str = "link") -> ctk.CTkLabel:
    """Text link (Copy, Retry, Speak under content). Underlines on hover."""
    lbl = ctk.CTkLabel(master, text=text, text_color=C[tone], cursor="hand2",
                       font=font(FONT_SIZE - 1), height=18)
    if command:
        lbl.bind("<Button-1>", lambda _e: command())
    lbl.bind("<Enter>", lambda _e: lbl.configure(font=ctk.CTkFont(family=ui_family(), size=FONT_SIZE - 1, underline=True)))
    lbl.bind("<Leave>", lambda _e: lbl.configure(font=font(FONT_SIZE - 1)))
    return lbl


def label(master, text: str, muted: bool = False, size: int | None = None, bold: bool = False, **kw):
    return ctk.CTkLabel(master, text=text, anchor="w", justify="left",
                        text_color=C["muted"] if muted else C["text"],
                        font=font(size, "bold" if bold else "normal"), **kw)


def search_entry(master, placeholder: str = "Search", **kw) -> ctk.CTkEntry:
    """Borderless entry on the hover tone, like LULIM's 'Search chats'."""
    return ctk.CTkEntry(master, placeholder_text=placeholder, border_width=0, corner_radius=RADIUS,
                        fg_color=C["hover"], text_color=C["text"],
                        placeholder_text_color=C["muted"], font=font(), **kw)


def entry(master, placeholder: str = "", **kw) -> ctk.CTkEntry:
    return search_entry(master, placeholder, **kw)


def textbox(master, **kw) -> ctk.CTkTextbox:
    """Big text area (content / input). Same surface as panels, themed scrollbar."""
    kw.setdefault("fg_color", C["surface"])
    return ctk.CTkTextbox(master, wrap="word", corner_radius=RADIUS, font=font(),
                          text_color=C["text"], scrollbar_button_color=C["scrollbar"],
                          scrollbar_button_hover_color=C["scrollbar_hover"], border_width=0, **kw)


def quiet_select(master, values: list[str], command=None, width: int = 200) -> ctk.CTkOptionMenu:
    """One-tone pill dropdown (LULIM's model picker)."""
    return ctk.CTkOptionMenu(master, values=values, command=command, width=width,
                             corner_radius=RADIUS, font=font(), dropdown_font=font(),
                             fg_color=C["hover"], button_color=C["hover"],
                             button_hover_color=C["scrollbar"], text_color=C["text"],
                             dropdown_fg_color=C["surface"], dropdown_hover_color=C["hover"],
                             dropdown_text_color=C["text"])


def checkbox(master, text: str, checked: bool = False, **kw) -> ctk.CTkCheckBox:
    cb = ctk.CTkCheckBox(master, text=text, font=font(), text_color=C["text"], fg_color=C["button"],
                         hover_color=C["button_hover"], border_color=C["muted"],
                         checkmark_color=C["text"], corner_radius=4, border_width=2, **kw)
    if checked:
        cb.select()
    return cb


def slider(master, from_: float, to: float, steps: int, value: float,
           fmt: Callable[[float], str] = lambda v: f"{v:.1f}", width: int = 170):
    """Slider + live value label. Returns (frame, slider)."""
    box = ctk.CTkFrame(master, fg_color="transparent")
    box.inset = SLIDER_INSET      # Form.row uses this so the TRACK (not the widget) lines up with other controls
    val = ctk.CTkLabel(box, width=44, anchor="w", text_color=C["text"], font=font())
    s = ctk.CTkSlider(box, from_=from_, to=to, number_of_steps=steps, width=width, border_width=SLIDER_INSET,
                      fg_color=C["hover"], progress_color=C["button"], button_color=C["text"],
                      button_hover_color=C["text_strong"],
                      command=lambda v: val.configure(text=fmt(v)))
    s.set(value)
    val.configure(text=fmt(value))
    s.grid(row=0, column=0)
    val.grid(row=0, column=1, padx=(8, 0))
    return box, s


def divider(master, vertical: bool = True, length: int = 18) -> tk.Frame:
    """1px rule between toolbar groups. Plain tk.Frame: CTk won't draw 1px wide."""
    d = tk.Frame(master, width=1 if vertical else length, height=length if vertical else 1,
                 bd=0, bg=cur("rule"))
    on_theme_change(lambda: d.configure(bg=cur("rule")))
    return d


def _enable_wheel(sf: ctk.CTkScrollableFrame):
    """CTk 6 listens for Button-4/5 on Linux, but Tk >= 8.7 sends the X11 wheel as <MouseWheel>, so the
    wheel did nothing. Add it (Windows, macOS and older Tk already work through CTk itself).
    Scrolls only the area under the pointer, and only when its content overflows."""
    if not (sys.platform.startswith("linux") and tk.TkVersion >= 8.7):
        return

    def on_wheel(event):
        try:
            if sf._check_if_valid_scroll(event.widget) and sf._parent_canvas.yview() != (0.0, 1.0):
                steps = -round(event.delta / 120) or (-1 if event.delta > 0 else 1)
                sf._parent_canvas.yview_scroll(steps, "units")
        except (tk.TclError, AttributeError):        # the frame was destroyed
            pass

    sf.bind_all("<MouseWheel>", on_wheel, add="+")


def autohide_scrollbar(sf: ctk.CTkScrollableFrame):
    """Scroll polish for every CTkScrollableFrame: show the scrollbar only when the content overflows,
    and make the mouse wheel scroll it. Call it on every scrollable area."""
    _enable_wheel(sf)
    def check(_e=None):
        try:
            canvas = sf._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))      # CTk's own binding breaks if an app replaces it
            need = sf.winfo_reqheight() > canvas.winfo_height() + 1
            bar = sf._scrollbar
            if need and not bar.winfo_ismapped():
                bar.grid()
            elif not need and bar.winfo_ismapped():
                bar.grid_remove()
                canvas.yview_moveto(0)
        except tk.TclError:
            pass
    sf.bind("<Configure>", lambda _e: sf.after_idle(check), add="+")
    sf._parent_canvas.bind("<Configure>", lambda _e: sf.after_idle(check), add="+")
    sf.after_idle(check)
    return sf


def themed_menu(master) -> tk.Menu:
    """Right-click menu in theme colors. Build it fresh each time it opens."""
    return tk.Menu(master, tearoff=0, bg=cur("surface"), fg=cur("text"),
                   activebackground=cur("hover"), activeforeground=cur("text"),
                   borderwidth=1, relief="flat", font=(ui_family(), 10))


def popup(menu: tk.Menu, event):
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


# =============================================================================
# COMPOSITE COMPONENTS
# =============================================================================
class Toolbar(Panel):
    """Horizontal bar of icon buttons in groups, a stretchy middle for a status note,
    and a right side. Usage:
        bar = Toolbar(parent)
        bar.add(icon_button(bar, "panel-left", ...)); bar.add(icon_button(bar, "square-pen"))
        bar.divider()
        bar.stretch()                       # status note lives here
        bar.add(quiet_select(bar, [...]))
        bar.divider(); bar.add(icon_button(bar, "settings")); bar.add(theme_btn, last=True)
    """

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._col = 0
        self.status = ctk.CTkLabel(self, text="", anchor="e", font=font(), text_color=C["muted"])
        self._note_job = None

    def add(self, widget, last: bool = False):
        first = self._col == 0
        widget.grid(row=0, column=self._col, pady=6,
                    padx=(6 if first else 0, 6 if last else 2))
        self._col += 1
        return widget

    def divider(self):
        divider(self).grid(row=0, column=self._col, padx=6)
        self._col += 1

    def stretch(self):
        self.grid_columnconfigure(self._col, weight=1)
        self.status.grid(row=0, column=self._col, sticky="e", padx=8)
        self._col += 1

    def note(self, text: str, tone: str = "muted", ms: int = 3000):
        """Brief message in the bar's middle (e.g. 'Saved', 'Text size 15'). ms=0 keeps it."""
        if self._note_job:
            self.after_cancel(self._note_job)
            self._note_job = None
        self.status.configure(text=text, text_color=C[tone])
        if ms:
            self._note_job = self.after(ms, lambda: self.status.configure(text=""))


class ItemList(Panel):
    """Sidebar list: search box on top, rows with a title button and a trash icon.
    Trash needs two clicks (first click arms it red), like LULIM's chat list.
    Right-click a row for a menu built by menu_items(item) -> [(label, fn), ...].

    items:      list of objects; title(item) gives the row text
    on_open:    called with the item when its row is clicked
    on_delete:  called with the item after the second trash click
    matches:    matches(item, words) for search (default: all words in the title)
    """

    def __init__(self, master, title: Callable, on_open: Callable, on_delete: Callable,
                 menu_items: Callable | None = None, matches: Callable | None = None,
                 placeholder: str = "Search", empty_text: str = "Nothing here yet"):
        super().__init__(master)
        self.title, self.on_open, self.on_delete = title, on_open, on_delete
        self.menu_items, self.empty_text = menu_items, empty_text
        self.matches = matches or (lambda it, words: all(w in title(it).lower() for w in words))
        self.items: list = []
        self.selected = None
        self._armed = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.search = search_entry(self, placeholder)
        self.search.grid(row=0, column=0, sticky="ew", padx=GUTTER, pady=(GUTTER, 0))
        self._job = None
        self.search.bind("<KeyRelease>", self._debounce)
        self.search.bind("<Escape>", lambda _e: (self.search.delete(0, "end"), self.refresh()))
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=C["scrollbar"],
                                           scrollbar_button_hover_color=C["scrollbar_hover"])
        self.list.grid(row=1, column=0, sticky="nsew", padx=5, pady=(4, GUTTER))
        self.list.grid_columnconfigure(0, weight=1)
        autohide_scrollbar(self.list)

    def set_items(self, items: list):
        self.items = items
        self.refresh()

    def _debounce(self, _e=None):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(150, self.refresh)

    def refresh(self):
        self._job = None
        self._armed = None
        for w in self.list.winfo_children():
            w.destroy()
        words = self.search.get().lower().split()
        shown = [it for it in self.items if not words or self.matches(it, words)]
        if not shown:
            label(self.list, "No matches" if words else self.empty_text, muted=True).grid(
                row=0, column=0, sticky="w", padx=GUTTER, pady=4)
        for i, it in enumerate(shown):
            on = it is self.selected
            # No selected background: the open item only gets stronger text (hover still fills).
            b = ctk.CTkButton(self.list, text=self.title(it), anchor="w", font=font(),
                              fg_color="transparent", hover_color=C["hover"],
                              text_color=C["text_strong"] if on else C["text"],
                              corner_radius=RADIUS, command=lambda it=it: self._open(it))
            b.grid(row=i, column=0, sticky="ew", pady=1)
            trash = ctk.CTkButton(self.list, text="", image=icon("trash-2", "muted", LIST_ICON_SIZE),
                                  width=28, fg_color="transparent", hover_color=C["hover"],
                                  corner_radius=RADIUS)
            trash.configure(command=lambda it=it, t=trash: self._trash(it, t))
            trash.grid(row=i, column=1, pady=1)
            Tooltip(trash, lambda t=trash: "Click again to delete" if self._armed and self._armed[1] is t
                    else "Delete (click twice)")
            if self.menu_items:
                b.bind("<Button-3>", lambda e, it=it: self._menu(e, it))

    def _open(self, it):
        self.selected = it
        self.on_open(it)
        self.refresh()

    def _trash(self, it, btn):
        if self._armed and self._armed[0] is it:
            self._armed = None
            self.on_delete(it)
            return
        if self._armed:                     # disarm the previous one
            try:
                self._armed[1].configure(image=icon("trash-2", "muted", LIST_ICON_SIZE))
            except tk.TclError:
                pass
        self._armed = (it, btn)
        btn.configure(image=icon("trash-2", "error", LIST_ICON_SIZE))
        btn.after(3000, lambda: self._disarm(it, btn))

    def _disarm(self, it, btn):
        if self._armed and self._armed[0] is it:
            self._armed = None
            try:
                btn.configure(image=icon("trash-2", "muted", LIST_ICON_SIZE))
            except tk.TclError:
                pass

    def _menu(self, event, it):
        m = themed_menu(self)
        for text, fn in self.menu_items(it):
            m.add_command(label=text, command=fn)
        popup(m, event)


class Form(ctk.CTkFrame):
    """Settings that read at a glance. ONE row pattern: [label | control], label on the LEFT in a fixed
    column (muted), control on the right, an optional (i) hover tip right after the label. Controls are
    grouped under bold headings. A control that doesn't apply is hidden by key (never greyed out).

        f = Form(panel)
        f.heading("Box")
        f.row("Shape", quiet_select(f, ["None", "Square"], ...), key="shape")
        f.row("Padding", pad_slider_frame, tip="Space between the icon and the box edge.", key="padding")
        f.show("padding", False)
    Create the controls with `f` as their master.
    """

    LABEL_W = 78

    def __init__(self, master, label_width: int | None = None, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self.label_w = label_width or self.LABEL_W
        self._r = 0
        self._rows: dict[str, list] = {}
        self.grid_columnconfigure(1, weight=1)

    def heading(self, text: str, tip: str | None = None):
        cell = ctk.CTkFrame(self, fg_color="transparent")
        label(cell, text, bold=True).pack(side="left")
        if tip:
            info(cell, tip).pack(side="left", padx=(6, 0))
        cell.grid(row=self._r, column=0, columnspan=2, sticky="w", padx=INSET, pady=(16 if self._r else 8, 4))
        self._r += 1

    def row(self, text: str, widget, tip: str = "", key: str | None = None):
        cell = ctk.CTkFrame(self, fg_color="transparent", width=self.label_w, height=28)
        cell.pack_propagate(False)
        label(cell, text, muted=True).pack(side="left")
        if tip:
            info(cell, tip).pack(side="left", padx=(3, 0))
        cell.grid(row=self._r, column=0, sticky="w", padx=(INSET, 4), pady=3)
        # every control's VISIBLE left edge sits on one line: a slider's track starts `inset` px inside it
        widget.grid(row=self._r, column=1, sticky="w", padx=(SLIDER_INSET - getattr(widget, "inset", 0), INSET), pady=3)
        if key:
            self._rows[key] = [cell, widget]
        self._r += 1

    def show(self, key: str, on: bool):
        for w in self._rows[key]:
            w.grid() if on else w.grid_remove()


class FormWindow(ctk.CTkToplevel):
    """Settings-style dialog: stacked panels ('sections'), each a Form of label | control rows,
    Cancel/Save at the bottom right. Explanations go in hover (i) tips, never as text under a control.
    Ported from LULIM's settings window.

        win = FormWindow(app, "Settings", on_save=lambda values: ...)
        win.section("Display")
        win.field("Text size", win.slider("font_size", 9, 24, 15, 13, lambda v: f"{v:.0f}"),
                  tip="Ctrl + and Ctrl − change it too.")
        win.finish()
    """

    def __init__(self, master, title: str, on_save: Callable[[dict], None], label_width: int = 110):
        super().__init__(master, fg_color=C["window"])
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self._on_save = on_save
        self._get: dict[str, Callable] = {}
        self._sec: Form | None = None
        self._sections = 0
        self._label_width = label_width
        self.bind("<Escape>", lambda _e: self.destroy())

    def section(self, title: str):
        panel = Panel(self)
        panel.grid(row=self._sections, column=0, sticky="ew", padx=GUTTER, pady=(GUTTER, 0))
        self._sections += 1
        label(panel, title, bold=True).pack(anchor="w", padx=INSET, pady=(8, 2))
        self._sec = Form(panel, label_width=self._label_width)
        self._sec.pack(fill="x", pady=(0, 6))
        return self._sec

    def field(self, text: str, widget, tip: str = ""):
        self._sec.row(text, widget, tip)

    # value builders: each registers how to read its value back on Save
    def menu(self, key: str, choices: list[tuple[str, object]], current):
        labels = [c[0] for c in choices]
        m = quiet_select(self._sec, labels, width=220)
        m.set(next((lbl for lbl, v in choices if v == current), labels[0]))
        self._get[key] = lambda: dict(choices)[m.get()]
        return m

    def slider(self, key: str, lo, hi, steps, current, fmt=lambda v: f"{v:.1f}"):
        box, s = slider(self._sec, lo, hi, steps, current, fmt)
        self._get[key] = lambda: round(s.get(), 2)
        return box

    def check(self, key: str, text: str, current: bool):
        c = checkbox(self._sec, text, current)
        self._get[key] = lambda: bool(c.get())
        return c

    def text(self, key: str, current: str, placeholder: str = "", width: int = 220):
        e = entry(self._sec, placeholder, width=width)
        if current:
            e.insert(0, current)
        self._get[key] = lambda: e.get().strip()
        return e

    def finish(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=self._sections, column=0, sticky="e", padx=GUTTER, pady=GUTTER)
        button(row, "Cancel", self.destroy).grid(row=0, column=0, padx=(0, 6))
        button(row, "Save", self._save).grid(row=0, column=1)
        self.after(150, self.focus)   # CTkToplevel finishes setting up after a moment

    def _save(self):
        self._on_save({k: fn() for k, fn in self._get.items()})
        self.destroy()


def toggle_window(owner, key: str, build: Callable[[], ctk.CTkToplevel]):
    """A toolbar button that opens a window toggles it: the first click opens it, the next
    click closes it. A button never stacks up copies.
        icon_button(bar, "settings", lambda: ui.toggle_window(self, "settings", self.build_settings))
    `build` creates and returns the window."""
    windows = owner.__dict__.setdefault("_ui_windows", {})
    win = windows.get(key)
    if win is not None and win.winfo_exists():
        win.destroy()
        windows.pop(key, None)
        return None
    win = windows[key] = build()
    return win


def ask(master, title: str, message: str, ok: str = "OK", danger: bool = False) -> bool:
    """Small modal yes/no in the same style. Returns True on OK."""
    result = {"ok": False}
    win = ctk.CTkToplevel(master, fg_color=C["window"])
    win.title(title)
    win.resizable(False, False)
    win.transient(master)
    p = Panel(win)
    p.pack(fill="both", expand=True, padx=GUTTER, pady=(GUTTER, 0))
    label(p, title, bold=True).pack(anchor="w", padx=14, pady=(10, 2))
    label(p, message, muted=True, wraplength=320).pack(anchor="w", padx=14, pady=(0, 12))
    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(anchor="e", padx=GUTTER, pady=GUTTER)

    def done(v):
        result["ok"] = v
        win.destroy()

    button(row, "Cancel", lambda: done(False)).pack(side="left", padx=(0, 6))
    okb = button(row, ok, lambda: done(True))
    if danger:
        okb.configure(text_color=C["error"])
    okb.pack(side="left")
    win.bind("<Escape>", lambda _e: done(False))
    win.bind("<Return>", lambda _e: done(True))
    win.after(150, lambda: (win.focus(), win.grab_set()))
    master.wait_window(win)
    return result["ok"]
