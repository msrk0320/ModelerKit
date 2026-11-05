"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_lens_gap_blender.py
Set BLENDER_USER_RESOURCES to a scratch folder first."""
import math
import sys
import unittest
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import explode_slider, lens_gap  # noqa: E402

N = 24
RADIUS = 1.0
OFFSET = 0.0007


def make_rim(name="front_rim", ring_y=None, flip_rows=(), seam=False):
    """Open tube along Y with rows of quads. Row 2 is the loop next to the lens; UV v equals y."""
    ring_y = ring_y or (lambda i: 0.005 if i % 2 else -0.004)
    rows = [-0.3, -0.1, None, 0.1, 0.3]
    bm = bmesh.new()
    verts = []
    for y in rows:
        row = []
        for i in range(N):
            a = 2 * math.pi * i / N
            row.append(bm.verts.new((RADIUS * math.cos(a), ring_y(i) if y is None else y, RADIUS * math.sin(a))))
        verts.append(row)
    uv = bm.loops.layers.uv.new("UVMap")
    for r in range(len(rows) - 1):
        for i in range(N):
            j = (i + 1) % N
            f = bm.faces.new((verts[r][i], verts[r + 1][i], verts[r + 1][j], verts[r][j]))
            if r in flip_rows:
                f.normal_flip()
            for lp in f.loops:
                vi = next(c for row in verts for c, x in enumerate(row) if x is lp.vert)
                u = vi / N
                if seam and i == N - 1 and vi == 0:
                    u = 1.0  # last column's island ends here, so vert 0 sits on a UV seam
                lp[uv].uv = (u, lp.vert.co.y)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def make_lens(name="lens_left"):
    """Flat fan at y=0, wider than the tube so every edge crossing y=0 hits it."""
    r = RADIUS + 0.05
    vs = [(0, 0, 0)] + [(r * math.cos(2 * math.pi * i / N), 0, r * math.sin(2 * math.pi * i / N)) for i in range(N)]
    fs = [(0, 1 + i, 1 + (i + 1) % N) for i in range(N)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def ring_indices():
    return range(2 * N, 3 * N)


def state(o):
    return [tuple(v.co) for v in o.data.vertices], [tuple(p.vertices) for p in o.data.polygons]


class LensGapTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        lens_gap.register()
        bpy.context.view_layer.update()

    def tearDown(self):
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        lens_gap.unregister()

    def activate(self, o):
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.context.view_layer.update()

    def test_closes_ring_with_no_flips(self):
        rim, lens = make_rim(), make_lens()
        lens_before = state(lens)
        others = [tuple(rim.data.vertices[i].co) for i in range(N)]
        self.activate(rim)
        bpy.ops.modelerkit.close_lens_gap()
        for i in ring_indices():
            v = rim.data.vertices[i].co
            self.assertAlmostEqual(v.y, -OFFSET, places=5)
            self.assertAlmostEqual(math.hypot(v.x, v.z), RADIUS, places=5)
        self.assertEqual(state(lens), lens_before)
        self.assertEqual([tuple(rim.data.vertices[i].co) for i in range(N)], others)

    def test_second_run_changes_nothing(self):
        rim = make_rim()
        make_lens()
        self.activate(rim)
        bpy.ops.modelerkit.close_lens_gap()
        once = state(rim)[0]
        bpy.ops.modelerkit.close_lens_gap()
        for a, b in zip(once, state(rim)[0]):
            self.assertAlmostEqual((Vector(a) - Vector(b)).length, 0.0, places=5)

    def test_transformed_rim_measures_in_world_space(self):
        rim = make_rim()
        make_lens()
        parent = bpy.data.objects.new("frame", None)
        bpy.context.scene.collection.objects.link(parent)
        rim.parent = parent
        # the local mesh sits off the lens and is smaller; the parent brings it back exactly over the lens
        for v in rim.data.vertices:
            v.co = v.co * 0.5 + Vector((3, 0, 0))
        parent.matrix_world = Matrix.Scale(2.0, 4) @ Matrix.Translation((-3, 0, 0))
        self.activate(rim)
        bpy.ops.modelerkit.close_lens_gap()
        world = rim.matrix_world
        for i in ring_indices():
            p = world @ rim.data.vertices[i].co
            self.assertAlmostEqual(p.y, -OFFSET, places=4)
            self.assertAlmostEqual(math.hypot(p.x, p.z), RADIUS, places=4)

    def test_flips_survive_and_offset_leads_away_from_band(self):
        rim = make_rim(flip_rows=(0, 1))  # band in front of the lens this time: offset must go to +Y
        make_lens()
        before = state(rim)[1]
        self.activate(rim)
        bpy.ops.modelerkit.close_lens_gap()
        self.assertEqual(state(rim)[1], before)
        for i in ring_indices():
            self.assertAlmostEqual(rim.data.vertices[i].co.y, OFFSET, places=5)

    def test_uvs_follow_on_both_sides_of_a_seam(self):
        rim = make_rim(seam=True)
        make_lens()
        self.activate(rim)
        bpy.ops.modelerkit.close_lens_gap()
        uv = rim.data.uv_layers.active.data
        for lp in rim.data.loops:
            self.assertAlmostEqual(uv[lp.index].uv.y, rim.data.vertices[lp.vertex_index].co.y, places=5)

    def test_check_moves_nothing(self):
        rim = make_rim()
        make_lens()
        before = state(rim)
        self.activate(rim)
        bpy.ops.modelerkit.check_lens_gap()
        self.assertEqual(state(rim), before)

    def test_selected_loop_works_past_search_distance(self):
        rim = make_rim(ring_y=lambda i: 0.05)
        make_lens()
        self.activate(rim)
        with self.assertRaises(RuntimeError):
            bpy.ops.modelerkit.close_lens_gap()
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(rim.data)
        bm.verts.ensure_lookup_table()
        ring = {bm.verts[i] for i in ring_indices()}
        for seq in (bm.faces, bm.edges, bm.verts):
            for item in seq:
                item.select = False
        for e in bm.edges:
            e.select = e.verts[0] in ring and e.verts[1] in ring
        bmesh.update_edit_mesh(rim.data)
        bpy.ops.modelerkit.close_lens_gap()
        bpy.ops.object.mode_set(mode="OBJECT")
        for i in ring_indices():
            self.assertAlmostEqual(rim.data.vertices[i].co.y, -OFFSET, places=5)

    def test_selected_band_uses_its_edge_nearest_the_lens(self):
        rim = make_rim(ring_y=lambda i: 0.05)
        make_lens()
        self.activate(rim)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(rim.data)
        for f in bm.faces:
            f.select = f.calc_center_median().y > 0.06  # rows behind the loop
        bm.select_flush_mode()
        bmesh.update_edit_mesh(rim.data)
        bpy.ops.modelerkit.close_lens_gap()
        bpy.ops.object.mode_set(mode="OBJECT")
        for i in ring_indices():
            self.assertAlmostEqual(rim.data.vertices[i].co.y, -OFFSET, places=5)

    def test_unreachable_moves_nothing_and_selects_the_verts(self):
        rim = make_rim(ring_y=lambda i: -0.004)  # the next row stays in front of the lens, so row 1 can't reach it
        make_lens()
        self.activate(rim)
        before = state(rim)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(rim.data)
        bm.verts.ensure_lookup_table()
        row = {bm.verts[i] for i in range(N, 2 * N)}  # row 1, one row short of the lens
        for seq in (bm.faces, bm.edges, bm.verts):
            for item in seq:
                item.select = False
        for e in bm.edges:
            e.select = e.verts[0] in row and e.verts[1] in row
        bmesh.update_edit_mesh(rim.data)
        with self.assertRaises(RuntimeError):
            bpy.ops.modelerkit.close_lens_gap()
        bpy.ops.object.mode_set(mode="OBJECT")
        self.assertEqual(state(rim), before)
        self.assertEqual({v.index for v in rim.data.vertices if v.select}, set(range(N, 2 * N)))

    def test_open_ring_refused(self):
        rim = make_rim(ring_y=lambda i: 0.01 if i < N // 2 else 0.09)
        make_lens()
        self.activate(rim)
        before = state(rim)
        with self.assertRaises(RuntimeError):
            bpy.ops.modelerkit.close_lens_gap()
        self.assertEqual(state(rim), before)

    def test_shape_keys_refused(self):
        rim = make_rim()
        make_lens()
        rim.shape_key_add(name="Basis")
        self.activate(rim)
        with self.assertRaises(RuntimeError):
            bpy.ops.modelerkit.close_lens_gap()

    def test_exploded_rim_or_lens_refused(self):
        rim, lens = make_rim(), make_lens()
        self.activate(rim)
        before = state(rim)
        for part in (rim, lens):
            part[explode_slider.KEY] = (0.0, 0.0, 0.0)
            with self.assertRaisesRegex(RuntimeError, "Explode slider"):
                bpy.ops.modelerkit.close_lens_gap()
            del part[explode_slider.KEY]
        self.assertEqual(state(rim), before)

    def test_undo_puts_the_loop_back(self):
        rim = make_rim()
        make_lens()
        self.activate(rim)
        before = state(rim)
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.ed.undo_push(message="Setup")
            bpy.ops.modelerkit.close_lens_gap("EXEC_DEFAULT", True)
            self.assertNotEqual(state(bpy.data.objects["front_rim"]), before)
            bpy.ops.ed.undo()
        self.assertEqual(state(bpy.data.objects["front_rim"]), before)

    def test_no_lens_refused(self):
        rim = make_rim()
        self.activate(rim)
        with self.assertRaises(RuntimeError):
            bpy.ops.modelerkit.close_lens_gap()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], exit=True)
