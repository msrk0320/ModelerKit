"""The whole add-on: the real panel, undo on every button, Import/Reload, Find Flipped UVs.
Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_modelerkit_blender.py"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelerkit  # noqa: E402
from modelerkit import panel, uv_flipped  # noqa: E402

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
            "modelerkit.name_materials_from_root", "modelerkit.find_folded_uvs",
            "modelerkit.reload_textures", "modelerkit.import_textures"})
        self.assertEqual(set(layout.props), {"mk_explode_factor", "mk_explode_selected_only", "mk_sp_texture_folder"})
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


def grid(name="front_rim", cuts=8):
    """A flat grid, unwrapped as one island laid out like the mesh (UV = x, y)."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts, y_subdivisions=cuts, size=2.0)
    o = bpy.context.active_object
    o.name = name
    me = o.data
    uv = me.uv_layers.active.data
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uv[loop.index].uv = ((co.x + 1) / 2, (co.y + 1) / 2)
    return o


def fold(o):
    """Move every UV corner on the middle vertex: the faces around it fold over, the island stays one piece."""
    me = o.data
    uv = me.uv_layers.active.data
    vertex = min(range(len(me.vertices)), key=lambda i: me.vertices[i].co.length)
    for loop in me.loops:
        if loop.vertex_index == vertex:
            uv[loop.index].uv = (uv[loop.index].uv[0] + 0.3, uv[loop.index].uv[1])


class FindFlippedUvTests(Base):
    def test_a_fold_is_found_inside_one_island(self):
        o = grid()
        fold(o)
        folds, islands = uv_flipped.folded(o.data)
        self.assertGreater(len(folds), 0)
        self.assertEqual(len(set(islands)), 1)

    def test_a_whole_island_mirrored_on_purpose_is_not_folded(self):
        o = grid()
        for d in o.data.uv_layers.active.data:
            d.uv = (1.0 - d.uv[0], d.uv[1])
        self.assertEqual(uv_flipped.folded(o.data)[0], [])

    def test_find_selects_the_folded_faces(self):
        o = grid()
        fold(o)
        folds, _islands = uv_flipped.folded(o.data)
        self.assertEqual(bpy.ops.modelerkit.find_folded_uvs(), {"FINISHED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        self.assertEqual([p.index for p in o.data.polygons if p.select], folds)

    def test_a_mesh_without_uvs_does_not_crash(self):
        select(mesh("bare", uvs=()))
        self.assertEqual(bpy.ops.modelerkit.find_folded_uvs(), {"FINISHED"})

    def test_works_when_the_active_object_is_not_a_mesh(self):
        o = grid()
        fold(o)
        empty = bpy.data.objects.new("empty", None)
        bpy.context.scene.collection.objects.link(empty)
        bpy.context.view_layer.update()
        select(empty, o)
        self.assertEqual(bpy.ops.modelerkit.find_folded_uvs(), {"FINISHED"})


def setUpModule():
    modelerkit.register()


def tearDownModule():
    modelerkit.unregister()


if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
