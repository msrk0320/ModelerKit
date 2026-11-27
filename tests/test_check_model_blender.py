"""Check Model: each problem is found, and its Fix clears it.
Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_check_model_blender.py"""
import sys
import unittest
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelerkit  # noqa: E402
from modelerkit import check_model, explode_slider  # noqa: E402
from tests.test_dimensions_blender import box_mesh, build, empty  # noqa: E402


def issues():
    bpy.ops.modelerkit.check_model()
    return check_model._issues


def errors():
    return [i for i in issues() if i.level == "error"]


def fix(key):
    index = next(n for n, i in enumerate(check_model._issues) if i.fix == key)
    bpy.ops.modelerkit.check_model_fix(index=index)


def clean():
    """build()'s product with the one material it lacks, and its UVs (a new map is 0-1 per face) all at 0,0."""
    root = build()
    mat = bpy.data.materials.new("Mat_" + root.name)
    for o in root.children_recursive:
        if o.type == "MESH":
            o.data.materials.append(mat)
            for loop in o.data.uv_layers[0].data:
                loop.uv = (0, 0)
    return root


def world_verts(o):
    return sorted(tuple(round(c, 4) for c in o.matrix_world @ v.co) for v in o.data.vertices)


def layout(o, u0):
    """A small square of UV space per face, side by side from u0."""
    uv = o.data.uv_layers[0].data
    for k, f in enumerate(o.data.polygons):
        for j, li in enumerate(f.loop_indices):
            uv[li].uv = (u0 + 0.06 * k + 0.05 * (j in (1, 2)), 0.1 + 0.05 * (j in (2, 3)))


class Base(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)

    def assertFound(self, key):
        found = [i for i in issues() if i.fix == key]
        self.assertTrue(found, issues())
        return found[0]

    def assertFixed(self, key):
        self.assertFound(key)
        fix(key)
        self.assertFalse([i for i in check_model._issues if i.fix == key], check_model._issues)


class CheckTests(Base):
    def test_a_clean_product_passes(self):
        clean()
        self.assertEqual(errors(), [])

    def test_no_tree_offers_set_up_hierarchy(self):
        box_mesh("front_rim", (-7, -2, 0), (7, -1, 5), None)
        self.assertFixed("hierarchy")

    def test_missing_unknown_and_misplaced_parts(self):
        clean()
        bpy.data.objects.remove(bpy.data.objects["lens_right"])
        bpy.data.objects["hinge_temple_left"].name = "hinge"
        bpy.data.objects["front_rim"].parent = bpy.data.objects["lenses"]
        texts = " | ".join(i.text for i in errors())
        self.assertIn("Missing: lens_right", texts)
        self.assertIn("Not a part name: hinge", texts)
        self.assertFixed("hierarchy")

    def test_numbered_name(self):
        clean()
        bpy.data.objects["front_rim"].name = "front_rim.001"
        self.assertFixed("drop_number")
        self.assertIn("front_rim", bpy.data.objects)

    def test_left_part_on_the_right(self):
        clean()
        bpy.data.objects["lens_left"].name = "tmp"
        bpy.data.objects["lens_right"].name = "lens_left"
        bpy.data.objects["tmp"].name = "lens_right"
        self.assertFixed("swap_side")
        lens = bpy.data.objects["lens_left"]
        self.assertGreater((lens.matrix_world @ lens.data.vertices[0].co).x, 0)

    def test_scale(self):
        clean()
        bpy.data.objects["front_rim"].scale = (1, 1, 1.5)
        self.assertFixed("apply_scale")

    def test_uv_maps_and_materials(self):
        clean()
        rim = bpy.data.objects["front_rim"].data
        rim.uv_layers.new(name="Second")
        rim.materials.append(bpy.data.materials.new("Other"))
        self.assertFixed("single_uv")
        self.assertFixed("material")

    def test_loose_ngons_and_flipped_normals(self):
        clean()
        me = bpy.data.objects["front_rim"].data
        me.vertices.add(1)
        self.assertFixed("loose")
        lens = bpy.data.objects["lens_left"].data
        lens.flip_normals()
        self.assertFixed("normals")
        ngon = box_mesh("nose_bridge", (-1, -2, 4), (1, -1, 5), bpy.data.objects["frame"])
        ngon.data.materials.append(bpy.data.materials["Mat_SKU"])
        bm = bmesh.new()
        bm.from_mesh(ngon.data)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:1], cuts=1)
        bm.to_mesh(ngon.data)
        bm.free()
        self.assertFixed("ngons")

    def test_uv_overlap_and_outside(self):
        clean()
        for name in ("lens_left", "lens_right"):  # one face each on the same square; the rest stay at 0,0
            uv = bpy.data.objects[name].data.uv_layers[0].data
            for i, corner in enumerate(((0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4))):
                uv[i].uv = corner
        overlap = [i for i in errors() if i.text.startswith("UVs overlap")]
        self.assertTrue(overlap and set(overlap[0].objects) == {"lens_left", "lens_right"}, issues())
        uv = bpy.data.objects["lens_right"].data.uv_layers[0].data
        for i in range(4):
            uv[i].uv.x += 0.5
        self.assertFalse([i for i in errors() if i.text.startswith("UVs overlap")])
        uv[0].uv = (1.5, 0.2)
        self.assertTrue([i for i in errors() if i.text.startswith("UVs outside")])
        self.assertTrue([i for i in issues() if i.text.startswith("Texel density")])

    def test_mirror_mismatch_is_a_note_and_copy_left_fixes_it(self):
        clean()
        bpy.data.objects["temple_right_outer"].data.vertices[0].co.y += 0.5
        note = self.assertFound("copy_left")
        self.assertEqual(note.level, "info")
        self.assertFixed("copy_left")

    def test_explode_data_is_found_and_reset(self):
        clean()
        bpy.data.objects["front_rim"][explode_slider.KEY] = (0.0, 0.0, 0.0)
        self.assertFixed("explode_reset")
        self.assertFalse(explode_slider.has_data())

    def test_scaled_root_is_found_and_applied_with_every_part_in_place(self):
        root = clean()
        root.scale = (1.1, 1.1, 1.1)
        bpy.context.view_layer.update()
        before = {o.name: world_verts(o) for o in root.children_recursive if o.type == "MESH"}
        self.assertIn(root.name, self.assertFound("apply_scale").objects)
        self.assertFixed("apply_scale")
        for o in [root] + list(root.children_recursive):
            self.assertEqual(tuple(round(s, 6) for s in o.scale), (1, 1, 1), o.name)
        for name, verts in before.items():
            self.assertEqual(world_verts(bpy.data.objects[name]), verts, name)

    def test_swap_side_refuses_a_name_already_taken(self):
        clean()
        bpy.data.objects["lens_left"].location.x -= 6.9  # now on the right, beside lens_right
        self.assertFound("swap_side")
        with self.assertRaisesRegex(RuntimeError, "lens_right already exists"):
            fix("swap_side")
        self.assertIn("lens_left", bpy.data.objects)
        self.assertIn("lens_right", bpy.data.objects)

    def test_mirror_and_sides_go_by_the_top_parent_away_from_the_origin(self):
        root = clean()
        root.location.x = 3
        bpy.context.view_layer.update()
        self.assertFalse([i for i in issues() if i.fix in ("copy_left", "swap_side")], issues())
        bpy.data.objects["temple_right_outer"].data.vertices[0].co.y += 0.5
        self.assertFixed("copy_left")
        self.assertFalse([i for i in errors() if i.fix == "swap_side"])

    def test_copy_left_keeps_the_right_parts_own_uvs(self):
        clean()
        left, right = bpy.data.objects["temple_left_outer"], bpy.data.objects["temple_right_outer"]
        layout(left, 0.1)
        layout(right, 0.5)
        right.data.vertices[0].co.y += 0.1
        self.assertFalse([i for i in errors() if i.text.startswith("UVs overlap")], issues())
        self.assertFixed("copy_left")
        self.assertFalse([i for i in errors() if i.text.startswith("UVs overlap")], issues())

    def test_check_changes_nothing(self):
        clean()
        bpy.data.objects["front_rim"].scale = (2, 2, 2)
        issues()
        self.assertEqual(tuple(bpy.data.objects["front_rim"].scale), (2, 2, 2))


def setUpModule():
    modelerkit.register()


def tearDownModule():
    modelerkit.unregister()


if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
