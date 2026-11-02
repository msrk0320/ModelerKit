"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_explode_blender.py"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import explode_slider as ex  # noqa: E402


def part(name, location, pieces=1, mesh=None):
    """Mesh object made of `pieces` loose unit cubes spread along X (or sharing `mesh`)."""
    if mesh is None:
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()
        for i in range(pieces):
            made = bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.translate(bm, vec=(i * 1.5, 0, 0), verts=made["verts"])
        bm.to_mesh(mesh)
        bm.free()
    o = bpy.data.objects.new(name, mesh)
    o.location = location
    bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    return o


def pos(o):
    return o.matrix_world.translation.copy()


def centre(o):
    return o.matrix_world @ (sum((Vector(c) for c in o.bound_box), Vector()) / 8)


def bbox_size(o):
    """Largest side of the object's world bounding box (scale and rotation included)."""
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))


def expected(objs, f):
    """Where the slider should put each object using along-X direction (default)."""
    centers = {o: centre(o) for o in objs}
    sizes = {o: bbox_size(o) for o in objs}
    # Rank by X coordinate of center, then by name; parts at the same X that sit apart on Y or Z share a rank
    ranked = sorted(objs, key=lambda o: (centers[o].x, o.name))
    step = f * max(sizes.values())
    rank, ranks, group = 0, [], []
    for i, o in enumerate(ranked):
        if i and (abs(centers[o].x - centers[ranked[i - 1]].x) > 1e-6 or not all(apart(o, g) for g in group)):
            rank, group = rank + 1, []
        group.append(o)
        ranks.append(rank)
    result = {}
    for o, r in zip(ranked, ranks):
        offset = (r - rank / 2) * step
        result[o.name] = pos(o) + Vector((offset, 0, 0))
    return result


def bounds(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def apart(a, b):
    """Boxes apart across X (on Y or Z)."""
    (alo, ahi), (blo, bhi) = bounds(a), bounds(b)
    return any(ahi[i] < blo[i] or bhi[i] < alo[i] for i in (1, 2))


def shown(o):
    """Vertex positions as displayed (shape keys applied, no modifiers in these tests)."""
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [v.co.copy() for v in ev.data.vertices]


def explode_key(o):
    keys = o.data.shape_keys
    return keys.key_blocks.get("Explode") if keys else None


def traces(o):
    return [k for k in o.keys() if k.startswith("_explode")]


def ui():
    """A window context, which undo needs. No area: in background mode the redo panel of a
    REGISTER operator run with an undo push crashes Blender (no region types to build it from)."""
    return bpy.context.temp_override(window=bpy.context.window_manager.windows[0])


def slide(f):
    """Move the slider the way the sidebar does: set it, then push an undo step."""
    bpy.context.scene.explode_factor = f
    with ui():
        bpy.ops.ed.undo_push(message="Explode")


def press(op, **props):
    """Click an operator button: runs with an undo push like the UI does."""
    with ui():
        return op('EXEC_DEFAULT', True, **props)


def select(*objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)


class ExplodeBase(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.sc = bpy.context.scene

    def assertNear(self, a, b, places=5):
        self.assertLess((Vector(a) - Vector(b)).length, 10 ** -places, f"{tuple(a)} != {tuple(b)}")

    def assertAt(self, where):
        for name, p in where.items():
            self.assertNear(pos(bpy.data.objects[name]), p)


class SliderTests(ExplodeBase):
    def test_all_visible_meshes_move_apart_and_come_back(self):
        objs = [part("frame", (0, 0, 0)), part("lens", (2, 0, 0)), part("temple", (0, 3, 1))]
        rest = expected(objs, 0)
        target = expected(objs, 2.0)
        slide(2.0)
        self.assertAt(target)
        slide(0.0)
        self.assertAt(rest)

    def test_selected_only_moves_just_the_selection(self):
        a, b, c = part("a", (0, 0, 0)), part("b", (2, 0, 0)), part("c", (5, 0, 0))
        self.sc.explode_selected_only = True
        select(a, b)
        target = expected([a, b], 1.0)
        c_rest = pos(c)
        slide(1.0)
        self.assertAt(target)
        self.assertNear(pos(c), c_rest)

    def test_split_pieces_spreads_the_islands_and_skips_single_piece_meshes(self):
        multi, single = part("multi", (0, 0, 0), pieces=2), part("single", (4, 0, 0))
        before = shown(multi)
        slide(1.0)
        self.assertIsNotNone(explode_key(multi))
        self.assertIsNone(single.data.shape_keys)
        self.assertNotEqual([round(v.x, 4) for v in shown(multi)], [round(v.x, 4) for v in before])
        slide(0.0)
        self.assertEqual([round(v.x, 4) for v in shown(multi)], [round(v.x, 4) for v in before])

    def test_unticking_split_pieces_puts_the_pieces_back(self):
        multi = part("multi", (0, 0, 0), pieces=2)
        part("other", (4, 0, 0))
        before = shown(multi)
        slide(1.0)
        self.sc.explode_islands = False
        for a, b in zip(shown(multi), before):
            self.assertNear(a, b)

    def test_split_pieces_off_never_builds_piece_data(self):
        multi = part("multi", (0, 0, 0), pieces=2)
        part("other", (4, 0, 0))
        self.sc.explode_islands = False
        slide(1.0)
        self.assertIsNone(multi.data.shape_keys)

    def test_child_and_parent_both_land_where_expected_and_come_back(self):
        child = part("A_child", (0, 0, 0))                   # first in the scene, so updated before its parent
        parent = part("B_parent", (4, 0, 0))
        child.parent = parent
        child.matrix_parent_inverse = parent.matrix_world.inverted()
        bpy.context.view_layer.update()
        rest = expected([child, parent], 0)
        target = expected([child, parent], 1.0)
        slide(1.0)
        self.assertAt(target)
        slide(0.0)
        self.assertAt(rest)

    def test_object_with_modifiers_moves_by_its_visible_centre_and_comes_back(self):
        arr = part("arr", (0, 0, 0))
        mod = arr.modifiers.new("Array", 'ARRAY')
        mod.count = 3
        other = part("other", (-3, 0, 0))
        bpy.context.view_layer.update()
        rest = expected([arr, other], 0)
        target = expected([arr, other], 1.0)              # bound_box includes the array copies
        slide(1.0)
        self.assertAt(target)
        slide(0.0)
        self.assertAt(rest)

    def test_linked_duplicates_share_the_pieces(self):
        a = part("a", (0, 0, 0), pieces=2)
        b = part("b", (6, 0, 0), mesh=a.data)
        slide(1.0)
        self.assertEqual(len(a.data.shape_keys.key_blocks), 2)    # one Explode key on the shared mesh
        self.assertEqual(shown(a), shown(b))
        slide(0.0)
        self.assertAlmostEqual(explode_key(a).value, 0.0)

    def test_non_mesh_objects_are_left_alone(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        empty = bpy.data.objects.new("empty", None)
        empty.location = (9, 0, 0)
        self.sc.collection.objects.link(empty)
        curve = bpy.data.objects.new("curve", bpy.data.curves.new("curve", 'CURVE'))
        curve.location = (0, 9, 0)
        self.sc.collection.objects.link(curve)
        self.sc.explode_selected_only = True
        select(a, b, empty, curve)
        target = expected([a, b], 1.0)
        slide(1.0)
        self.assertAt(target)
        self.assertNear(pos(empty), (9, 0, 0))
        self.assertNear(pos(curve), (0, 9, 0))
        self.assertEqual(traces(empty) + traces(curve), [])

    def test_empty_selection_moves_nothing(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        self.sc.explode_selected_only = True
        select()
        slide(1.0)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(b), (2, 0, 0))
        self.assertEqual(traces(a) + traces(b), [])

    def test_object_added_after_explode_is_captured_where_it_is(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        slide(1.0)
        new = part("new", (0, 5, 0))
        slide(0.5)
        slide(0.0)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(b), (2, 0, 0))
        self.assertNear(pos(new), (0, 5, 0))

    def test_copy_made_while_exploded_keeps_its_own_place(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        slide(1.0)
        dup = a.copy()                                     # Shift+D copies custom properties too
        self.sc.collection.objects.link(dup)
        dup.location = (0, 7, 0)
        bpy.context.view_layer.update()
        slide(0.5)
        slide(0.0)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(dup), (0, 7, 0))

    def test_object_renamed_while_exploded_still_comes_back(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        slide(1.0)
        a.name = "frame"
        slide(0.5)
        slide(0.0)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(b), (2, 0, 0))

    def test_object_deleted_after_explode_leaves_the_rest_working(self):
        a, b, c = part("a", (0, 0, 0)), part("b", (2, 0, 0)), part("c", (0, 4, 0))
        slide(1.0)
        bpy.data.objects.remove(c)
        slide(0.5)
        slide(0.0)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(b), (2, 0, 0))

    def test_object_moved_after_the_slider_returned_keeps_its_new_place(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        slide(1.0)
        slide(0.0)
        a.location = (-3, 0, 0)                            # the user goes on modelling at rest
        bpy.context.view_layer.update()
        slide(1.0)
        slide(0.0)
        self.assertNear(pos(a), (-3, 0, 0))
        self.assertNear(pos(b), (2, 0, 0))

    def test_edit_mode_at_rest_edits_the_mesh_not_the_explode_key(self):
        multi = part("multi", (0, 0, 0), pieces=2)
        part("other", (4, 0, 0))
        slide(1.0)
        self.assertEqual(multi.active_shape_key.name, "Explode")       # Edit Mode shows the pieces apart
        slide(0.0)
        bpy.context.view_layer.objects.active = multi
        select(multi)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            cage = sorted(round(v.co.x, 4) for v in bmesh.from_edit_mesh(multi.data).verts)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(cage, sorted(round(v.co.x, 4) for v in multi.data.vertices))

    def test_mesh_in_edit_mode_splits_once_edit_mode_is_left(self):
        multi = part("multi", (0, 0, 0), pieces=2)
        part("other", (4, 0, 0))
        before = [round(v.x, 4) for v in shown(multi)]
        bpy.context.view_layer.objects.active = multi
        select(multi)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            slide(1.0)                                     # looking at the layout while editing
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        slide(1.2)
        self.assertNotEqual([round(v.x, 4) for v in shown(multi)], before)


class ActionTests(ExplodeBase):
    def test_reset_puts_everything_back_and_removes_all_explode_data(self):
        multi, b = part("multi", (0, 0, 0), pieces=2), part("b", (4, 0, 0))
        before = shown(multi)
        slide(1.5)
        # Also give b the _explode_ignore key (like Finish used to do)
        b["_explode_ignore"] = True
        press(bpy.ops.object.explode_reset)
        self.assertEqual(self.sc.explode_factor, 0.0)
        self.assertNear(pos(multi), (0, 0, 0))
        self.assertNear(pos(b), (4, 0, 0))
        for p, q in zip(shown(multi), before):
            self.assertNear(p, q)
        self.assertIsNone(multi.data.shape_keys)
        # Reset removes ALL explode traces from all objects, including _explode_ignore
        self.assertEqual(traces(multi) + traces(b), [])
        # Reset also removes legacy scene keys
        self.assertNotIn("_explode_mid", self.sc)

    def test_reset_includes_meshes_outside_the_current_selection(self):
        multi, b = part("multi", (0, 0, 0), pieces=2), part("b", (4, 0, 0))
        before = shown(multi)
        self.sc.explode_selected_only = True
        select(multi, b)
        slide(1.0)
        select(b)
        press(bpy.ops.object.explode_reset)
        self.assertNear(pos(multi), (0, 0, 0))
        for p, q in zip(shown(multi), before):
            self.assertNear(p, q)

    def test_reset_leaves_a_fresh_copy_where_it_is(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        self.sc.explode_selected_only = True
        select(a, b)
        slide(1.0)
        dup = a.copy()                                     # carries a's rest data until the slider moves
        self.sc.collection.objects.link(dup)
        dup.location = (0, 7, 0)
        select(a, b)
        bpy.context.view_layer.update()
        press(bpy.ops.object.explode_reset)
        self.assertNear(pos(a), (0, 0, 0))
        self.assertNear(pos(dup), (0, 7, 0))

    def test_reset_handles_hidden_objects_and_ignore_keys(self):
        a, b, c = part("a", (0, 0, 0)), part("b", (2, 0, 0)), part("c", (4, 0, 0))
        slide(1.0)
        # Hide object c and give it _explode_ignore key (like Finish used to do)
        c.hide_set(True)
        c["_explode_ignore"] = True
        self.assertIn("_explode_ignore", c)
        # Select only a and b
        select(a, b)
        press(bpy.ops.object.explode_reset)
        # c should be reset even though it's hidden and has _explode_ignore
        self.assertNear(pos(c), (4, 0, 0))
        self.assertNotIn("_explode_ignore", c)
        self.assertEqual(traces(c), [])


    def test_reset_disabled_when_there_is_nothing_to_reset(self):
        a, b = part("a", (0, 0, 0)), part("b", (2, 0, 0))
        with ui():
            self.assertFalse(bpy.ops.object.explode_reset.poll())
        slide(1.0)
        with ui():
            self.assertTrue(bpy.ops.object.explode_reset.poll())
        press(bpy.ops.object.explode_reset)
        with ui():
            self.assertFalse(bpy.ops.object.explode_reset.poll())

    def test_reset_waits_for_object_mode(self):
        multi = part("multi", (0, 0, 0), pieces=2)
        part("b", (4, 0, 0))
        slide(1.0)
        bpy.context.view_layer.objects.active = multi
        select(multi)
        bpy.ops.object.mode_set(mode='EDIT')               # leaving it writes the edit cage over our shape keys
        try:
            with ui():
                self.assertFalse(bpy.ops.object.explode_reset.poll())
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')


class Recorder:
    """Stands in for a UILayout: records the operators and menus a draw() puts on screen."""

    def __init__(self):
        self.ops, self.menus = [], []

    def operator(self, idname, **kw):
        self.ops.append(idname)
        return type("Props", (), {})()

    def menu(self, idname, **kw):
        self.menus.append(idname)

    def __getattr__(self, name):                           # row(), column(), prop(), separator() ...
        return lambda *a, **kw: self


class DirectionTests(ExplodeBase):
    """Test the new explode_direction and explode_anchor features."""

    def test_nested_boxes_separate_along_x_axis(self):
        """Nested boxes (1.4 mm apart on X) should separate when direction is X."""
        outer = part("outer", (0, 0, 0))
        outer.scale = (0.24, 0.03, 0.08)
        bpy.context.view_layer.update()
        inner = part("inner", (0.0014, 0, 0))
        inner.scale = (0.239, 0.029, 0.079)
        bpy.context.view_layer.update()
        self.sc.explode_direction = 'X'
        slide(1.0)
        outer_pos = pos(outer).x
        inner_pos = pos(inner).x
        separation = abs(outer_pos - inner_pos)
        self.assertGreater(separation, 0.2, f"Boxes only {separation}m apart, should be > 0.2m")

    def test_along_axis_ordering_x(self):
        """Three cubes at x = 0, 1, 5 keep their order; each gap grows by f x the largest part size."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        c = part("c", (5, 0, 0))
        self.sc.explode_direction = 'X'
        slide(1.0)
        self.assertLess(pos(a).x, pos(b).x)
        self.assertLess(pos(b).x, pos(c).x)
        self.assertAlmostEqual(pos(b).x - pos(a).x, 1 + 1.0, places=4)
        self.assertAlmostEqual(pos(c).x - pos(b).x, 4 + 1.0, places=4)

    def test_along_axis_small_slider_moves_parts_little(self):
        """The slider is continuous along an axis too: at 0.01 no part jumps to a shared position."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        c = part("c", (5, 0, 0))
        self.sc.explode_direction = 'X'
        slide(0.01)
        for o, x in ((a, 0), (b, 1), (c, 5)):
            self.assertLess(abs(pos(o).x - x), 0.05, o.name)

    def test_size_includes_object_scale(self):
        """A part scaled 3x needs 3x the room to clear its neighbours."""
        a = part("a", (0, 0, 0))
        a.scale = (3, 1, 1)
        b = part("b", (10, 0, 0))
        bpy.context.view_layer.update()
        slide(1.0)
        self.assertAlmostEqual(a[ex.KEY_S], 3.0, places=4)
        self.assertAlmostEqual(b[ex.KEY_S], 1.0, places=4)

    def test_direction_change_relays_parts_immediately(self):
        """Changing explode_direction should immediately re-layout parts."""
        a = part("a", (0, 0, 0))
        b = part("b", (0, 1, 0))
        self.sc.explode_direction = 'X'
        slide(1.0)
        x_pos = pos(a)
        self.sc.explode_direction = 'Y'
        y_pos = pos(a)
        # Position should change when direction changes
        self.assertNotEqual(tuple(x_pos), tuple(y_pos),
                           msg="Changing direction should re-layout immediately")

    def test_anchor_change_relays_parts_immediately(self):
        """Changing explode_anchor should immediately re-layout parts."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        bpy.context.view_layer.objects.active = a
        select(a, b)
        slide(1.0)
        pos_before = pos(a)
        self.sc.explode_anchor = True
        pos_after = pos(a)
        self.assertNear(pos_after, (0, 0, 0))

    def test_anchor_keeps_active_part_in_place_along_x(self):
        """Sleeve stays, tray slides out: the active part keeps its rest position, the others keep their spacing."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        c = part("c", (5, 0, 0))
        slide(1.0)
        free = [pos(o) for o in (a, b, c)]
        bpy.context.view_layer.objects.active = b
        self.sc.explode_anchor = True
        self.assertNear(pos(b), (1, 0, 0))
        shift = free[1] - Vector((1, 0, 0))
        for o, before in zip((a, c), (free[0], free[2])):
            self.assertNear(pos(o), before - shift)

    def test_anchor_ignored_when_active_is_not_moving(self):
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        lamp = bpy.data.objects.new("lamp", None)
        bpy.context.scene.collection.objects.link(lamp)
        slide(1.0)
        free = [pos(a), pos(b)]
        bpy.context.view_layer.objects.active = lamp
        self.sc.explode_anchor = True
        self.assertNear(pos(a), free[0])
        self.assertNear(pos(b), free[1])

    def test_explode_size_data_cleared_on_reset(self):
        """_explode_size should be removed by Reset."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        self.sc.explode_direction = 'X'
        slide(1.0)
        self.assertIn("_explode_size", a)
        press(bpy.ops.object.explode_reset)
        self.assertNotIn("_explode_size", a)
        self.assertNotIn("_explode_size", b)

    def test_explode_size_data_cleared_on_reset(self):
        """_explode_size should be removed by Reset."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        self.sc.explode_direction = 'X'
        slide(1.0)
        self.assertIn("_explode_size", a)
        press(bpy.ops.object.explode_reset)
        self.assertNotIn("_explode_size", a)
        self.assertNotIn("_explode_size", b)

    def test_default_direction_is_x(self):
        """A fresh scene should have explode_direction set to 'X'."""
        self.assertEqual(self.sc.explode_direction, 'X')

    def test_direction_enum_has_only_x_y_z(self):
        """The enum property should only have X, Y, Z items (no CENTRE)."""
        rna_type = bpy.types.Scene.bl_rna
        prop = rna_type.properties['explode_direction']
        items = [item.identifier for item in prop.enum_items]
        self.assertEqual(items, ['X', 'Y', 'Z'])

    def test_reset_removes_legacy_explode_mid_key(self):
        """Reset should clean up old _explode_mid keys from older file versions."""
        a = part("a", (0, 0, 0))
        b = part("b", (1, 0, 0))
        slide(1.0)
        # Simulate a file from an older version that has _explode_mid
        self.sc["_explode_mid"] = (0.5, 0, 0)
        self.assertIn("_explode_mid", self.sc)
        press(bpy.ops.object.explode_reset)
        self.assertNotIn("_explode_mid", self.sc)


def world_pieces(o):
    """World x, y, z of each loose cube's centre as displayed (cubes of `part` hold 8 vertices each)."""
    vs = [o.matrix_world @ v for v in shown(o)]
    return [sum(vs[i:i + 8], Vector()) / 8 for i in range(0, len(vs), 8)]


class PiecesAlongAxisTests(ExplodeBase):
    """Loose pieces move along the chosen world axis, whatever the object's rotation or mirror (SDNA files keep the
    right-hand parts at scale -0.1, which used to send their pieces the wrong way)."""

    def test_pieces_do_not_move_off_the_chosen_axis(self):
        o = part("multi", (0, 0, 0), pieces=3)  # pieces side by side on X
        before = world_pieces(o)
        self.sc.explode_direction = 'Z'
        slide(2.0)
        for a, b in zip(before, world_pieces(o)):
            self.assertAlmostEqual(a.x, b.x, places=5)
            self.assertAlmostEqual(a.y, b.y, places=5)

    def test_mirrored_object_pieces_move_outward_along_world_x(self):
        o = part("right", (-4, 0, 0), pieces=2)
        o.scale = (-1, -1, -1)
        bpy.context.view_layer.update()
        before = world_pieces(o)
        slide(1.0)
        after = world_pieces(o)
        outer, inner = (0, 1) if before[0].x < before[1].x else (1, 0)
        self.assertLess(after[outer].x, before[outer].x)    # the outer piece goes further out (-X)
        self.assertGreater(after[inner].x, before[inner].x)
        for a, b in zip(before, after):
            self.assertAlmostEqual(a.y, b.y, places=5)
            self.assertAlmostEqual(a.z, b.z, places=5)

    def test_rotated_object_pieces_follow_the_world_axis(self):
        o = part("rotated", (0, 0, 0), pieces=3)
        o.rotation_euler = (0, 0, 1.5707963267948966)  # pieces now lie along world Y
        bpy.context.view_layer.update()
        before = world_pieces(o)
        self.sc.explode_direction = 'Y'
        slide(1.0)
        after = world_pieces(o)
        self.assertGreater(max(abs(a.y - b.y) for a, b in zip(before, after)), 0.5)
        for a, b in zip(before, after):
            self.assertAlmostEqual(a.x, b.x, places=5)
            self.assertAlmostEqual(a.z, b.z, places=5)

    def test_direction_change_rebuilds_the_pieces_for_the_new_axis(self):
        o = part("multi", (0, 0, 0), pieces=2)
        o.rotation_euler = (0, 1.5707963267948966, 0)  # pieces now lie along world Z
        bpy.context.view_layer.update()
        before = world_pieces(o)
        slide(1.0)
        self.assertEqual([round(p.z, 4) for p in world_pieces(o)], [round(p.z, 4) for p in before])  # X: no room
        self.sc.explode_direction = 'Z'
        self.assertEqual(o.data.shape_keys["_explode_axis"], 'Z')
        after = world_pieces(o)
        self.assertNotEqual([round(p.z, 4) for p in after], [round(p.z, 4) for p in before])
        for a, b in zip(before, after):
            self.assertAlmostEqual(a.x, b.x, places=5)

    def test_reset_removes_the_axis_note(self):
        o = part("multi", (0, 0, 0), pieces=2)
        o.data.shape_keys or o.shape_key_add(name="Basis")
        o.shape_key_add(name="Smile")  # another key keeps the shape key block alive after Reset
        slide(1.0)
        self.assertIn("_explode_axis", o.data.shape_keys)
        press(bpy.ops.object.explode_reset)
        self.assertNotIn("_explode_axis", o.data.shape_keys)


class TwinTests(ExplodeBase):
    def test_left_and_right_parts_move_together_along_z(self):
        """Temples or lenses at the same height, apart on X: one rank, same offset, so they stay a pair."""
        left, right = part("temple_left", (3, 0, 0)), part("temple_right", (-3, 0, 0))
        front = part("front", (0, 0, 2))
        self.sc.explode_direction = 'Z'
        slide(1.0)
        self.assertAlmostEqual(left.matrix_world.translation.z, right.matrix_world.translation.z, places=5)
        self.assertLess(left.matrix_world.translation.z, 0)
        self.assertGreater(front.matrix_world.translation.z, 2)

    def test_overlapping_parts_at_the_same_place_still_separate(self):
        outer, inner = part("outer", (0, 0, 0)), part("inner", (0, 0, 0))
        inner.scale = (0.5, 0.5, 0.5)
        bpy.context.view_layer.update()
        self.sc.explode_direction = 'Z'
        slide(1.0)
        self.assertNotAlmostEqual(outer.matrix_world.translation.z, inner.matrix_world.translation.z, places=3)


class PanelTests(ExplodeBase):
    def test_panel_only_has_reset_button(self):
        layout = Recorder()
        ex.draw(layout, bpy.context)
        self.assertEqual(set(layout.ops), {"object.explode_reset"})
        for idname in layout.ops:
            group, name = idname.split(".")
            getattr(getattr(bpy.ops, group), name).get_rna_type()  # raises if not registered

    def test_removed_operators_are_not_registered(self):
        # Keep, Finish, Wipe and menu are deleted; only Reset remains
        self.assertFalse(hasattr(bpy.types, "OBJECT_OT_explode_keep"))
        self.assertFalse(hasattr(bpy.types, "OBJECT_OT_explode_finish"))
        self.assertFalse(hasattr(bpy.types, "OBJECT_OT_explode_wipe"))
        self.assertFalse(hasattr(bpy.types, "VIEW3D_MT_explode"))

    def test_remove_mesh_piece_data_is_gone(self):
        # Unticking Also Split Mesh Pieces puts pieces back; Reset clears the data.
        self.assertFalse(hasattr(bpy.types, "OBJECT_OT_explode_remove_islands"))


class UndoTests(ExplodeBase):
    ACTIONS = [("explode_reset", {})]

    def test_undo_after_each_action_returns_to_the_exploded_layout(self):
        for name, props in self.ACTIONS:
            with self.subTest(action=name, **props):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                multi, b = part("multi", (0, 0, 0), pieces=2), part("b", (4, 0, 0))
                select(multi, b)
                with ui():
                    bpy.ops.ed.undo_push(message="Setup")
                slide(1.0)
                where = {o.name: pos(o) for o in (multi, b)}
                look = shown(multi)
                press(getattr(bpy.ops.object, name), **props)
                with ui():
                    bpy.ops.ed.undo()
                multi = bpy.data.objects["multi"]
                self.assertEqual(bpy.context.scene.explode_factor, 1.0)
                self.assertAt(where)
                for p, q in zip(shown(multi), look):
                    self.assertNear(p, q)
                slide(0.0)                                  # still knows where everything started
                self.assertAt({"multi": (0, 0, 0), "b": (4, 0, 0)})


class SaveReloadTests(ExplodeBase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exploded_state_survives_save_and_reload(self):
        multi, b, c = part("multi", (0, 0, 0), pieces=2), part("b", (4, 0, 0)), part("c", (0, 4, 0))
        before = shown(multi)
        self.sc.explode_selected_only = True
        select(multi, b, c)
        slide(1.25)
        where = {o.name: pos(o) for o in (multi, b, c)}
        blend = os.path.join(self.tmp, "explode.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        bpy.ops.wm.open_mainfile(filepath=blend)
        sc = bpy.context.scene
        self.assertEqual(sc.explode_factor, 1.25)
        self.assertTrue(sc.explode_selected_only)
        self.assertAt(where)
        multi = bpy.data.objects["multi"]
        self.assertAlmostEqual(explode_key(multi).value, 1.25)
        slide(0.0)
        self.assertAt({"multi": (0, 0, 0), "b": (4, 0, 0), "c": (0, 4, 0)})
        for p, q in zip(shown(multi), before):
            self.assertNear(p, q)


def setUpModule():
    ex.register()


class QaRegressionTests(ExplodeBase):
    def test_child_of_a_displaced_parent_keeps_its_real_rest(self):
        root, ref = part("root", (0, 0, 0)), part("ref", (10, 0, 0))
        child = part("child", (3, 0, 0))
        child.parent = root
        self.sc.explode_selected_only = True
        select(root, ref)
        slide(3.0)
        select(child)
        slide(2.0)
        press(bpy.ops.object.explode_reset)
        self.assertNear(pos(child), (3, 0, 0))

    def test_unmoved_part_between_moved_parts_in_a_chain_comes_back(self):
        p0, p1, p2 = part("p0", (0, 0, 0)), part("p1", (0, 0, 0)), part("p2", (0, 0, 0))
        ref = part("ref", (10, 0, 0))
        p1.parent, p2.parent = p0, p1
        p1.location, p2.location = (3, 0, 0), (3, 0, 0)
        bpy.context.view_layer.update()
        rest = {o.name: pos(o) for o in (p0, p1, p2, ref)}
        self.sc.explode_selected_only = True
        select(p0, p2, ref)
        slide(3.0)
        slide(0.0)
        for o in (p0, p1, p2, ref):
            self.assertNear(pos(o), rest[o.name])
        slide(3.0)
        press(bpy.ops.object.explode_reset)
        for o in (p0, p1, p2, ref):
            self.assertNear(pos(o), rest[o.name])

    def test_child_moved_alone_rides_its_displaced_parent_and_resets(self):
        root, ref = part("root", (0, 0, 0)), part("ref", (10, 0, 0))
        child = part("child", (3, 0, 0))
        child.parent = root
        self.sc.explode_selected_only = True
        select(root, ref)
        slide(3.0)
        parent_at = pos(root)
        select(child)
        slide(2.0)
        slide(0.0)  # the child is back at rest; its parent is still displaced, so it must ride along
        self.assertNear(pos(child) - pos(root), (3, 0, 0))
        self.assertNear(pos(root), parent_at)
        press(bpy.ops.object.explode_reset)
        self.assertNear(pos(root), (0, 0, 0))
        self.assertNear(pos(child), (3, 0, 0))

    def test_hidden_part_goes_back_with_the_slider(self):
        objs = [part("a", (0, 0, 0)), part("b", (6, 0, 0)), part("c", (12, 0, 0))]
        slide(3.0)
        objs[0].hide_set(True)
        slide(0.0)
        objs[0].hide_set(False)
        self.assertNear(pos(objs[0]), (0, 0, 0))

    def test_users_only_shape_key_survives_reset(self):
        for name in ("Smile", "Basis"):
            o = part("hinge_" + name, (0, 0, 0), pieces=2)
            o.shape_key_add(name=name, from_mix=False)
            slide(2.0)
            press(bpy.ops.object.explode_reset)
            self.assertEqual([k.name for k in o.data.shape_keys.key_blocks], [name])
            slide(0.0)

    def test_reset_clears_shape_key_edit_mode_and_basis_it_added(self):
        o = part("hinge", (0, 0, 0), pieces=2)
        slide(2.0)
        self.assertTrue(o.use_shape_key_edit_mode)
        press(bpy.ops.object.explode_reset)
        self.assertFalse(o.use_shape_key_edit_mode)
        self.assertIsNone(o.data.shape_keys)


def tearDownModule():
    ex.unregister()


if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
