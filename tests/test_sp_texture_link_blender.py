"""Run: blender --background --factory-startup --python-exit-code 1 --python tests\test_sp_texture_link_blender.py"""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modelerkit import sp_texture_link  # noqa: E402


class SpTextureLinkTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sp_texture_link.register()

    def tearDown(self):
        sp_texture_link.unregister()

    def test_unsaved_blend_with_default_folder_asks_to_save_instead_of_scanning_the_launch_folder(self):
        for op in (bpy.ops.modelerkit.import_textures, bpy.ops.modelerkit.reload_textures):
            with self.assertRaisesRegex(RuntimeError, "Save the .blend"):
                op()


    def test_packed_image_is_named_in_a_warning(self):
        folder = tempfile.mkdtemp()
        img = bpy.data.images.new("Frame_BaseColor", 4, 4)
        img.filepath_raw = os.path.join(folder, "Frame_BaseColor.png")
        img.file_format = "PNG"
        img.save()
        img.pack()
        bpy.context.scene.mk_sp_texture_folder = folder
        reports = []
        op = types.SimpleNamespace(report=lambda kind, msg: reports.append((kind, msg)))
        sp_texture_link.MODELERKIT_OT_reload.execute(op, bpy.context)
        self.assertEqual(len(reports), 1, reports)
        self.assertEqual(reports[0][0], {"WARNING"})
        self.assertIn("1 packed image(s) keep their old pixels: Frame_BaseColor", reports[0][1])

if __name__ == "__main__":
    result = unittest.main(argv=["blender"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
