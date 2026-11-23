# Icon Library

One master library of your own SVG icons. For any project, pick a subset, choose a theme and style, and export
SVGs, a sprite, PNGs and a theme CSS file. The master library is never changed by an export. Styled with
**Dave-Standard** (`dave_theme.py` and `icons/` are copies from there).

```
python3 app.py                      # from a checkout
python3 app.py --library ~/icons    # use another library folder for this run
python3 app.py --theme light        # or dark (default; remembered; sun/moon button in the toolbar)
```

## Install with pipx (from the repo)
```
sudo dnf install pipx python3-tkinter          # once; Tk is not on PyPI
pipx install git+https://github.com/KillGorack/PyCon_maker      # or: pipx install /path/to/PyCon_Maker
icon-library                                    # upgrade: pipx upgrade icon-library   remove: pipx uninstall icon-library
icon-library --install-menu                     # optional: adds it to the applications menu (--remove-menu undoes it)
icon-library --selftest                         # checks the install is complete
```
pipx keeps the app in its own private environment, so nothing else on the system is touched. Your icons and
settings are never removed by an uninstall. Run `icon-library --remove-menu` before `pipx uninstall`.

## Where things live
- **Library:** an installed copy uses `~/.local/share/IconLibrary/library`. A source checkout with a `library/`
  folder next to `app.py` uses that instead. `--library DIR` overrides both for one run.
- **Settings:** `~/.local/share/IconLibrary/settings.json` (window size, theme, last style, ...).
- The library is plain folders, easy to back up or keep in git:
  ```
  library/
    icons/          one SVG per icon; the filename is its permanent ID (arrow-left.svg)
    collections/    named lists of icon IDs, with the style last used with them
    index.json      tags and flags per icon (rebuilt from the files if it is lost)
    themes.json     your own themes
    .trash/         removed icons and collections are moved here, never deleted outright
  ```

## Drawing icons
Draw on a 24 x 24 canvas (2-unit margin) in Inkscape or any editor and save as plain SVG. Use only paths, lines,
circles, ellipses, rects and polygons. Ungroup and apply transforms before importing: the importer cleans editor
data but refuses transforms and text. The line thickness you drew with is ignored; the thickness is set in the app
so the whole set stays consistent.

Colors are roles, not real colors:

| Color in the SVG | Role |
|---|---|
| `#000000` | main (the theme's main color) |
| `#ff0000` | shade (darker accent) |
| `#0000ff` | light (highlight accent) |

An all-black icon is a plain single-color icon. Draw with the other two roles when you want hand-made depth; any
other color is kept exactly as drawn. Plain icons can get an automatic shade and highlight instead (Style tab, Depth).

## Using it
- **Import** an SVG with the + button (Ctrl+O): the dialog shows the cleaned result and any warnings first.
- **Search** (Ctrl+F) matches names and tags. Select an icon to see it at several sizes, edit its tags, rename or replace it.
- **Style tab:** theme (colors), box (none, square, rounded, circle) with padding and corners, depth, line thickness.
  The whole grid previews the style live.
- **Collections:** Ctrl+N makes one. Ctrl+click selects several icons; right-click adds them. A collection remembers
  the style you used with it.
- **Export** (Ctrl+E): the open collection, the selection, or everything. SVG files, a sprite, PNGs, and
  `icons-theme.css` with one `[data-theme="..."]` block per theme (themed mode), or fixed colors (baked mode). Re-exporting
  to the same folder replaces only the files its own `manifest.json` lists.
- Shortcuts: Ctrl+O import, Ctrl+N new collection, Ctrl+E export, Ctrl+F search, Ctrl+G safe-area guides, Ctrl+A select all
  shown, Ctrl+B collections sidebar.

## Development
```
python3 -m unittest discover -s tests -t .    # tests build their own sample library; they never touch yours
python3 tools/make_dummy_icons.py             # sample icons for an empty checkout (refuses to overwrite a real library)
python3 tools/snapshot.py out.png dark star   # screenshot of the app on a throwaway copy
```
`SPEC.md` is the design document. `iconlib/` is the UI-free core (parsing, rendering, library, style, export);
the other `.py` files are the interface.

## Files
`app.py` shell, shortcuts and command line · `gallery.py` grid, detail panel, import dialog · `stylepanel.py` Style tab and
theme editor · `sidebar.py` collections · `exportdialog.py` export · `dialogs.py` small prompts · `iconlib/` core ·
`dave_theme.py` + `icons/` the look (from Dave-Standard; `icons/LICENSE` covers the Lucide icons among them).
