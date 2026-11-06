"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_dimensions_blender.py"""
import sys
import unittest
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import dimensions, explode_slider  # noqa: E402
from modelerkit.dimensions import logic, measure, overlay, ui  # noqa: E402

SPEC_LINE = "Lens Height 40mm Bridge Width 19mm Temple Length 140mm Frame Width 140mm"


def box_mesh(name, low, high, parent):
    """A mesh with the corners of the world box low..high, under parent."""
    corners = [(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(corners, [], faces)
    me.uv_layers.new(name="UVMap")
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.parent = parent
    return o


def empty(name, parent=None):
    o = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(o)
    o.parent = parent
    return o


def build(lens_left="lens_left", root_name="SKU"):
    """Frame 14.0 wide (140 mm), lenses 5.0 wide and 4.0 tall, 1.9 apart, temples 14.0 long."""
    root = empty(root_name)
    frame, lenses, temples = empty("frame", root), empty("lenses", root), empty("temples", root)
    box_mesh("front_rim", (-7, -2, 0), (7, -1, 5), frame)
    box_mesh("nose_pad_left", (-9, -3, -1), (9, -2, 0), frame)
    box_mesh(lens_left, (0.95, -1.8, 0.5), (5.95, -1.2, 4.5), lenses)
    box_mesh("lens_right", (-5.95, -1.8, 0.5), (-0.95, -1.2, 4.5), lenses)
    left, right = empty("temple_left", temples), empty("temple_right", temples)
    box_mesh("temple_left_outer", (6, -1, 3), (6.5, 12, 4), left)
    box_mesh("hinge_temple_left", (6, -2, 3), (6.5, -1, 4), left)
    box_mesh("temple_right_outer", (-6.5, -1, 3), (-6, 12, 4), right)
    box_mesh("hinge_temple_right", (-6.5, -2, 3), (-6, -1, 4), right)
    bpy.context.view_layer.update()
    measure.mark_dirty()
    return root


class Base(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        dimensions.register()
        self.scene = bpy.context.scene
        self.props = self.scene.mk_dimensions

    def tearDown(self):
        dimensions.unregister()

    def values(self):
        return measure.result(self.scene).values

    def assertMm(self, got, expected):
        self.assertAlmostEqual(got, expected, places=3)

    def refresh(self):
        bpy.context.view_layer.update()
        measure.mark_dirty()


class MeasureTests(Base):
    def test_definitions(self):
        build()
        got = self.values()
        self.assertMm(got["frame_width"], 140.0)
        self.assertMm(got["bridge"], 19.0)
        self.assertMm(got["lens_height"], 40.0)
        self.assertMm(got["temple_length"], 140.0)
        self.assertMm(measure.result(self.scene).lens_width, 50.0)

    def test_duplicate_suffix_still_counts(self):
        build(lens_left="lens_left.001")
        self.assertMm(self.values()["bridge"], 19.0)

    def test_root_scale_counts(self):
        build().scale = (0.1, 0.1, 0.1)
        self.refresh()
        self.assertMm(self.values()["frame_width"], 14.0)

    def test_scale_length_is_ignored(self):
        build()
        self.scene.unit_settings.scale_length = 0.01
        measure.mark_dirty()
        self.assertMm(self.values()["frame_width"], 140.0)

    def test_stray_mesh_outside_the_root_is_ignored(self):
        build()
        box_mesh("front_rim.001", (-50, 0, 0), (50, 1, 1), None)
        self.refresh()
        self.assertMm(self.values()["frame_width"], 140.0)

    def test_missing_part_reads_none(self):
        build()
        bpy.data.objects.remove(bpy.data.objects["lens_right"])
        measure.mark_dirty()
        got = self.values()
        self.assertIsNone(got["bridge"])
        self.assertMm(got["lens_height"], 40.0)

    def test_no_root_and_two_roots_explain_themselves(self):
        self.assertIn("No product root", measure.result(self.scene).error)
        build(), build(root_name="SKU2")
        measure.mark_dirty()
        self.assertIn("2 product roots", measure.result(self.scene).error)

    def test_rotated_root_folded_temple_and_mismatch_add_notes(self):
        root = build()
        self.assertEqual(measure.result(self.scene).notes, [])
        root.rotation_euler.z = 0.2
        self.refresh()
        self.assertTrue(any("rotated" in n for n in measure.result(self.scene).notes))
        root.rotation_euler.z = 0.0
        # Fold the left temple across the front, and make the right lens 1 mm taller
        bpy.data.objects["temple_left"].rotation_euler.z = 1.5708
        bpy.data.objects["lens_right"].data.vertices[0].co.z -= 0.1
        self.refresh()
        notes = measure.result(self.scene).notes
        self.assertTrue(any("temple_left looks folded" in n for n in notes), notes)
        self.assertTrue(any("Lens sizes differ" in n for n in notes), notes)


class LiveUpdateTests(Base):
    def test_moving_a_part_updates_through_the_depsgraph(self):
        build()
        self.assertMm(self.values()["frame_width"], 140.0)
        bpy.data.objects["front_rim"].scale.x = 1.1
        bpy.context.view_layer.update()
        self.assertMm(self.values()["frame_width"], 154.0)

    def test_edited_mesh_updates_after_geometry_tag(self):
        build()
        self.assertMm(self.values()["frame_width"], 140.0)
        rim = bpy.data.objects["front_rim"]
        for v in rim.data.vertices:
            v.co.x *= 2
        rim.data.update()
        bpy.context.view_layer.update()
        self.assertMm(self.values()["frame_width"], 280.0)

    def test_edit_mode_reads_the_live_mesh(self):
        build()
        rim = bpy.data.objects["front_rim"]
        bpy.context.view_layer.objects.active = rim
        rim.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(rim.data)
        for v in bm.verts:
            v.co.x *= 2
        bmesh.update_edit_mesh(rim.data)
        measure.mark_dirty()
        self.assertMm(self.values()["frame_width"], 280.0)
        bpy.ops.object.mode_set(mode="OBJECT")

    def test_deleting_a_part_updates_through_the_depsgraph(self):
        build()
        self.assertIsNotNone(self.values()["frame_width"])
        bpy.data.objects.remove(bpy.data.objects["front_rim"])
        bpy.context.view_layer.update()
        self.assertIsNone(self.values()["frame_width"])

    def test_name_moved_to_another_object_reads_the_new_mesh(self):
        build()
        self.assertMm(self.values()["frame_width"], 140.0)
        old = bpy.data.objects["front_rim"]
        new = box_mesh("new_rim", (-8, -2, 0), (8, -1, 5), old.parent)
        old.name = "old_rim"
        new.name = "front_rim"
        bpy.context.view_layer.update()
        measure._result.clear()
        self.assertMm(self.values()["frame_width"], 160.0)

    def test_overlapping_lenses_say_so(self):
        build()
        bpy.data.objects["lens_left"].location.x = -3.0
        self.refresh()
        self.assertTrue(any("lenses overlap" in n for n in measure.result(self.scene).notes))

    def test_undo_or_load_forgets_everything(self):
        build()
        self.values()
        measure._on_reset()
        self.assertEqual((measure._result, measure._verts), ({}, {}))


class PasteTests(Base):
    def test_paste_fills_the_fields_and_clears_the_box(self):
        self.props.paste = SPEC_LINE
        self.assertEqual(logic.specs_of(self.props),
                         {"frame_width": 140.0, "bridge": 19.0, "lens_height": 40.0, "temple_length": 140.0})
        self.assertEqual(self.props.paste, "")

    def test_junk_stays_in_the_box_and_changes_nothing(self):
        self.props.bridge = 18.0
        self.props.paste = "not a measurement"
        self.assertEqual(self.props.paste, "not a measurement")
        self.assertEqual(self.props.bridge, 18.0)

    def test_partial_line_only_changes_what_it_names(self):
        self.props.bridge = 18.0
        self.props.paste = "Frame Width 142mm"
        self.assertEqual((self.props.frame_width, self.props.bridge), (142.0, 18.0))


class OverlayTests(Base):
    def items(self):
        got = overlay.geometry(measure.result(self.scene), logic.specs_of(self.props))
        return {i.key: i for i in got}

    def test_frame_line_spans_the_rim_above_it(self):
        build()
        self.props.paste = SPEC_LINE
        line = self.items()["frame_width"].lines[0]
        self.assertAlmostEqual(line[0].x, -7.0, places=3)
        self.assertAlmostEqual(line[1].x, 7.0, places=3)
        self.assertGreater(line[0].z, 5.0)

    def test_in_range_has_no_outline(self):
        build()
        self.props.paste = SPEC_LINE
        self.assertEqual(self.items()["frame_width"].outlines, [])
        self.assertEqual(self.items()["frame_width"].value_text, "140.0")
        self.assertEqual(self.items()["frame_width"].spec_text, "spec 140")
        self.assertEqual(self.items()["bridge"].spec_text, "spec 19 ±2")

    def test_out_of_range_outlines_its_part(self):
        build()
        self.props.paste = "Frame Width 150mm"
        item = self.items()["frame_width"]
        self.assertEqual(item.status, "out")
        self.assertEqual(len(item.outlines), 12)

    def test_conflict_outlines_both_members(self):
        build()
        self.props.paste = "Temple Length 140mm Lens Height 30mm"
        items = self.items()
        self.assertEqual((items["temple_length"].status, items["lens_height"].status), ("near", "out"))
        self.assertEqual(len(items["temple_length"].outlines), 24)  # both temples
        self.assertEqual(len(items["lens_height"].outlines), 24)  # both lenses

    def test_no_spec_is_grey_without_spec_text(self):
        build()
        item = self.items()["bridge"]
        self.assertEqual((item.status, item.spec_text), ("unset", ""))

    def test_missing_part_or_root_draws_nothing(self):
        self.assertEqual(self.items(), {})
        build()
        bpy.data.objects.remove(bpy.data.objects["lens_left"])
        measure.mark_dirty()
        self.assertNotIn("bridge", self.items())
        self.assertIn("frame_width", self.items())


class IconTests(unittest.TestCase):
    def test_status_icons_exist_in_this_blender(self):
        valid = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        for icon in ui.STATUS_ICON.values():
            self.assertIn(icon, valid)


class LabelTests(unittest.TestCase):
    def test_goes_above_a_line_with_ticks_below_it(self):
        self.assertEqual(overlay.place_label((100, 100), (0, 1), (40, 20), 5, []), (80, 105))

    def test_goes_outward_beside_a_vertical_line(self):
        self.assertEqual(overlay.place_label((100, 100), (1, 0), (40, 20), 5, []), (105, 90))
        self.assertEqual(overlay.place_label((100, 100), (-1, 0), (40, 20), 5, []), (55, 90))

    def test_moves_up_past_labels_already_placed(self):
        placed = []
        first = overlay.place_label((100, 100), (0, 1), (40, 20), 5, placed)
        second = overlay.place_label((100, 104), (0, 1), (40, 20), 5, placed)
        self.assertGreaterEqual(second[1], first[1] + 20)
        third = overlay.place_label((100, 100), (0, 1), (40, 20), 5, placed)
        self.assertGreaterEqual(third[1], second[1] + 20)


class ExactFrameTests(Base):
    def setUp(self):
        super().setUp()
        build()

    def test_overlay_drops_the_tolerance_and_outlines_a_small_miss(self):
        self.props.paste = "Frame Width 141mm"
        got = overlay.geometry(measure.result(self.scene), logic.specs_of(self.props))
        item = next(i for i in got if i.key == "frame_width")
        self.assertEqual((item.status, item.spec_text, len(item.outlines)), ("out", "spec 141", 12))

    def test_fit_makes_the_value_exact(self):
        self.props.paste = "Frame Width 141mm"
        self.assertEqual(bpy.ops.modelerkit.dimensions_fit(), {"FINISHED"})
        self.assertMm(self.values()["frame_width"], 141.0)

    def test_fit_makes_the_frame_exact_and_leaves_lens_out(self):
        self.props.paste = "Frame Width 141mm Lens Height 37mm"
        self.assertEqual(bpy.ops.modelerkit.dimensions_fit(), {"FINISHED"})
        self.assertMm(self.values()["frame_width"], 141.0)
        self.assertEqual(logic.statuses(self.values(), logic.specs_of(self.props))["lens_height"], "out")


class FitTests(Base):
    def fit(self):
        return bpy.ops.modelerkit.dimensions_fit()

    def test_undo_puts_the_scale_back(self):
        build()
        self.props.paste = "Frame Width 150mm"
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.ed.undo_push(message="Setup")
            bpy.ops.modelerkit.dimensions_fit("EXEC_DEFAULT", True)
            self.assertNotEqual(bpy.data.objects["SKU"].scale.x, 1.0)
            bpy.ops.ed.undo()
        self.assertEqual(bpy.data.objects["SKU"].scale.x, 1.0)

    def test_scales_only_the_root_into_range(self):
        root = build()
        root.location = (0.0, 1.0, 0.0)
        self.refresh()
        self.props.paste = "Frame Width 150mm"
        rim = bpy.data.objects["front_rim"]
        before = [v.co.copy() for v in rim.data.vertices]
        uvs = [d.uv.copy() for d in rim.data.uv_layers[0].data]
        self.assertEqual(self.fit(), {"FINISHED"})
        factor = 150 / 140
        self.assertAlmostEqual(root.scale.x, factor, places=5)
        self.assertAlmostEqual(root.location.y, factor, places=5)
        self.assertEqual(tuple(rim.scale), (1.0, 1.0, 1.0))
        self.assertEqual([v.co.copy() for v in rim.data.vertices], before)
        self.assertEqual([d.uv.copy() for d in rim.data.uv_layers[0].data], uvs)
        self.assertMm(self.values()["frame_width"], 150.0)

    def test_every_measurement_scales_alike(self):
        build()
        self.props.paste = "Frame Width 150mm"
        self.fit()
        got = self.values()
        self.assertMm(got["bridge"], 19 * 150 / 140)
        self.assertMm(got["lens_height"], 40 * 150 / 140)

    def test_refuses_with_explode_data(self):
        build()
        self.props.paste = "Frame Width 150mm"
        bpy.data.objects["front_rim"][explode_slider.KEY] = (0.0, 0.0, 0.0)
        with self.assertRaisesRegex(RuntimeError, "Explode"):
            self.fit()
        self.assertEqual(bpy.data.objects["SKU"].scale.x, 1.0)

    def test_refuses_on_a_conflict(self):
        build()
        self.props.paste = "Temple Length 140mm Lens Height 30mm"
        with self.assertRaisesRegex(RuntimeError, "No single scale"):
            self.fit()
        self.assertEqual(bpy.data.objects["SKU"].scale.x, 1.0)

    def test_refuses_when_already_in_range(self):
        build()
        self.props.paste = SPEC_LINE
        with self.assertRaisesRegex(RuntimeError, "Nothing to fit"):
            self.fit()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
