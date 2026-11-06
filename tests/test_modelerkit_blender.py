"""The whole add-on: the real panel, undo on every button, Import/Reload, Install Painter Export.
Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_modelerkit_blender.py"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelerkit  # noqa: E402
from modelerkit import panel, sp_texture_link  # noqa: E402

MAP_NAMES = ("BaseColor", "Roughness", "Metallic", "Normal", "Transmissive")


class Recorder:
    """Stands in for a layout: remembers the operators and properties drawn."""
    def __init__(self):
        self.ops, self.props = [], []

    def operator(self, idname, **kwargs):
        self.ops.append(idname)
        return self

    def prop(self, data, name, **kwargs):
        getattr(data, name)  # raises if the property isn't registered
        self.props.append(name)
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


def ui():
    """A window context, which undo needs."""
    return bpy.context.temp_override(window=bpy.context.window_manager.windows[0])


def mesh(name, parent=None, uvs=("UVMap",), material=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    for u in uvs:
        me.uv_layers.new(name=u)
    if material:
        me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    o.parent = parent
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return o


def select(*objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def write_png(path, value=0.5):
    img = bpy.data.images.new("tmp", 4, 4)
    img.pixels = [value] * 64
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


class Base(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")


class PanelTests(Base):
    def test_every_button_on_the_panel_exists(self):
        layout = Recorder()
        panel.VIEW3D_PT_modelerkit.draw(type("P", (), {"layout": layout})(), bpy.context)
        self.assertEqual(set(layout.ops), {
            "modelerkit.explode_reset", "modelerkit.toggle_lock_location", "modelerkit.single_uv_map",
            "modelerkit.dimensions_fit", "modelerkit.check_lens_gap", "modelerkit.close_lens_gap",
            "modelerkit.name_materials_from_root",
            "modelerkit.reload_textures", "modelerkit.import_textures", "modelerkit.install_painter_export"})
        self.assertEqual(set(layout.props), {"mk_explode_factor", "mk_explode_axis", "mk_explode_selected_only",
                                             "mk_lens_gap_search", "mk_lens_gap_offset", "mk_sp_texture_folder",
                                             "exact_frame", "paste", "frame_width", "bridge", "lens_height",
                                             "temple_length", "show",
                                             "mk_sp_import_normal"})
        for idname in layout.ops:
            group, name = idname.split(".")
            getattr(getattr(bpy.ops, group), name).get_rna_type()  # raises if not registered


class UndoTests(Base):
    def press_then_undo(self, op):
        with ui():
            bpy.ops.ed.undo_push(message="Setup")
            op("EXEC_DEFAULT", True)
            bpy.ops.ed.undo()

    def test_lock_location(self):
        o = mesh("o")
        select(o)
        self.press_then_undo(bpy.ops.modelerkit.toggle_lock_location)
        self.assertEqual(tuple(bpy.data.objects["o"].lock_location), (False, False, False))

    def test_single_uv_map(self):
        o = mesh("o", uvs=("A", "B"))
        select(o)
        self.press_then_undo(bpy.ops.modelerkit.single_uv_map)
        self.assertEqual([u.name for u in bpy.data.objects["o"].data.uv_layers], ["A", "B"])

    def test_single_material(self):
        o = mesh("o", material=bpy.data.materials.new("Old"))
        select(o)
        self.press_then_undo(bpy.ops.modelerkit.name_materials_from_root)
        self.assertEqual(bpy.data.objects["o"].data.materials[0].name, "Old")

    def test_import_textures(self):
        o = mesh("o", material=bpy.data.materials.new("Mat_o"))
        select(o)
        write_png(os.path.join(self.tmp, "Mat_o_BaseColor.png"))
        bpy.context.scene.mk_sp_texture_folder = self.tmp
        self.press_then_undo(bpy.ops.modelerkit.import_textures)
        mat = bpy.data.objects["o"].data.materials[0]
        self.assertFalse(mat.node_tree and any(n.name.startswith("SPLink_") for n in mat.node_tree.nodes))


class TextureTests(Base):
    def setUp(self):
        super().setUp()
        self.mat = bpy.data.materials.new("Mat_R")
        select(mesh("o", material=self.mat))
        bpy.context.scene.mk_sp_texture_folder = self.tmp

    def linked(self):
        bsdf = next(n for n in self.mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        return {s.name for s in bsdf.inputs if s.is_linked}

    def test_import_wires_every_map_and_twice_stays_clean(self):
        for name in MAP_NAMES:
            write_png(os.path.join(self.tmp, "Mat_R_%s.png" % name))
        for _ in range(2):
            self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color", "Roughness", "Metallic", "Normal", "Transmission Weight"})
        self.assertEqual(sum(n.name.startswith("SPLink_") for n in self.mat.node_tree.nodes), 6)
        self.assertEqual(sum(i.name.startswith("Mat_R_") for i in bpy.data.images), 5)

    def test_delivery_pack_names_match_the_mat_material(self):
        for name in ("basecolor", "roughness", "metalness", "normal", "transmissive"):
            write_png(os.path.join(self.tmp, "R_%s.png" % name))
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color", "Roughness", "Metallic", "Normal", "Transmission Weight"})

    def test_mat_textures_match_a_material_without_the_prefix(self):
        self.mat.name = "R"
        write_png(os.path.join(self.tmp, "Mat_R_BaseColor.png"))
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color"})

    def test_unticking_normal_map_skips_it_and_removes_one_already_connected(self):
        for name in MAP_NAMES:
            write_png(os.path.join(self.tmp, "Mat_R_%s.png" % name))
        bpy.ops.modelerkit.import_textures()
        self.assertIn("Normal", self.linked())
        bpy.context.scene.mk_sp_import_normal = False
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color", "Roughness", "Metallic", "Transmission Weight"})
        self.assertFalse(any(n.name.startswith(("SPLink_Normal", "SPLink_NormalMap")) for n in self.mat.node_tree.nodes))
        bpy.context.scene.mk_sp_import_normal = True
        bpy.ops.modelerkit.import_textures()
        self.assertIn("Normal", self.linked())

    def test_unticked_with_only_a_normal_file_is_not_a_name_mismatch(self):
        write_png(os.path.join(self.tmp, "Mat_R_Normal.png"))
        bpy.context.scene.mk_sp_import_normal = False
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), set())

    def save_blend_with_export_folder(self):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(self.tmp, "JOB.blend"))
        self.mat = bpy.data.materials["Mat_R"]
        export = os.path.join(self.tmp, "JOB", "Textures")
        os.makedirs(export)
        return export

    def test_default_folder_finds_painters_export_folder(self):
        write_png(os.path.join(self.save_blend_with_export_folder(), "Mat_R_BaseColor.png"))
        bpy.context.scene.mk_sp_texture_folder = "//"
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color"})
        self.assertEqual(bpy.ops.modelerkit.reload_textures(), {"FINISHED"})

    def test_default_folder_still_reads_the_blends_folder_without_an_export_folder(self):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(self.tmp, "JOB.blend"))
        self.mat = bpy.data.materials["Mat_R"]
        write_png(os.path.join(self.tmp, "Mat_R_BaseColor.png"))
        bpy.context.scene.mk_sp_texture_folder = "//"
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Base Color"})

    def test_a_picked_folder_is_not_redirected_to_the_export_folder(self):
        write_png(os.path.join(self.save_blend_with_export_folder(), "Mat_R_BaseColor.png"))
        write_png(os.path.join(self.tmp, "Mat_R_Roughness.png"))
        bpy.context.scene.mk_sp_texture_folder = self.tmp
        self.assertEqual(bpy.ops.modelerkit.import_textures(), {"FINISHED"})
        self.assertEqual(self.linked(), {"Roughness"})

    def test_empty_folder_field_asks_for_a_folder(self):
        bpy.context.scene.mk_sp_texture_folder = ""
        with self.assertRaisesRegex(RuntimeError, "Pick a texture folder"):
            bpy.ops.modelerkit.import_textures()

    def test_reload_reads_the_new_file(self):
        path = os.path.join(self.tmp, "Mat_R_BaseColor.png")
        write_png(path, 0.2)
        bpy.ops.modelerkit.import_textures()
        before = bpy.data.images["Mat_R_BaseColor.png"].pixels[0]
        write_png(path, 0.8)
        self.assertEqual(bpy.ops.modelerkit.reload_textures(), {"FINISHED"})
        self.assertGreater(bpy.data.images["Mat_R_BaseColor.png"].pixels[0], before + 0.1)

    def test_reload_does_not_count_a_deleted_file(self):
        path = os.path.join(self.tmp, "Mat_R_BaseColor.png")
        write_png(path)
        bpy.ops.modelerkit.import_textures()
        os.remove(path)
        self.assertEqual(bpy.ops.modelerkit.reload_textures(), {"CANCELLED"})


class InstallPainterExportTests(Base):
    def setUp(self):
        super().setUp()
        self.original = sp_texture_link._painter_folder
        sp_texture_link._painter_folder = lambda: self.tmp

    def tearDown(self):
        sp_texture_link._painter_folder = self.original
        super().tearDown()

    def test_copies_the_script_into_startup_and_replaces_an_older_copy(self):
        target = Path(self.tmp, "python", "startup", "export_to_project_folder.py")
        target.parent.mkdir(parents=True)
        target.write_text("old")
        self.assertEqual(bpy.ops.modelerkit.install_painter_export(), {"FINISHED"})
        self.assertEqual(target.read_bytes(), Path(sp_texture_link.PAINTER_SCRIPT).read_bytes())

    def test_button_greys_out_once_installed_and_returns_for_a_different_copy(self):
        self.assertTrue(bpy.ops.modelerkit.install_painter_export.poll())
        bpy.ops.modelerkit.install_painter_export()
        self.assertFalse(bpy.ops.modelerkit.install_painter_export.poll())
        target = Path(self.tmp, "python", "startup", "export_to_project_folder.py")
        target.write_text("old")
        self.assertTrue(bpy.ops.modelerkit.install_painter_export.poll())
        target.unlink()
        self.assertTrue(bpy.ops.modelerkit.install_painter_export.poll())

    def test_no_painter_folder_says_so_and_creates_nothing(self):
        missing = os.path.join(self.tmp, "none")
        sp_texture_link._painter_folder = lambda: missing
        with self.assertRaisesRegex(RuntimeError, "Painter's folder not found"):
            bpy.ops.modelerkit.install_painter_export()
        self.assertFalse(os.path.exists(missing))


class UninstallTest(unittest.TestCase):
    def test_outside_an_extension_it_refuses_and_keeps_the_addon(self):
        # run from a file or --python, the package is not bl_ext.*, so nothing may be removed
        with self.assertRaisesRegex(RuntimeError, "Not installed as an extension"):
            bpy.ops.modelerkit.uninstall("EXEC_DEFAULT")


def setUpModule():
    modelerkit.register()


def tearDownModule():
    modelerkit.unregister()


if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
