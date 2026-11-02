"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\test_uv_material_blender.py"""
import sys
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import uv_material  # noqa: E402


def mesh_obj(name, uvs, mats=(), parent=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    for u in uvs:
        me.uv_layers.new(name=u)
    for m in mats:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    o.parent = parent
    bpy.context.scene.collection.objects.link(o)
    o.select_set(True)
    return o


class UvMaterialTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        uv_material.register()

    def tearDown(self):
        uv_material.unregister()

    def test_keeps_active_uv_only_and_names_it(self):
        o = mesh_obj("a", ["Front", "Lightmap", "Old"])
        o.data.uv_layers.active = o.data.uv_layers["Lightmap"]
        bpy.ops.modelerkit.single_uv_map()
        self.assertEqual([l.name for l in o.data.uv_layers], ["UVMap"])

    def test_new_product_does_not_share_a_material_with_an_unselected_one(self):
        old = mesh_obj("A", [])
        bpy.ops.modelerkit.name_materials_from_root()
        old.name = "A_OLD"
        new = mesh_obj("A", [])
        bpy.ops.object.select_all(action="DESELECT")
        new.select_set(True)
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertIsNot(old.data.materials[0], new.data.materials[0])

    def test_pressing_again_on_part_of_a_product_keeps_the_product_material(self):
        root = mesh_obj("R", [])
        a, b = mesh_obj("a", [], parent=root), mesh_obj("b", [], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        bpy.ops.object.select_all(action="DESELECT")
        a.select_set(True)
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual([m.name for m in bpy.data.materials], ["Mat_R"])
        self.assertIs(a.data.materials[0], b.data.materials[0])

    def test_deleting_a_part_does_not_make_a_new_material(self):
        root = mesh_obj("R", [])
        a, b = mesh_obj("a", [], parent=root), mesh_obj("b", [], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        bpy.data.objects.remove(b)  # its mesh stays in the file with no users, like X > Delete
        for _ in range(2):
            bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual([m.name for m in bpy.data.materials], ["Mat_R"])

    def test_pressing_again_after_a_name_clash_makes_no_more_copies(self):
        stray = mesh_obj("stray", [], mats=[bpy.data.materials.new("Mat_R")])
        stray.select_set(False)
        root = mesh_obj("R", [])
        for _ in range(3):
            bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual(sorted(m.name for m in bpy.data.materials), ["Mat_R", "Mat_R.001"])
        self.assertEqual(root.data.materials[0].name, "Mat_R.001")
        self.assertEqual(stray.data.materials[0].name, "Mat_R")

    def test_mesh_without_uv_is_skipped(self):
        o = mesh_obj("a", [])
        bpy.ops.modelerkit.single_uv_map()
        self.assertEqual(len(o.data.uv_layers), 0)

    def test_single_material_takes_root_name(self):
        root = bpy.data.objects.new("SDNA-263230", None)
        bpy.context.scene.collection.objects.link(root)
        mat = bpy.data.materials.new("Material.001")
        o = mesh_obj("frame", ["UVMap"], [mat], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual(o.data.materials[0].name, "Mat_SDNA-263230")

    def test_several_materials_collapse_to_one_on_every_face(self):
        root = bpy.data.objects.new("SKU9", None)
        bpy.context.scene.collection.objects.link(root)
        a, b = bpy.data.materials.new("x"), bpy.data.materials.new("y")
        frame = mesh_obj("frame", ["UVMap"], [a, b], parent=root)
        frame.data.polygons[0].material_index = 1
        lens = mesh_obj("lens", ["UVMap"], [b], parent=root)
        bare = mesh_obj("bare", ["UVMap"], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        for o in (frame, lens, bare):
            self.assertEqual([m.name for m in o.data.materials], ["Mat_SKU9"])
            self.assertEqual({p.material_index for p in o.data.polygons}, {0})
        self.assertIs(frame.data.materials[0], lens.data.materials[0])

    def test_roots_sharing_a_material_get_their_own(self):
        shared = bpy.data.materials.new("Acetate")
        frames = []
        for name in ("SKU_A", "SKU_B"):
            root = bpy.data.objects.new(name, None)
            bpy.context.scene.collection.objects.link(root)
            frames.append(mesh_obj(name + "_frame", ["UVMap"], [shared], parent=root))
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual([o.data.materials[0].name for o in frames], ["Mat_SKU_A", "Mat_SKU_B"])

    def test_mesh_shared_by_two_roots_is_left_alone(self):
        """An Alt+D part used by two products cannot carry both SKU materials: skip it, don't split a product."""
        roots = []
        for name in ("SKU_A", "SKU_B"):
            root = bpy.data.objects.new(name, None)
            bpy.context.scene.collection.objects.link(root)
            roots.append(root)
        old = bpy.data.materials.new("Acetate")
        a_frame = mesh_obj("a_frame", ["UVMap"], [old], parent=roots[0])
        a_screw = mesh_obj("a_screw", ["UVMap"], [old], parent=roots[0])
        b_screw = bpy.data.objects.new("b_screw", a_screw.data)
        b_screw.parent = roots[1]
        bpy.context.scene.collection.objects.link(b_screw)
        b_screw.select_set(True)
        b_frame = mesh_obj("b_frame", ["UVMap"], [old], parent=roots[1])
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual(a_frame.data.materials[0].name, "Mat_SKU_A")
        self.assertEqual(b_frame.data.materials[0].name, "Mat_SKU_B")
        self.assertIs(a_screw.data.materials[0], old)  # untouched

    def test_unselected_product_keeps_its_material_name(self):
        shared = bpy.data.materials.new("Acetate")
        other = mesh_obj("other", ["UVMap"], [shared])
        other.select_set(False)
        root = bpy.data.objects.new("SKU_A", None)
        bpy.context.scene.collection.objects.link(root)
        mine = mesh_obj("frame", ["UVMap"], [shared], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual(mine.data.materials[0].name, "Mat_SKU_A")
        self.assertEqual(other.data.materials[0].name, "Acetate")

    def test_an_existing_sku_material_is_reused_not_renamed_to_001(self):
        """Renaming Acetate onto a taken Mat_SKU9 gave Mat_SKU9.001, which the packer can't read a SKU from."""
        root = bpy.data.objects.new("SKU9", None)
        bpy.context.scene.collection.objects.link(root)
        sku_mat, acetate = bpy.data.materials.new("Mat_SKU9"), bpy.data.materials.new("Acetate")
        temple = mesh_obj("temple", ["UVMap"], [acetate], parent=root)      # first in the selection
        frame = mesh_obj("frame", ["UVMap"], [sku_mat], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        for o in (temple, frame):
            self.assertIs(o.data.materials[0], sku_mat)
        self.assertEqual(sku_mat.name, "Mat_SKU9")
        self.assertEqual(acetate.name, "Acetate")

    def test_a_material_on_an_object_linked_slot_elsewhere_is_copied(self):
        shared = bpy.data.materials.new("Acetate")
        other = mesh_obj("other", ["UVMap"])
        other.data.materials.append(None)
        other.material_slots[0].link = "OBJECT"
        other.material_slots[0].material = shared
        other.select_set(False)
        root = bpy.data.objects.new("SKU_A", None)
        bpy.context.scene.collection.objects.link(root)
        mine = mesh_obj("frame", ["UVMap"], [shared], parent=root)
        bpy.ops.modelerkit.name_materials_from_root()
        self.assertEqual(mine.data.materials[0].name, "Mat_SKU_A")
        self.assertEqual(other.material_slots[0].material.name, "Acetate")

    def test_not_offered_in_edit_mode(self):
        """In Edit Mode the edit mesh wrote the old material indices back on exit, onto a slot that was gone."""
        o = mesh_obj("frame", ["UVMap"], [bpy.data.materials.new("x")])
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        self.assertFalse(bpy.ops.modelerkit.name_materials_from_root.poll())
        bpy.ops.object.mode_set(mode="OBJECT")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
