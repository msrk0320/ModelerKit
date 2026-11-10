"""The one Modeler Kit sidebar panel: every tool as a section of buttons that folds away."""

import bpy

from . import check_model, dimensions, explode_slider, lens_gap, lock_location, parts, sp_texture_link, turntable, \
    uv_material

SECTIONS = (("Check Model", check_model), ("Parts", parts), ("Explode", explode_slider), ("Lock", lock_location),
            ("Dimensions", dimensions), ("Close Lens Gap", lens_gap), ("UV & Material Names", uv_material),
            ("SP Textures", sp_texture_link), ("Turntable", turntable))


class VIEW3D_PT_modelerkit(bpy.types.Panel):
    bl_label = "Modeler Kit"
    bl_idname = "VIEW3D_PT_modelerkit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modeler Kit"

    def draw(self, context):
        for title, module in SECTIONS:
            header, body = self.layout.panel("mk_" + module.__name__.rsplit(".", 1)[-1])
            header.label(text=title)
            if body:
                module.draw(body, context)


def register():
    bpy.utils.register_class(VIEW3D_PT_modelerkit)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_modelerkit)
