# Changelog

## 0.1.2
Fixed blank exports. Themed SVGs carried their colors only as CSS variables, which browsers understand but Inkscape,
librsvg (GNOME's image viewer) and most other viewers don't, so the icon vanished and the box turned black. Themed
files now also hold plain colors; browsers still use the variables, other viewers show the default theme. Re-export
to get the fixed files.

## 0.1.1
Import now works with real Inkscape files: layer, group and object transforms are applied to the shapes instead of
being refused, a page smaller than 24 x 24 is centered on the canvas (a larger one is scaled to fit), and the
needless "stroke-opacity" warning for fully opaque lines is gone.

## 0.1.0
First release. Master icon library (a folder of SVGs plus a small index), import from Inkscape SVGs with cleanup,
tags and search, collections (saved subsets that remember their style), three-tone themes with optional automatic
depth, box / padding / thickness styling, and export to SVG files, an SVG sprite, PNG and a theme CSS file.
`icon-library --install-menu` adds an applications-menu entry.
