# Icon Library App: Spec v0.1

## 1. Purpose
One master library of icons the user drew. For any project, pick a subset, choose a style, export it.
Exporting never changes the master.

## 2. Master library (plain folders, no database)
```
library/
  icons/          sword-crossed.svg, arrow-left.svg ...   (flat, no subfolders)
  collections/    project-x.json, ui-core.json ...
  index.json      per-icon metadata (rebuildable from the SVGs)
```
- Filename = permanent ID: lowercase words joined by hyphens, general to specific (`arrow-left`).
  A rename keeps the old name as an alias so collections don't break.
- Index fields per icon: `tags`, optional `notes`, `depth: auto|off`, optional nudge (deferred).
- Tags replace categories. Find icons by search or by scrolling the grid.
- Add / replace / remove are single actions. Replace keeps ID, tags, notes. Remove = two clicks.
- Library folder location is a setting. No OS-specific paths (Fedora + Windows).

## 3. Icon files
- SVG on a 24x24 canvas, 2-unit safe margin. Inkscape template supplied.
- Allowed: path, line, polyline, polygon, circle, ellipse, rect; strokes or fills. Transparent background.
- Role colors: main `#000000`, shade `#FF0000`, light `#0000FF` (placeholders, never shown in output).
  Black-only = plain single-color icon. Any other color: import warns.
- Import cleans Inkscape extras (editor settings, layers, metadata).

## 4. Collections
Named list of icon IDs (no copies). May remember the last export style. An icon can be in many collections.

## 5. Export
Style (same for every icon in the export, never stored in the master): size, stroke thickness,
background box (none/square/rounded/circle, radius, padding, fill), depth (off/on + strength), theme palette(s).

Formats v1: web themed (default; SVGs and/or sprite + generated CSS, one block per theme, baked
fallbacks), web baked, PNG baked. v2: WPF / Avalonia XAML.

## 6. Theming
Theme = three role colors + box color. Preview and export share one engine.

## 7. Depth (optional, three tones)
Explicit roles used as drawn. Otherwise automatic: shifted shade + light copies behind main shapes
(plain duplicated shapes, no filters). Precedence: explicit roles > icon `depth: off` > export setting.

## 8. App / UI
CustomTkinter + Dave-Standard (dave_theme.py copied unchanged). Sidebar (collections + search),
icon grid (search, tag filters, safe-area toggle), preview/properties panel, toolbar
(Import, Replace, Remove, Export). Unique `APP_NAME`.

## 9. Deferred / dropped
Deferred: per-icon optical nudge + suggest, WPF/Avalonia export, color mapping, creator/license tracking.
Dropped: bitmap import.

## 10. Technical choices
- No new dependencies: customtkinter + Pillow (already used by the template); stdlib for SVG/JSON.
- Own small SVG-subset renderer on Pillow (prototype first). Fallback: cairosvg (needs system cairo).
- Dummy data: ~12 generated icons covering single-color, explicit roles, and too-detailed-for-depth.

## 11. Build order
1. Scaffold + dummy icons  2. Renderer prototype  3. Library + index  4. Grid UI
5. Preview (themes, boxes, depth)  6. Collections  7. Export + tests that the master is unchanged

## 12. Decisions made while building (v0.1 -> steps 1-7)
- All icons are the user's own originals: no creator/license tracking, no bitmap import (section 9).
- Removed/replaced icons go to `library/.trash/`, never deleted outright. Renames keep an alias.
- Import rejects transforms and text (error); non-role colors and non-24x24 canvases only warn.
- Strokes render with round caps/joins only. Depth default 0.30 units, slider 0-0.6; it is
  subtle at 48px+ and fades below ~32px (sub-pixel offset). It is a medium/large-icon feature.
- Themes = main, shade, light, box fill, preview page. Built-ins in code (read-only), user themes in
  `library/themes.json`. "App colors" is a special entry that follows the app's light/dark mode.
- Style (box, padding, radius, depth, stroke) and theme are chosen per export; the grid and preview
  use the same engine (`iconlib/style.py: compose`) the exports will use.
- Collections (step 6): one JSON file per collection listing IDs (aliases resolve); optional saved style +
  theme, which is loaded when the collection opens and updated by style edits while it is open. Deleted
  collections go to `.trash`. Missing members show a banner instead of vanishing.
- Export (step 7, `iconlib/export.py`): svg/ files, `icons-sprite.svg`, PNGs, `icons-theme.css`, `manifest.json`,
  `README.txt`. Themed mode writes `style="...var(--icon-main,#fallback)"` (variables --icon-main/shade/light/box,
  one `[data-theme="<name>"]` block per theme, first theme also `:root`); baked mode writes plain hex attributes.
  Box = `<rect>`, padding = translated group, depth = shifted copies (same maths as the preview).
  `<img>` cannot see page CSS variables, so it shows the default theme (documented in the README).
- Export safety: refuses folders inside the library and foreign non-empty folders; a re-export removes only the
  files its own manifest lists. Verified against Inkscape (pixel diff < ~1/255 mean) and Firefox (themes switch).
- UI feedback after first real use: no keyword/tag chips (tags stay searchable), no Notes field in the UI (the data
  field remains in index.json), explanations live in hover (i) icons, inapplicable style controls are hidden, and the
  grid always names its view ("All icons" / the collection) with a "Show all icons" link; the app starts on All icons.
  Collections are kept, pending a trial of the flow.
- Not built: drag-and-drop import, per-icon optical nudge, font zoom shortcuts (Ctrl +/-), a Settings window,
  WPF/Avalonia XAML export (v2).
