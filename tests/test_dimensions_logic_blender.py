"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\\test_dimensions_logic_blender.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit.dimensions import logic  # noqa: E402

SPECS = {"frame_width": 140.0, "bridge": 19.0, "lens_height": 40.0, "temple_length": 140.0}
NO_FRAME = {"lens_height": 40.0, "temple_length": 140.0}


def values(frame=140.1, bridge=19.0, lens=40.3, temple=140.2):
    return {"frame_width": frame, "bridge": bridge, "lens_height": lens, "temple_length": temple}


class StatusTests(unittest.TestCase):
    def test_limits_are_inclusive_after_rounding(self):
        self.assertEqual(logic.status(143.0, 140, 3), "near")
        self.assertEqual(logic.status(143.04, 140, 3), "near")
        self.assertEqual(logic.status(143.1, 140, 3), "out")
        self.assertEqual(logic.status(136.9, 140, 3), "out")

    def test_near_band_is_ten_percent_of_tolerance(self):
        self.assertEqual(logic.status(142.6, 140, 3), "ok")
        self.assertEqual(logic.status(142.8, 140, 3), "near")
        self.assertEqual(logic.status(137.2, 140, 3), "near")

    def test_unset_and_missing(self):
        self.assertEqual(logic.status(140, 0, 3), "unset")
        self.assertEqual(logic.status(None, 140, 3), "missing")
        self.assertEqual(logic.status(-1.0, 19, 2), "missing")


class FitTests(unittest.TestCase):
    def test_no_specs(self):
        self.assertEqual(logic.fit(values(), {}).state, "none")

    def test_exact_frame_needs_nothing(self):
        got = logic.fit(values(140.04), SPECS)
        self.assertEqual((got.state, got.factor), ("ok", None))

    def test_frame_a_little_off_still_fits(self):
        got = logic.fit(values(138.5), SPECS)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 140 / 138.5)

    def test_scale_aims_at_the_exact_frame_width(self):
        got = logic.fit(values(133.0, 18.0, 38.2, 134.0), SPECS)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 140 / 133)
        self.assertAlmostEqual(got.after["frame_width"], 140.0)
        self.assertAlmostEqual(got.after["lens_height"], 38.2 * 140 / 133)

    def test_frame_lands_exact_even_when_lens_goes_out(self):
        got = logic.fit(values(135.0, 19.0, 42.0, 140.0), SPECS)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 140 / 135)
        found = logic.statuses(got.after, SPECS)
        self.assertEqual((found["frame_width"], found["lens_height"]), ("ok", "out"))

    def test_without_frame_spec_stays_closest_to_one(self):
        specs = {"lens_height": 40.0}
        got = logic.fit(values(lens=46.0), specs)
        self.assertAlmostEqual(got.factor, 43 / 46)

    def test_conflict_without_frame_spec_names_the_pair(self):
        got = logic.fit(values(lens=48.0), NO_FRAME)
        self.assertEqual((got.state, got.factor), ("conflict", None))
        self.assertEqual(set(got.conflict), {"temple_length", "lens_height"})

    def test_metre_scale_file_gets_a_visible_100x(self):
        got = logic.fit(values(1.401, 0.19, 0.40, 1.40), SPECS)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 140 / 1.401)

    def test_zero_bridge_is_ignored(self):
        got = logic.fit(values(133.0, 0.0, 38.2, 134.0), SPECS)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 140 / 133)

    def test_fit_lands_in_range_with_a_spec_of_two_decimals(self):
        # Without a frame spec the fit moves as little as it can, so it lands exactly on the limit
        specs = {"lens_height": 30.25}
        v = values(lens=34.0)
        got = logic.fit(v, specs)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor * 34.0, 33.2)
        after = {k: x * got.factor for k, x in v.items()}
        self.assertNotIn("out", logic.statuses(after, specs).values())

    def test_only_missing_values_is_nothing_to_do(self):
        self.assertEqual(logic.fit(dict.fromkeys(logic.KEYS), SPECS).state, "none")


class ExactFrameTests(unittest.TestCase):
    def test_only_the_frame_must_round_to_its_spec(self):
        found = logic.statuses(values(140.1, 20.5, 42.0, 131.0), SPECS)
        self.assertEqual(found, {"frame_width": "out", "bridge": "ok", "lens_height": "ok", "temple_length": "ok"})
        self.assertEqual(logic.statuses(values(140.04), SPECS)["frame_width"], "ok")

    def test_right_proportions_fit_all_four(self):
        v = values(133.0, 18.05, 38.0, 133.0)
        got = logic.fit(v, SPECS)
        self.assertEqual(got.state, "fit")
        self.assertEqual(set(logic.statuses(got.after, SPECS).values()), {"ok"})

    def test_spec_text_has_no_range_for_the_frame(self):
        self.assertEqual(logic.spec_text("frame_width", 140.0), "spec 140")
        self.assertEqual(logic.spec_text("bridge", 19.0), "spec 19 ±2")
        self.assertEqual(logic.spec_text("frame_width", 140.0, False), "spec 140 ±3")


class FrameRangeTests(unittest.TestCase):
    """Exact Frame Fit off: Frame Width gets its ±3 too."""

    def test_frame_in_range_needs_nothing(self):
        self.assertEqual(logic.fit(values(138.5), SPECS, False).state, "ok")
        self.assertEqual(logic.statuses(values(138.5), SPECS, exact_frame=False)["frame_width"], "ok")

    def test_factor_aims_at_the_frame_inside_the_overlap(self):
        # Frame alone wants 140/135, but lens height 42 caps the factor at 43/42
        got = logic.fit(values(135.0, 19.0, 42.0, 140.0), SPECS, False)
        self.assertEqual(got.state, "fit")
        self.assertAlmostEqual(got.factor, 43 / 42)

    def test_conflict_names_the_frame(self):
        got = logic.fit(values(lens=48.0), SPECS, False)
        self.assertEqual(got.state, "conflict")
        self.assertEqual(set(got.conflict), {"frame_width", "lens_height"})


class StatusesTests(unittest.TestCase):
    def test_in_range_conflict_member_turns_amber(self):
        v = values(lens=48.0)
        got = logic.statuses(v, NO_FRAME, logic.fit(v, NO_FRAME).conflict)
        self.assertEqual(got["temple_length"], "near")
        self.assertEqual(got["lens_height"], "out")
        self.assertEqual(got["bridge"], "unset")

    def test_unset_specs_stay_unset(self):
        self.assertEqual(logic.statuses(values(), {})["frame_width"], "unset")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
