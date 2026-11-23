"""UI smoke test: drives the real app (CustomTkinter) against a throwaway library and settings.
Skipped when there is no display."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
INK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g style="stroke:#000000;stroke-width:2;fill:none">'
       '<path d="M3 17c3-8 6-8 9 0s6 8 9 0"/></g></svg>')


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class AppSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        os.environ["XDG_DATA_HOME"] = str(cls.tmp / "data")
        from tests.fixtures import library_dir
        shutil.copytree(library_dir(), cls.tmp / "library")
        sys.path.insert(0, str(ROOT))
        import app as appmod
        import dave_theme as ui
        appmod.DEFAULT_LIBRARY = cls.tmp / "library"
        ui.setup("dark")
        cls.app = appmod.App()
        cls.app.geometry("1100x700")
        cls.app.update()
        cls.appmod = appmod

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def pump(self):
        self.app.update_idletasks()
        self.app.update()

    def test_01_gallery_shows_every_icon_and_filters(self):
        a = self.app
        self.assertEqual(len(a.gallery.tiles), 13)
        a.gallery.search.insert(0, "arrow")
        a.gallery.apply_filter()
        self.assertEqual(a.gallery.visible_ids(), ["arrow-left", "arrow-right"])
        a.gallery.clear_search()
        a.gallery.search.insert(0, "combat")                       # tags are searchable (there are no tag chips)
        a.gallery.apply_filter()
        self.assertEqual(set(a.gallery.visible_ids()), {"shield", "shield-tone", "sword"})
        a.gallery.clear_search()
        self.assertEqual(len(a.gallery.visible_ids()), 13)
        self.assertFalse(hasattr(a.gallery, "chips"))

    def test_02_style_changes_reach_tiles_settings_and_survive_restart_values(self):
        a = self.app
        a.gallery.select("shield")
        before = a.gallery._stamps["shield"]
        p = a.style_panel
        p.box_menu.set("Rounded")
        p._enable()
        p.depth.set(0.3)
        p._emit()
        self.pump()
        self.assertEqual((a.thumbs.style.box, a.thumbs.style.depth), ("rounded", 0.3))
        self.assertEqual(a.settings["style"]["box"], "rounded")
        self.assertNotEqual(a.gallery._stamps["shield"], before)
        from iconlib.style import Style
        self.assertEqual(Style.from_json(a.settings["style"]), a.thumbs.style)
        p.reset()
        from stylepanel import app_default_style
        self.assertEqual(a.thumbs.style, app_default_style())
        self.assertEqual(a.thumbs.style.stroke, 2.0)                 # a thickness is always set in the UI

    def test_03_depth_flag_refreshes_the_tile(self):
        a = self.app
        a.gallery.select("shield")
        p = a.style_panel
        p.depth.set(0.4)
        p._emit()
        img_on = a.gallery.tiles["shield"].cget("image")
        self.assertTrue(a.style_panel.flag.winfo_ismapped() or a.detail.tab == "Icon")     # lives in the Style tab
        a.style_panel.flag.deselect()
        a.style_panel.on_flag(False)                                    # what ticking the box calls
        self.assertEqual(a.lib.get("shield").depth, "off")
        self.assertIsNot(a.gallery.tiles["shield"].cget("image"), img_on)
        a.style_panel.flag.select()
        a.style_panel.on_flag(True)
        self.assertEqual(a.lib.get("shield").depth, "auto")
        p.reset()

    def test_04_new_theme_is_saved_to_the_library_and_selected(self):
        a = self.app
        a.edit_theme(None)
        self.pump()
        ed = next(w for w in a.winfo_children() if w.winfo_class() == "Toplevel" and hasattr(w, "entries"))
        ed.name.delete(0, "end")
        ed.name.insert(0, "Smoke teal")
        ed.entries["main"].delete(0, "end")
        ed.entries["main"].insert(0, "#14b8a6")
        ed._derive()
        ed._save()
        self.pump()
        self.assertEqual(a.thumbs.theme_name, "Smoke teal")
        self.assertIn("Smoke teal", (a.library / "themes.json").read_text())
        self.assertEqual(a.settings["style_theme"], "Smoke teal")

    def test_05_import_edit_and_two_click_remove(self):
        from gallery import ImportDialog
        from iconlib.clean import clean_svg
        a = self.app

        def confirm(icon_id, tags):
            a.lib.add(icon_id, INK, tags=tags)
            a.reload()
            a.gallery.select(icon_id)

        dlg = ImportDialog(a, a.thumbs, clean_svg(INK), "add", "Wave Line.svg", confirm)
        self.pump()
        self.assertEqual(dlg.id_entry.get(), "wave-line")
        dlg.tag_entry.insert(0, "wave, water")
        dlg._confirm()
        self.pump()
        self.assertEqual(a.detail.icon_id, "wave-line")
        self.assertEqual(a.lib.get("wave-line").tags, ["water", "wave"])
        a.detail.tags.delete(0, "end")
        a.detail.tags.insert(0, "sea")
        a.detail._save_tags()
        self.assertEqual(a.lib.get("wave-line").tags, ["sea"])
        a.gallery.search.insert(0, "sea")
        a.gallery.apply_filter()
        self.assertEqual(a.gallery.visible_ids(), ["wave-line"])        # the new tag is searchable at once
        a.gallery.clear_search()
        a.detail._remove_click()
        self.assertIn("wave-line", a.lib.ids())                      # one click only arms it
        a.detail._remove_click()
        self.assertNotIn("wave-line", a.lib.ids())
        self.assertIsNone(a.detail.icon_id)
        self.assertEqual(len(list((a.library / ".trash").glob("wave-line.*.svg"))), 1)

    def test_06_duplicate_id_is_reported_in_the_dialog_not_raised(self):
        from gallery import ImportDialog
        from iconlib.clean import clean_svg
        a = self.app
        dlg = ImportDialog(a, a.thumbs, clean_svg(INK), "add", "star.svg", lambda i, t: a.lib.add(i, INK, tags=t))
        self.pump()
        dlg._confirm()
        self.assertIn("already exists", dlg.error.cget("text"))
        dlg.destroy()

    def test_07_import_errors_are_shown_and_cannot_be_confirmed(self):
        from gallery import ImportDialog
        from iconlib.clean import clean_svg
        a = self.app
        bad = '<svg xmlns="http://www.w3.org/2000/svg"><text x="1" y="5">Hi</text></svg>'
        dlg = ImportDialog(a, a.thumbs, clean_svg(bad), "add", "bad.svg", lambda i, t: None)
        self.pump()
        self.assertIsNone(dlg.id_entry)
        dlg.destroy()

    # ------------------------------------------------------------ collections
    def fake_prompt(self, text):
        """Stand-in for the modal prompt: runs the dialog's validation, like pressing OK."""
        def fake(master, title, label, initial="", ok="OK", on_ok=None):
            msg = on_ok(text) if on_ok else None
            self.last_prompt_error = msg
            return None if msg else text
        self.appmod.prompt = fake

    def test_08_opening_a_collection_scopes_the_grid_and_all_icons_restores_it(self):
        a = self.app
        c = a.collections.get("UI basics")
        a.sidebar._open(c)
        self.pump()
        self.assertEqual(set(a.gallery.visible_ids()), {"arrow-left", "arrow-right", "check", "home", "plus"})
        self.assertTrue(a.gallery.header.winfo_ismapped())                  # inside a collection the view is named...
        self.assertEqual(a.gallery.title.cget("text"), "UI basics")
        self.assertEqual(a.gallery.count.cget("text"), "5 icons")
        self.assertTrue(a.gallery.back.winfo_ismapped())                    # ...with a way back
        a.gallery._back()                                                   # what clicking the link calls
        self.pump()
        self.assertIsNone(a.current)
        self.assertEqual(len(a.gallery.visible_ids()), 13)
        self.assertFalse(a.gallery.header.winfo_ismapped())                 # ...and in All icons there is no header

    def test_09_style_is_saved_with_the_open_collection_not_the_app(self):
        from iconlib.style import Style
        a = self.app
        a.style_panel.reset()
        app_style = a.thumbs.style
        a.sidebar._open(a.collections.get("UI basics"))
        p = a.style_panel
        p.box_menu.set("Circle")
        p._enable()
        p._emit()
        saved = Style.from_json(a.collections.get("UI basics").style)
        self.assertEqual(saved.box, "circle")
        self.assertEqual(Style.from_json(a.settings.get("style", {})), app_style)      # app style untouched
        a.sidebar._open(None)
        self.assertEqual(a.thumbs.style, app_style)                                      # back to the app style
        a.sidebar._open(a.collections.get("UI basics"))
        self.assertEqual(a.thumbs.style.box, "circle")                                   # collection's style returns
        self.assertIn("UI basics", a.style_panel.where_text)
        a.sidebar._open(None)

    def test_10_ctrl_click_multi_select_and_add_to_collection(self):
        a = self.app
        a.gallery.select("star")
        a.gallery.toggle_select("heart")
        a.gallery.toggle_select("sword")
        self.assertEqual(a.gallery.selection, ["star", "heart", "sword"])
        self.assertEqual(a.gallery.selected, "sword")
        a.gallery.toggle_select("sword")
        self.assertEqual((a.gallery.selection, a.gallery.selected), (["star", "heart"], "heart"))
        self.fake_prompt("Favorites")
        a.new_collection(a.gallery.selection)
        self.assertEqual(a.current.name, "Favorites")
        self.assertEqual(set(a.gallery.visible_ids()), {"star", "heart"})
        a.sidebar._open(None)
        a.add_to_collection("Favorites", ["sword", "star"])
        self.assertEqual(a.collections.members(a.collections.get("Favorites"))[0], ["heart", "star", "sword"])

    def test_11_detail_checkboxes_toggle_membership(self):
        a = self.app
        a.gallery.select("check")
        boxes = {cb.cget("text"): cb for cb in a.detail.coll_frame.winfo_children() if hasattr(cb, "get")}
        self.assertTrue(boxes["UI basics"].get())
        self.assertFalse(boxes["Favorites"].get())
        boxes["Favorites"].toggle()                                   # the real checkbox command
        self.assertIn("check", a.collections.members(a.collections.get("Favorites"))[0])
        boxes["Favorites"].toggle()
        self.assertNotIn("check", a.collections.members(a.collections.get("Favorites"))[0])

    def test_12_missing_members_show_a_banner_and_can_be_dropped(self):
        a = self.app
        a.add_to_collection("Favorites", ["gem-tone"])
        a.sidebar._open(a.collections.get("Favorites"))
        a.gallery.select("gem-tone")
        a.remove_icon("gem-tone")
        self.pump()
        self.assertIn("no longer in the library", a.gallery.banner_text.cget("text"))
        self.assertIn("gem-tone", a.gallery.banner_text.cget("text"))
        a.drop_missing()
        self.pump()
        self.assertFalse(a.gallery.banner.winfo_ismapped())
        a.sidebar._open(None)

    def test_13_import_while_a_collection_is_open_adds_it_there(self):
        from iconlib.library import Library
        a = self.app
        a.sidebar._open(a.collections.get("Favorites"))
        a._pick_svg = lambda title: (Path("Tide.svg"), INK)
        a.import_icon()
        self.pump()
        dlg = next(w for w in a.winfo_children() if hasattr(w, "id_entry") and w.winfo_exists())
        dlg._confirm()
        self.pump()
        self.assertIn("tide", a.collections.members(a.collections.get("Favorites"))[0])
        self.assertIn("tide", a.gallery.visible_ids())
        a.sidebar._open(None)

    def test_14_renaming_an_icon_keeps_collections_working(self):
        a = self.app
        a.gallery.select("home")
        self.fake_prompt("house")
        a.rename_icon("home")
        self.pump()
        self.assertEqual(a.gallery.selected, "house")
        a.sidebar._open(a.collections.get("UI basics"))
        self.assertIn("house", a.gallery.visible_ids())
        self.assertFalse(a.gallery.banner.winfo_ismapped())                    # not reported missing
        self.fake_prompt("star")                                              # taken: error stays in the dialog
        a.rename_icon("house")
        self.assertIn("already exists", self.last_prompt_error)
        a.sidebar._open(None)

    def test_15_rename_and_delete_a_collection(self):
        a = self.app
        c = a.collections.get("Favorites")
        self.fake_prompt("Top picks")
        a.rename_collection(c)
        self.assertIn("Top picks", a.collections.names())
        self.fake_prompt("ui basics")
        a.rename_collection(c)
        self.assertIn("already a collection", self.last_prompt_error)
        a.sidebar._open(c)
        a.delete_collection(c)
        self.assertIsNone(a.current)
        self.assertNotIn("Top picks", a.collections.names())
        self.assertEqual(len(list((a.library / ".trash").glob("collection-*.json"))), 1)
        self.assertFalse(a.gallery.header.winfo_ismapped())


    # ----------------------------------------------------------------- export
    def open_export(self):
        a = self.app
        a.export_icons()
        self.pump()
        return a._ui_windows["export"]

    def wait_export(self, dlg, seconds=20):
        import time
        end = time.time() + seconds
        while time.time() < end and not dlg.done and dlg.error.cget("text") == "":
            self.app.update()
            time.sleep(0.02)

    def test_16_export_dialog_exports_the_open_collection(self):
        import hashlib
        a = self.app
        a.sidebar._open(a.collections.get("UI basics"))
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in a.library.rglob("*") if p.is_file()}
        dlg = self.open_export()
        self.assertTrue(next(iter(dlg.sources)).startswith("Collection: UI basics"))
        self.assertEqual(dlg.count.cget("text"), "5 icons")
        out = self.tmp / "exports" / "ui"
        dlg.folder.delete(0, "end")
        dlg.folder.insert(0, str(out))
        dlg.png.select()
        dlg.png_sizes.delete(0, "end")
        dlg.png_sizes.insert(0, "16, 32")
        dlg._start()
        self.wait_export(dlg)
        self.assertTrue(dlg.done, dlg.error.cget("text"))
        self.assertEqual(len(dlg.result.icons), 5)
        self.assertTrue((out / "svg" / "plus.svg").exists() and (out / "png" / "16px" / "plus.png").exists())
        self.assertTrue((out / "icons-theme.css").exists())
        saved = a.settings["export"]
        self.assertEqual((saved["png"], saved["png_sizes"], saved["dir"]), (True, [16, 32], str(out.parent)))
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in a.library.rglob("*") if p.is_file()}
        self.assertEqual(before, after)                                        # the master library is untouched
        dlg.destroy()
        a.sidebar._open(None)

    def test_17_export_dialog_reports_problems_instead_of_writing(self):
        a = self.app
        dlg = self.open_export()
        self.assertEqual(next(iter(dlg.sources)), "All icons (%d)" % len(a.lib.ids()))
        dlg.folder.delete(0, "end")
        dlg.folder.insert(0, str(a.library / "exports"))                       # inside the library
        dlg._start()
        self.wait_export(dlg)
        self.assertIn("outside the library", dlg.error.cget("text"))
        self.assertFalse((a.library / "exports").exists())
        dlg.folder.delete(0, "end")
        dlg.folder.insert(0, str(self.tmp / "exports" / "x"))
        dlg.svg_size.delete(0, "end")
        dlg.svg_size.insert(0, "banana")
        dlg._start()
        self.assertIn("whole numbers", dlg.error.cget("text"))
        dlg.svg_size.delete(0, "end")
        dlg.svg_size.insert(0, "48")
        for cb in dlg.theme_boxes.values():
            cb.deselect()
        dlg._start()
        self.wait_export(dlg)
        self.assertIn("at least one theme", dlg.error.cget("text"))
        dlg.destroy()

    def test_18_the_export_window_toggles_and_a_selection_source_appears(self):
        a = self.app
        a.gallery.select("star")
        a.gallery.toggle_select("heart")
        dlg = self.open_export()
        self.assertTrue(next(iter(dlg.sources)).startswith("Selected icons (2)"))
        a.export_icons()                                                       # second press closes it
        self.pump()
        self.assertFalse(dlg.winfo_exists())


    # ------------------------------------------------------------- layout
    def test_19_first_tile_lines_up_with_the_search_bar(self):
        a = self.app
        a.sidebar.open_all()
        self.pump()
        first = a.gallery.tiles[a.gallery.visible_ids()[0]]
        self.assertEqual(first.winfo_rootx(), a.gallery.search.winfo_rootx())
        a.sidebar._open(a.collections.get("UI basics"))                  # also with the collection header showing
        self.pump()
        first = a.gallery.tiles[a.gallery.visible_ids()[0]]
        self.assertEqual(first.winfo_rootx(), a.gallery.search.winfo_rootx())
        a.sidebar.open_all()

    def test_20_the_depth_flag_row_only_shows_with_an_icon_selected(self):
        a = self.app
        a.gallery.select("star")
        a.detail.set_tab("Style")
        self.pump()
        self.assertTrue(a.style_panel.flag.winfo_ismapped())
        a.gallery.select(None)
        self.pump()
        self.assertFalse(a.style_panel.flag.winfo_ismapped())
        a.detail.set_tab("Icon")


    def test_21_thickness_is_always_set_and_old_as_drawn_styles_are_upgraded(self):
        from iconlib.style import Style
        from stylepanel import with_thickness
        a = self.app
        self.assertFalse(hasattr(a.style_panel, "stroke_mode"))                 # no "As drawn" choice any more
        self.assertEqual(with_thickness(Style(box="circle")).stroke, 2.0)       # old saved style: thickness added
        self.assertEqual(with_thickness(Style(stroke=3.0)).stroke, 3.0)         # an explicit choice is kept
        a.style_panel.stroke.set(3.5)
        a.style_panel._slid(a.style_panel.stroke)(3.5)
        a.style_panel._emit()
        self.assertEqual(a.thumbs.style.stroke, 3.5)
        a.style_panel.reset()
        self.assertEqual(a.thumbs.style.stroke, 2.0)


    # ------------------------------------------------- scrolling + alignment rules
    def test_22_mouse_wheel_scrolls_an_overflowing_panel_and_leaves_a_fitting_one_alone(self):
        a = self.app
        a.geometry("1100x430")                                   # short window: the Style tab overflows
        a.detail.set_tab("Style")
        a.gallery.select("star")
        for _ in range(5):
            self.pump()
        canvas = a.detail._parent_canvas
        self.assertNotEqual(canvas.cget("scrollregion"), "")     # CTk's scroll region must be alive
        self.assertNotEqual(canvas.yview(), (0.0, 1.0))          # the content really is taller than the panel
        target = a.style_panel.box_menu
        start = canvas.yview()[0]
        target.event_generate("<MouseWheel>", x=5, y=5, delta=-120)
        self.pump()
        down = canvas.yview()[0]
        self.assertGreater(down, start)                          # wheel down scrolls down...
        target.event_generate("<MouseWheel>", x=5, y=5, delta=120)
        self.pump()
        self.assertLess(canvas.yview()[0], down)                 # ...and wheel up scrolls back
        a.geometry("1100x700")
        a.detail.set_tab("Icon")
        for _ in range(5):
            self.pump()

    def test_23_style_controls_share_one_visible_left_edge(self):
        import dave_theme as ui
        a = self.app
        a.detail.set_tab("Style")
        a.gallery.select("star")
        for _ in range(3):
            self.pump()
        p = a.style_panel
        p.box_menu.set("Rounded")
        p._enable()
        self.pump()
        edge = p.theme_menu.winfo_rootx()
        self.assertEqual(p.box_menu.winfo_rootx(), edge)
        for box in (p.pad_box, p.rad_box, p.depth_box, p.stroke_box):         # a slider's TRACK starts inside its widget
            self.assertEqual(box.winfo_rootx() + ui.SLIDER_INSET, edge)
        self.assertEqual(p.flag.winfo_rootx(), edge)
        a.detail.set_tab("Icon")


if __name__ == "__main__":
    unittest.main()
