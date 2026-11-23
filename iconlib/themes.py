"""Theme storage: built-in themes (read-only, in code) + user themes in <library>/themes.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .style import BUILTIN_THEMES, Theme


class ThemeError(ValueError):
    pass


class ThemeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.user: dict[str, Theme] = {}
        self.load()

    def load(self):
        self.user = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))["themes"]
        except (OSError, ValueError, KeyError, TypeError):
            return
        for name, d in data.items():
            try:
                t = Theme(name=name, **{k: d.get(k) for k in ("main", "shade", "light", "box", "bg")})
                t.validate()
                self.user[name] = t
            except (ValueError, TypeError, AttributeError):
                continue                       # skip a damaged entry, keep the rest

    @property
    def builtin_names(self) -> list[str]:
        return [t.name for t in BUILTIN_THEMES]

    def all(self) -> dict[str, Theme]:
        return {**{t.name: t for t in BUILTIN_THEMES}, **self.user}

    def names(self) -> list[str]:
        return [*self.builtin_names, *sorted(self.user)]

    def get(self, name: str, fallback: str | None = None) -> Theme:
        themes = self.all()
        if name in themes:
            return themes[name]
        return themes[fallback or BUILTIN_THEMES[0].name]

    def save_theme(self, theme: Theme):
        theme.validate()
        if theme.name in self.builtin_names:
            raise ThemeError(f"{theme.name!r} is a built-in theme; pick another name")
        self.user[theme.name] = theme
        self._write()

    def delete(self, name: str):
        if name in self.builtin_names:
            raise ThemeError("built-in themes can't be deleted")
        if self.user.pop(name, None) is not None:
            self._write()

    def _write(self):
        data = {"version": 1, "themes": {n: {k: v for k, v in vars(t).items() if k != "name" and v is not None}
                                         for n, t in sorted(self.user.items())}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
