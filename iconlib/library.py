"""The master library: a folder of SVG files plus index.json (see SPEC.md section 2).

    root/
      icons/<id>.svg      the artwork (flat folder; the filename is the permanent ID)
      index.json          metadata per icon: tags, notes, depth, aliases (rebuildable)
      collections/*.json  named lists of icon IDs (read here only to warn before removal)
      .trash/             removed icons are moved here, never deleted outright

No UI code. Every write to index.json is atomic (temp file + rename).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .clean import CleanError, clean_svg

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TAG_RE = ID_RE
DEPTH_MODES = ("auto", "off")


class LibraryError(ValueError):
    pass


@dataclass
class Record:
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    depth: str = "auto"
    aliases: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"tags": sorted(self.tags), "notes": self.notes, "depth": self.depth,
                "aliases": sorted(self.aliases)}

    @classmethod
    def from_json(cls, d: dict) -> "Record":
        depth = d.get("depth", "auto")
        return cls(tags=[t for t in d.get("tags", []) if TAG_RE.match(str(t))], notes=str(d.get("notes", "")),
                   depth=depth if depth in DEPTH_MODES else "auto",
                   aliases=[a for a in d.get("aliases", []) if ID_RE.match(str(a))])


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def normalize_tag(tag: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
    if not t:
        raise LibraryError(f"empty tag from {tag!r}")
    return t


class Library:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.icons_dir = self.root / "icons"
        self.index_path = self.root / "index.json"
        self.records: dict[str, Record] = {}
        self.index_was_rebuilt = False
        self.load()

    # ------------------------------------------------------------- loading / index
    def load(self):
        """Read index.json, then reconcile with the files on disk. A missing or corrupt index is
        rebuilt (a corrupt one is kept as index.json.bad)."""
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.records, self.index_was_rebuilt = {}, False
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.records = {k: Record.from_json(v) for k, v in data["icons"].items()}
        except FileNotFoundError:
            self.index_was_rebuilt = True
        except (ValueError, KeyError, AttributeError, TypeError):
            self.index_was_rebuilt = True
            shutil.copy2(self.index_path, self.index_path.with_name("index.json.bad"))
        changed = False
        for name in self._files():
            if name not in self.records:
                self.records[name] = Record()
                changed = True
        if changed or self.index_was_rebuilt:
            self.save()

    def save(self):
        data = {"version": 1, "icons": {k: self.records[k].to_json() for k in sorted(self.records)}}
        _atomic_write(self.index_path, json.dumps(data, indent=2) + "\n")

    def _files(self) -> list[str]:
        return sorted(p.stem for p in self.icons_dir.glob("*.svg") if ID_RE.match(p.stem))

    def path(self, icon_id: str) -> Path:
        return self.icons_dir / f"{icon_id}.svg"

    def ids(self) -> list[str]:
        """IDs that have an SVG file (the library's real content)."""
        return [i for i in sorted(self.records) if self.path(i).exists()]

    def orphans(self) -> list[str]:
        """Index entries whose file is gone."""
        return [i for i in sorted(self.records) if not self.path(i).exists()]

    def prune(self) -> list[str]:
        gone = self.orphans()
        for i in gone:
            del self.records[i]
        if gone:
            self.save()
        return gone

    def __contains__(self, icon_id: str) -> bool:
        return icon_id in self.records and self.path(icon_id).exists()

    def get(self, icon_id: str) -> Record:
        return self.records[self.resolve(icon_id)]

    def read_svg(self, icon_id: str) -> str:
        return self.path(self.resolve(icon_id)).read_text(encoding="utf-8")

    # ------------------------------------------------------------------ names
    def resolve(self, name: str) -> str:
        """Current ID for an ID or an old alias. Raises LibraryError if unknown."""
        if name in self:
            return name
        for icon_id, rec in self.records.items():
            if name in rec.aliases and icon_id in self:
                return icon_id
        raise LibraryError(f"no icon named {name!r}")

    def _check_new_id(self, new_id: str, ignore: str | None = None):
        if not ID_RE.match(new_id):
            raise LibraryError(f"{new_id!r} is not a valid ID (lowercase words joined by hyphens, e.g. arrow-left)")
        if new_id != ignore and (self.path(new_id).exists() or new_id in self.records):
            raise LibraryError(f"{new_id!r} already exists")
        for icon_id, rec in self.records.items():
            if icon_id != ignore and new_id in rec.aliases:
                raise LibraryError(f"{new_id!r} is an old name of {icon_id!r}")

    # -------------------------------------------------------- add / replace / remove
    def _clean(self, svg_text: str) -> tuple[str, list[str]]:
        res = clean_svg(svg_text)
        if res.errors:
            raise CleanError(res.errors)
        return res.svg, res.warnings

    def add(self, icon_id: str, svg_text: str, tags=(), notes: str = "", depth: str = "auto") -> list[str]:
        """Clean and add a new icon. Returns import warnings. Raises on bad ID, duplicate, bad SVG."""
        self._check_new_id(icon_id)
        if depth not in DEPTH_MODES:
            raise LibraryError(f"depth must be one of {DEPTH_MODES}")
        svg, warnings = self._clean(svg_text)
        _atomic_write(self.path(icon_id), svg)
        self.records[icon_id] = Record(tags=sorted({normalize_tag(t) for t in tags}), notes=notes, depth=depth)
        self.save()
        return warnings

    def replace(self, icon_id: str, svg_text: str) -> list[str]:
        """New artwork, same ID/tags/notes/depth/aliases. The old file is kept in .trash/."""
        icon_id = self.resolve(icon_id)
        svg, warnings = self._clean(svg_text)           # validate before touching anything
        self._to_trash(icon_id, keep_file=True)
        _atomic_write(self.path(icon_id), svg)
        return warnings

    def remove(self, icon_id: str) -> Path:
        """Move the icon to .trash/ (reversible by hand). Returns the trashed file."""
        icon_id = self.resolve(icon_id)
        trashed = self._to_trash(icon_id, keep_file=False)
        del self.records[icon_id]
        self.save()
        return trashed

    def _to_trash(self, icon_id: str, keep_file: bool) -> Path:
        trash = self.root / ".trash"
        trash.mkdir(exist_ok=True)
        dest = trash / f"{icon_id}.{time.strftime('%Y%m%d-%H%M%S')}.{time.monotonic_ns() % 10**6:06d}.svg"
        (shutil.copy2 if keep_file else shutil.move)(self.path(icon_id), dest)
        return dest

    def rename(self, old: str, new: str):
        """Rename the file and keep the old name as an alias, so old collections still resolve."""
        old = self.resolve(old)
        self._check_new_id(new, ignore=old)
        if new == old:
            return
        rec = self.records.pop(old)
        self.path(old).rename(self.path(new))
        rec.aliases = sorted((set(rec.aliases) | {old}) - {new})
        self.records[new] = rec
        self.save()

    # ----------------------------------------------------------- tags / notes / depth
    def set_tags(self, icon_id: str, tags):
        self.get(icon_id).tags = sorted({normalize_tag(t) for t in tags})
        self.save()

    def set_notes(self, icon_id: str, notes: str):
        self.get(icon_id).notes = notes
        self.save()

    def set_depth(self, icon_id: str, mode: str):
        if mode not in DEPTH_MODES:
            raise LibraryError(f"depth must be one of {DEPTH_MODES}")
        self.get(icon_id).depth = mode
        self.save()

    def all_tags(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.ids():
            for t in self.records[i].tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items()))

    # ------------------------------------------------------------------- search
    def search(self, query: str = "", tags=()) -> list[str]:
        """Every word in `query` must appear in the ID, a tag, an alias or the notes; every tag in
        `tags` must be present. Empty arguments return everything."""
        words = query.lower().split()
        want = {normalize_tag(t) for t in tags}
        out = []
        for i in self.ids():
            r = self.records[i]
            hay = " ".join([i.replace("-", " "), i, *r.tags, *r.aliases, r.notes]).lower()
            if want <= set(r.tags) and all(w in hay for w in words):
                out.append(i)
        return out

    # -------------------------------------------------------------- collections
    def collections_using(self, icon_id: str) -> list[str]:
        """Names of collections that list this icon (by ID or alias), so the UI can warn before removal."""
        icon_id = self.resolve(icon_id)
        names = {icon_id, *self.records[icon_id].aliases}
        found = []
        for f in sorted((self.root / "collections").glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if names & set(data.get("icons", [])):
                found.append(data.get("name", f.stem))
        return found
