"""Collections: named lists of icon IDs for a project or purpose (SPEC.md section 4).

A collection never copies artwork, it only lists IDs (old names/aliases still resolve). It may also
remember the style + theme last used with it. One file per collection in <library>/collections/.
Deleted collections are moved to <library>/.trash/, like removed icons.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .library import Library, LibraryError, _atomic_write
from .style import Style

MAX_NAME = 60


class CollectionError(ValueError):
    pass


@dataclass
class Collection:
    name: str
    icons: list[str] = field(default_factory=list)
    style: dict | None = None            # Style.to_json() of the last style used with this collection
    theme: str | None = None             # theme name used with it
    slug: str = ""                       # file stem


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "collection"


class CollectionStore:
    def __init__(self, lib: Library):
        self.lib = lib
        self.dir = lib.root / "collections"
        self.items: list[Collection] = []
        self.load()

    # ------------------------------------------------------------------ io
    def load(self):
        self.items = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                name = str(d["name"]).strip()
                icons = [str(i) for i in d.get("icons", [])]
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue                                     # damaged file: skipped, never overwritten
            if not name:
                continue
            style = d.get("style") if isinstance(d.get("style"), dict) else None
            theme = d.get("theme") if isinstance(d.get("theme"), str) else None
            self.items.append(Collection(name, icons, style, theme, f.stem))
        self.items.sort(key=lambda c: c.name.lower())

    def _save(self, c: Collection):
        data = {"name": c.name, "icons": c.icons, "style": c.style, "theme": c.theme}
        _atomic_write(self.dir / f"{c.slug}.json", json.dumps(data, indent=2) + "\n")

    # --------------------------------------------------------------- queries
    def all(self) -> list[Collection]:
        return list(self.items)

    def names(self) -> list[str]:
        return [c.name for c in self.items]

    def get(self, name: str) -> Collection:
        for c in self.items:
            if c.name.lower() == name.strip().lower():
                return c
        raise CollectionError(f"no collection named {name!r}")

    def members(self, c: Collection) -> tuple[list[str], list[str]]:
        """(icon IDs that exist now, sorted and de-duplicated; entries that no longer exist).
        Old names resolve through the library's aliases."""
        present, missing = set(), []
        for entry in c.icons:
            try:
                present.add(self.lib.resolve(entry))
            except LibraryError:
                if entry not in missing:
                    missing.append(entry)
        return sorted(present), missing

    def containing(self, icon_id: str) -> list[str]:
        """Names of collections that include this icon (by ID or any alias)."""
        icon_id = self.lib.resolve(icon_id)
        names = {icon_id, *self.lib.records[icon_id].aliases}
        return [c.name for c in self.items if names & set(c.icons)]

    # ------------------------------------------------------------- mutations
    def _check_name(self, name: str, ignore: Collection | None = None) -> str:
        name = " ".join(name.split())
        if not name:
            raise CollectionError("a collection needs a name")
        if len(name) > MAX_NAME:
            raise CollectionError(f"keep names under {MAX_NAME} characters")
        for c in self.items:
            if c is not ignore and c.name.lower() == name.lower():
                raise CollectionError(f"there is already a collection named {c.name!r}")
        return name

    def _free_slug(self, name: str, ignore: Collection | None = None) -> str:
        base, n = slugify(name), 1
        taken = {c.slug for c in self.items if c is not ignore}
        slug = base
        while slug in taken or ((self.dir / f"{slug}.json").exists() and (ignore is None or slug != ignore.slug)):
            n += 1
            slug = f"{base}-{n}"
        return slug

    def create(self, name: str, icons=()) -> Collection:
        name = self._check_name(name)
        c = Collection(name, [], None, None, self._free_slug(name))
        c.icons = self._canon(icons)
        self.items.append(c)
        self.items.sort(key=lambda x: x.name.lower())
        self._save(c)
        return c

    def rename(self, name: str, new: str):
        c = self.get(name)
        new = self._check_name(new, ignore=c)
        old_path = self.dir / f"{c.slug}.json"
        c.name = new
        slug = self._free_slug(new, ignore=c)
        self._save(Collection(new, c.icons, c.style, c.theme, slug))
        if slug != c.slug:
            old_path.unlink(missing_ok=True)
            c.slug = slug
        self.items.sort(key=lambda x: x.name.lower())

    def delete(self, name: str) -> Path:
        c = self.get(name)
        trash = self.lib.root / ".trash"
        trash.mkdir(exist_ok=True)
        dest = trash / f"collection-{c.slug}.{time.strftime('%Y%m%d-%H%M%S')}.json"
        shutil.move(self.dir / f"{c.slug}.json", dest)
        self.items.remove(c)
        return dest

    def _canon(self, ids) -> list[str]:
        out = []
        for i in ids:
            i = self.lib.resolve(i)
            if i not in out:
                out.append(i)
        return sorted(out)

    def add(self, name: str, ids) -> int:
        """Add icons (IDs or aliases); returns how many were new."""
        c = self.get(name)
        current = set(self._canon_lenient(c.icons))
        new = [i for i in self._canon(ids) if i not in current]
        c.icons = sorted(current | set(new))
        self._save(c)
        return len(new)

    def remove(self, name: str, ids) -> int:
        """Remove icons from a collection (also matches their old names). Returns how many went."""
        c = self.get(name)
        drop = set()
        for i in ids:
            drop.add(i)
            try:
                canon = self.lib.resolve(i)
                drop |= {canon, *self.lib.records[canon].aliases}
            except LibraryError:
                pass                                          # already gone from the library: match by name
        kept = [i for i in c.icons if i not in drop]
        removed = len(c.icons) - len(kept)
        c.icons = kept
        self._save(c)
        return removed

    def _canon_lenient(self, ids) -> list[str]:
        """Canonical IDs where possible; entries that no longer resolve are kept as written."""
        out = []
        for i in ids:
            try:
                i = self.lib.resolve(i)
            except LibraryError:
                pass
            if i not in out:
                out.append(i)
        return out

    def drop_missing(self, name: str) -> list[str]:
        c = self.get(name)
        _, missing = self.members(c)
        if missing:
            c.icons = [i for i in c.icons if i not in missing]
            self._save(c)
        return missing

    def set_style(self, name: str, style: Style, theme: str | None):
        c = self.get(name)
        c.style, c.theme = style.to_json(), theme
        self._save(c)
