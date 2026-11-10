"""Set Up Hierarchy, Rename Part, Copy Left to Right and Fold Temples.
Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_parts_blender.py"""
import sys
import unittest
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelerkit  # noqa: E402
from modelerkit import parts  # noqa: E402
from tests.test_dimensions_blender import box_mesh, build, empty  # noqa: E402


def select(*objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0] if objs else None


def world_verts(o):
    return sorted(tuple(round(c, 4) for c in o.matrix_world @ v.co) for v in o.data.vertices)


def volume(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


class Base(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)

    def tearDown(self):
        bpy.context.scene.mk_temple_fold = 0.0


class HierarchyTests(Base):
    def test_sorts_selected_parts_into_a_new_tree_and_keeps_them_in_place(self):
        rim = box_mesh("front_rim", (-7, -2, 0), (7, -1, 5), None)
        outer = box_mesh("temple_left_outer", (6, -1, 3), (6.5, 12, 4), None)
        stray = box_mesh("cube", (0, 0, 0), (1, 1, 1), None)
        bpy.context.view_layer.update()
        before = world_verts(outer)
        select(rim, outer, stray)
        bpy.ops.modelerkit.set_up_hierarchy()
        root = parts.product_root(bpy.context)
        self.assertIsNotNone(root)
        self.assertEqual(rim.parent.name, "frame")
        self.assertEqual(outer.parent.name, "temple_left")
        self.assertEqual(outer.parent.parent.name, "temples")
        self.assertIsNone(stray.parent)
        self.assertEqual(world_verts(outer), before)

    def test_reuses_the_existing_tree_and_a_temple_mesh_as_its_group(self):
        root = build()
        loose = box_mesh("lens_left.001", (0, 0, 0), (1, 1, 1), None)
        select(loose)
        bpy.ops.modelerkit.set_up_hierarchy()
        self.assertEqual(parts.product_root(bpy.context), root)
        self.assertEqual(sum(o.name.startswith("frame") for o in bpy.data.objects), 1)
        self.assertEqual(loose.parent.name, "lenses")

    def test_nothing_selected_sorts_every_named_part(self):
        lens = box_mesh("lens_right", (0, 0, 0), (1, 1, 1), None)
        select()
        bpy.ops.modelerkit.set_up_hierarchy()
        self.assertEqual(lens.parent.name, "lenses")


class RenameTests(Base):
    def test_renames_the_active_object_and_warns_on_a_taken_name(self):
        a = box_mesh("a", (0, 0, 0), (1, 1, 1), None)
        b = box_mesh("b", (0, 0, 0), (1, 1, 1), None)
        select(a)
        bpy.ops.modelerkit.rename_part(part="screw_left")
        self.assertEqual(a.name, "screw_left")
        select(b)
        bpy.ops.modelerkit.rename_part(part="screw_left")
        self.assertNotEqual(b.name, "screw_left")


class CopyLeftToRightTests(Base):
    def test_replaces_the_right_mesh_with_a_mirror_facing_out(self):
        build()
        left, right = bpy.data.objects["temple_left_outer"], bpy.data.objects["temple_right_outer"]
        right.data.vertices[0].co.x -= 3
        select(left)
        bpy.ops.modelerkit.copy_left_to_right()
        self.assertEqual(world_verts(right), sorted((-x, y, z) for x, y, z in world_verts(left)))
        self.assertGreater(volume(right), 0)
        self.assertEqual(right.parent.name, "temple_right")

    def test_a_left_group_copies_every_left_part_under_it_and_makes_missing_ones(self):
        build()
        bpy.data.objects.remove(bpy.data.objects["hinge_temple_right"])
        select(bpy.data.objects["temple_left"])
        bpy.ops.modelerkit.copy_left_to_right()
        made = bpy.data.objects["hinge_temple_right"]
        self.assertEqual(made.parent.name, "temple_right")
        self.assertEqual(world_verts(made),
                         sorted((-x, y, z) for x, y, z in world_verts(bpy.data.objects["hinge_temple_left"])))

    def test_needs_a_left_part(self):
        build()
        select(bpy.data.objects["front_rim"])
        self.assertFalse(bpy.ops.modelerkit.copy_left_to_right.poll())


class FoldTests(Base):
    def xs(self, name):
        return [x for x, _y, _z in world_verts(bpy.data.objects[name])]

    def test_both_tips_swing_inward_and_zero_restores_exactly(self):
        build()
        before = {n: world_verts(bpy.data.objects[n]) for n in ("temple_left_outer", "temple_right_outer")}
        bpy.context.scene.mk_temple_fold = 1.5708
        self.assertLess(min(self.xs("temple_left_outer")), -7)  # the tip crosses behind the other lens
        self.assertGreater(max(self.xs("temple_right_outer")), 7)
        self.assertLess(max(y for _x, y, _z in world_verts(bpy.data.objects["temple_left_outer"])), -1.9)
        bpy.context.scene.mk_temple_fold = 0.0
        for n, verts in before.items():
            self.assertEqual(world_verts(bpy.data.objects[n]), verts)
        self.assertFalse(parts.folded(bpy.context.scene))

    def test_scaling_the_root_while_folded_unfolds_at_the_new_size(self):
        root = build()
        bpy.context.scene.mk_temple_fold = 1.0
        root.scale *= 2
        bpy.context.view_layer.update()
        bpy.context.scene.mk_temple_fold = 0.0
        hinge = bpy.data.objects["hinge_temple_left"]
        self.assertAlmostEqual(min((hinge.matrix_world @ v.co).x for v in hinge.data.vertices), 12.0, places=4)


def setUpModule():
    modelerkit.register()


def tearDownModule():
    modelerkit.unregister()


if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
