"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\test_lock_location_blender.py"""
import sys
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import lock_location  # noqa: E402


def cube(name, selected):
    o = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(o)
    o.select_set(selected)
    return o


class LockLocationTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        lock_location.register()
        self.a, self.b = cube("a", True), cube("b", True)
        self.other = cube("other", False)

    def tearDown(self):
        lock_location.unregister()

    def toggle(self):
        return bpy.ops.modelerkit.toggle_lock_location()

    def test_locks_all_three_axes_of_selected_only(self):
        self.toggle()
        self.assertEqual(tuple(self.a.lock_location), (True, True, True))
        self.assertEqual(tuple(self.b.lock_location), (True, True, True))
        self.assertEqual(tuple(self.other.lock_location), (False, False, False))

    def test_second_toggle_unlocks(self):
        self.toggle()
        self.toggle()
        self.assertEqual(tuple(self.a.lock_location), (False, False, False))

    def test_mixed_selection_locks_everything_first(self):
        self.a.lock_location = (True, False, False)
        self.toggle()
        self.assertEqual(tuple(self.a.lock_location), (True, True, True))

    def test_locks_and_unlocks_the_children_of_a_selected_parent(self):
        grandchild, child = cube("grandchild", False), cube("child", False)
        child.parent, grandchild.parent = self.a, child
        self.toggle()
        self.assertEqual(tuple(grandchild.lock_location), (True, True, True))
        self.toggle()
        self.assertEqual(tuple(grandchild.lock_location), (False, False, False))

    def test_nothing_selected_is_refused(self):
        self.a.select_set(False)
        self.b.select_set(False)
        self.assertFalse(bpy.ops.modelerkit.toggle_lock_location.poll())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
