"""Run: set BLENDER_USER_RESOURCES to a scratch folder, then
blender --background --factory-startup --python-exit-code 1 --python tests\\test_update_repo_blender.py
It adds a repository to the preferences, so it skips itself without its own profile."""
import os
import sys
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modelerkit  # noqa: E402
from modelerkit import prefs  # noqa: E402


class UpdateRepositoryTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get("BLENDER_USER_RESOURCES"):
            self.skipTest("needs BLENDER_USER_RESOURCES, so the real preferences stay untouched")

    def ours(self):
        return [r for r in bpy.context.preferences.extensions.repos if r.remote_url == modelerkit.UPDATE_URL]

    def test_adds_the_repository_once_with_sync_on_start(self):
        modelerkit._add_update_repository()
        modelerkit._add_update_repository()
        repos = self.ours()
        self.assertEqual(len(repos), 1)
        self.assertTrue(repos[0].use_sync_on_startup)

    def test_turn_on_updates_adds_it_back(self):
        modelerkit._add_update_repository()
        index = next(i for i, r in enumerate(bpy.context.preferences.extensions.repos)
                     if r.remote_url == modelerkit.UPDATE_URL)
        bpy.ops.preferences.extension_repo_remove(index=index)
        self.assertEqual(self.ours(), [])
        self.assertTrue(bpy.ops.modelerkit.add_update_repository.poll())
        bpy.ops.modelerkit.add_update_repository()
        self.assertEqual(len(self.ours()), 1)
        self.assertFalse(bpy.ops.modelerkit.add_update_repository.poll())


def setUpModule():
    bpy.utils.register_class(prefs.MODELERKIT_OT_add_update_repository)


def tearDownModule():
    bpy.utils.unregister_class(prefs.MODELERKIT_OT_add_update_repository)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
