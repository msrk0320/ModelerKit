"""Run: blender -b --factory-startup --python-exit-code 1 --python tests\\test_flips_blender.py"""
import math
import os
import sys
import tempfile
import unittest

import bmesh
import bpy
import numpy as np

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import flips, sp_texture_link  # noqa: E402


def snapshot(me):
    """Capture mesh state: winding, UVs, normals, and flags."""
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    normals = [tuple(n.vector) for n in me.corner_normals]
    return flips.winding(me), uv.tobytes(), normals, flips.flags(me)


def simple_box(name, size=1.0):
    """Box with 6 faces (one per side), UVs laid out in a grid."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.normal_update()
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        axis = max(range(3), key=lambda i: abs(f.normal[i]))
        cell = axis * 2 + (0 if f.normal[axis] > 0 else 1)
        cx, cy = cell % 3, cell // 3
        for loop in f.loops:
            loop[uv].uv = (cx / 3.0, cy / 2.0)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


class FlipCoreTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.box = simple_box("test_box")

    def test_uv_islands_partitions_faces_by_connectivity(self):
        me = self.box.data
        islands = flips.mesh_islands(me)
        self.assertEqual(len(set(islands)), 6)  # 6 faces = 6 islands (no seams)

    def test_flags_round_trip(self):
        me = self.box.data
        values = [i % 2 == 0 for i in range(len(me.polygons))]
        flips.set_flags(me, values)
        self.assertEqual(flips.flags(me), values)
        self.assertEqual(flips.flagged(me), [i for i, v in enumerate(values) if v])

    def test_flagged_returns_indices_where_flag_is_true(self):
        me = self.box.data
        flips.set_flags(me, [True, False, True, False, False, False])
        self.assertEqual(flips.flagged(me), [0, 2])

    def test_flip_faces_reverses_winding_and_turns_normals(self):
        me = self.box.data
        faces = [0, 1]
        before_winding = flips.winding(me)
        before_normals = [tuple(n.vector) for n in me.corner_normals]
        flips.flip_faces(me, faces)
        after_winding = flips.winding(me)
        after_normals = [tuple(n.vector) for n in me.corner_normals]
        self.assertNotEqual(before_winding, after_winding)
        # Some normals should have opposite direction for flipped faces
        for p_idx in faces:
            for li in me.polygons[p_idx].loop_indices:
                before_n = before_normals[li]
                after_n = after_normals[li]
                dot = sum(b * a for b, a in zip(before_n, after_n))
                self.assertLess(dot, 0)  # Opposite direction

    def test_flip_faces_preserves_custom_normals(self):
        me = self.box.data
        custom_normals = [(0.3, 0.4, math.sqrt(0.75)) if i % 3 == 0 else tuple(n.vector)
                           for i, n in enumerate(me.corner_normals)]
        me.normals_split_custom_set(custom_normals)
        faces = [0, 1]
        before = snapshot(me)
        flips.flip_faces(me, faces)
        after = snapshot(me)
        # Winding and normals differ, but structure matches
        self.assertNotEqual(before[0], after[0])  # winding changed
        self.assertEqual(before[1], after[1])  # UVs unchanged
        self.assertNotEqual(before[2], after[2])  # normals flipped

    def test_unflipped_context_manager_restores_mesh_exactly(self):
        me = self.box.data
        me.normals_split_custom_set([(0.3, 0.4, math.sqrt(0.75)) if i % 3 == 0 else tuple(n.vector)
                                       for i, n in enumerate(me.corner_normals)])
        faces = [0, 1, 2]
        flips.set_flags(me, [i in faces for i in range(len(me.polygons))])
        before = snapshot(me)
        with flips.unflipped([self.box]):
            # Inside context, flagged faces should be unflipped
            after_inside = snapshot(me)
            self.assertNotEqual(before, after_inside)  # State changed
        after = snapshot(me)
        self.assertEqual(before, after)  # State restored exactly


class GrowToIslandsTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.box = simple_box("test_box")

    def test_grow_to_islands_returns_whole_islands(self):
        me = self.box.data
        # Select one face
        result = flips.grow_to_islands(me, [0])
        # Without seams, each face is its own island, so result is [0]
        self.assertEqual(result, [0])

    def test_whole_islands_detects_complete_islands(self):
        me = self.box.data
        self.assertTrue(flips.whole_islands(me, [0]))
        self.assertTrue(flips.whole_islands(me, list(range(len(me.polygons)))))

    def test_whole_islands_works_with_multiple_separate_islands(self):
        me = self.box.data
        # Box has 6 faces, each is its own island. [0, 1] covers two islands, so it's "whole"
        self.assertTrue(flips.whole_islands(me, [0, 1]))


class MarkOperatorTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.box = simple_box("test_box")
        # Register the operator
        try:
            bpy.utils.register_class(flips.MODELERKIT_OT_mark_flipped)
        except ValueError:
            pass  # Already registered

    def tearDown(self):
        try:
            bpy.utils.unregister_class(flips.MODELERKIT_OT_mark_flipped)
        except RuntimeError:
            pass

    def test_mark_in_edit_mode_grows_to_whole_islands(self):
        me = self.box.data
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        bpy.ops.mesh.select_all(action="DESELECT")
        ebm = bmesh.from_edit_mesh(me)
        ebm.faces.ensure_lookup_table()
        ebm.faces[0].select_set(True)
        bmesh.update_edit_mesh(me)
        result = bpy.ops.modelerkit.mark_flipped()
        self.assertEqual(result, {"FINISHED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        # Face 0 should be flipped and marked (along with any island mates)
        flagged = flips.flagged(me)
        self.assertIn(0, flagged)
        # Winding should change (faces were flipped)
        self.assertTrue(len(flagged) > 0)

    def test_flags_readable_in_edit_mode(self):
        """The panel counts marks while the mesh is in Edit Mode (attribute data is empty there)."""
        me = self.box.data
        flips.set_flags(me, [True] + [False] * (len(me.polygons) - 1))
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            self.assertEqual(flips.flagged(me), [0])
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

    def test_mark_flips_the_faces_and_marks_them(self):
        """Mark Flipped does Alt+N > Flip itself; marking the same faces again must not flip them twice."""
        me = self.box.data
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        before_winding = flips.winding(me)
        result = bpy.ops.modelerkit.mark_flipped()
        self.assertEqual(result, {"FINISHED"})
        self.assertNotEqual(flips.winding(me), before_winding)
        self.assertEqual(len(flips.flagged(me)), len(me.polygons))
        marked_winding = flips.winding(me)
        bpy.ops.modelerkit.mark_flipped()
        self.assertEqual(flips.winding(me), marked_winding)

    def test_unmark_clears_flags_and_unflips(self):
        me = self.box.data
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        original = flips.winding(me)
        bpy.ops.modelerkit.mark_flipped()
        before_unmark = flips.flags(me)
        self.assertTrue(any(before_unmark))
        bpy.ops.modelerkit.mark_flipped(unmark=True)
        after_unmark = flips.flags(me)
        self.assertFalse(any(after_unmark))
        self.assertEqual(flips.winding(me), original)  # unmarking flips the faces back



class FixNormalsTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.box = simple_box("test_box")
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        try:
            bpy.utils.register_class(flips.MODELERKIT_OT_fix_normals)
        except ValueError:
            pass

    def tearDown(self):
        try:
            bpy.utils.unregister_class(flips.MODELERKIT_OT_fix_normals)
        except RuntimeError:
            pass

    def test_flips_only_the_wrong_facing_faces(self):
        me = self.box.data
        original = flips.winding(me)
        flips.flip_faces(me, [0, 3])
        self.assertEqual(flips.wrong_facing(me), [0, 3])
        self.assertEqual(bpy.ops.modelerkit.fix_normals(), {"FINISHED"})
        self.assertEqual(flips.winding(me), original)

    def test_lens_sheet_is_left_alone(self):
        lens = simple_box("lens_left")
        lens.select_set(True)
        flips.flip_faces(lens.data, [0])
        before = flips.winding(lens.data)
        bpy.ops.modelerkit.fix_normals()
        self.assertEqual(flips.winding(lens.data), before)

    def test_marked_faces_stay_flipped(self):
        me = self.box.data
        flips.flip_faces(me, [1])
        flips.set_flags(me, [i == 1 for i in range(len(me.polygons))])
        self.assertEqual(flips.wrong_facing(me), [])
        bpy.ops.modelerkit.fix_normals()
        self.assertEqual(flips.flagged(me), [1])
        self.assertEqual(flips.wrong_facing(me), [])


class SelectMarkedTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.box = simple_box("test_box")
        bpy.utils.register_class(flips.MODELERKIT_OT_select_marked)
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        flips.set_flags(self.box.data, [False, True, False, True, False, False])

    def tearDown(self):
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.utils.unregister_class(flips.MODELERKIT_OT_select_marked)

    def selected_faces(self):
        bm = bmesh.from_edit_mesh(self.box.data)
        return [f.index for f in bm.faces if f.select]

    def test_select_marked_from_object_mode_selects_exactly_the_marks(self):
        for p in self.box.data.polygons:
            p.select = True  # an old selection must not survive
        self.assertEqual(bpy.ops.modelerkit.select_marked(), {"FINISHED"})
        self.assertEqual(bpy.context.mode, "EDIT_MESH")
        self.assertEqual(tuple(bpy.context.tool_settings.mesh_select_mode), (False, False, True))
        self.assertEqual(self.selected_faces(), [1, 3])

    def test_select_marked_in_edit_mode_replaces_the_selection(self):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.modelerkit.select_marked(), {"FINISHED"})
        self.assertEqual(self.selected_faces(), [1, 3])


class UnflipForPackingTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        for c in (flips.MODELERKIT_OT_mark_flipped, flips.MODELERKIT_OT_unflip_for_packing):
            bpy.utils.register_class(c)
        self.box = simple_box("test_box")
        self.other = simple_box("other_box")
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box
        bpy.ops.modelerkit.mark_flipped()            # every face marked and flipped
        self.marked = snapshot(self.box.data)

    def tearDown(self):
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for c in (flips.MODELERKIT_OT_unflip_for_packing, flips.MODELERKIT_OT_mark_flipped):
            bpy.utils.unregister_class(c)

    def test_unflip_turns_marked_faces_back_and_keeps_the_marks(self):
        me = self.box.data
        self.assertEqual(bpy.ops.modelerkit.unflip_for_packing(), {"FINISHED"})
        self.assertNotEqual(flips.winding(me), self.marked[0])
        self.assertEqual(flips.flags(me), self.marked[3])
        self.assertEqual(flips.unflipped_for_packing(), [me])
        self.assertIn("test_box", flips.packing_block())

    def test_reflip_restores_every_unflipped_mesh_even_when_not_selected(self):
        me = self.box.data
        bpy.ops.modelerkit.unflip_for_packing()
        self.box.select_set(False)
        self.other.select_set(True)
        self.assertEqual(bpy.ops.modelerkit.unflip_for_packing(), {"FINISHED"})
        after = snapshot(me)
        self.assertEqual(after[0], self.marked[0])
        self.assertEqual(after[3], self.marked[3])
        self.assertEqual(flips.unflipped_for_packing(), [])
        self.assertIsNone(flips.packing_block())
        self.assertEqual(flips.flagged(self.other.data), [])     # the other mesh was not touched

    def test_unflip_in_edit_mode_returns_to_edit_mode(self):
        bpy.ops.object.mode_set(mode="EDIT")
        self.assertEqual(bpy.ops.modelerkit.unflip_for_packing(), {"FINISHED"})
        self.assertEqual(bpy.context.mode, "EDIT_MESH")
        bpy.ops.object.mode_set(mode="OBJECT")
        self.assertEqual(flips.unflipped_for_packing(), [self.box.data])

    def test_unflip_without_marks_does_nothing(self):
        self.box.select_set(False)
        self.other.select_set(True)
        bpy.context.view_layer.objects.active = self.other
        self.assertEqual(bpy.ops.modelerkit.unflip_for_packing(), {"CANCELLED"})
        self.assertEqual(flips.unflipped_for_packing(), [])

    def test_mark_is_refused_while_unflipped(self):
        bpy.ops.modelerkit.unflip_for_packing()
        before = snapshot(self.box.data)
        with self.assertRaises(RuntimeError):          # reported as an error
            bpy.ops.modelerkit.mark_flipped(unmark=True)
        self.assertEqual(snapshot(self.box.data)[0], before[0])
        self.assertEqual(snapshot(self.box.data)[3], before[3])


class ExportForPainterTests(unittest.TestCase):
    """Export for Painter writes marked faces flipped or unflipped as chosen; the working file stays as it was."""

    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sp_texture_link.register()
        flips.register()
        self.folder = tempfile.mkdtemp()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(self.folder, "job.blend"))
        self.box = simple_box("test_box")
        flips.flip_faces(self.box.data, [0])
        flips.set_flags(self.box.data, [i == 0 for i in range(6)])
        self.box.select_set(True)
        bpy.context.view_layer.objects.active = self.box

    def tearDown(self):
        flips.unregister()
        sp_texture_link.unregister()

    def inward_faces_in_fbx(self):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(self.folder, "job.fbx"))
        o = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
        mw = o.matrix_world
        centre = sum((mw @ v.co for v in o.data.vertices), mw.translation * 0) / len(o.data.vertices)
        rot = mw.to_3x3()
        return sum((rot @ p.normal).dot(mw @ p.center - centre) < 0 for p in o.data.polygons)

    def export(self, mode):
        bpy.context.scene.mk_fbx_send_mode = mode
        before = snapshot(self.box.data)
        self.assertEqual(bpy.ops.modelerkit.export_for_painter(), {"FINISHED"})
        self.assertEqual(snapshot(self.box.data), before)  # working mesh untouched

    def test_flipped_sends_the_faces_as_they_are(self):
        self.export("FLIPPED")
        self.assertEqual(self.inward_faces_in_fbx(), 1)

    def test_unflipped_turns_the_marked_faces_back(self):
        self.export("UNFLIPPED")
        self.assertEqual(self.inward_faces_in_fbx(), 0)

    def test_export_waits_while_unflipped_for_packing(self):
        bpy.ops.modelerkit.unflip_for_packing()
        with self.assertRaisesRegex(RuntimeError, "Re-flip after Packing"):
            bpy.ops.modelerkit.export_for_painter()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
