"""The one Modeler Kit sidebar panel: every tool as a section of buttons."""

import bpy

from . import dimensions, explode_slider, lock_location, sp_texture_link, uv_material


class VIEW3D_PT_modelerkit(bpy.types.Panel):
    bl_label = "Modeler Kit"
    bl_idname = "VIEW3D_PT_modelerkit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modeler Kit"

    def draw(self, context):
        layout = self.layout
        for title, module in (("Explode", explode_slider), ("Lock", lock_location), ("Dimensions", dimensions),
                              ("UV & Material Names", uv_material), ("SP Textures", sp_texture_link)):
            box = layout.box()
            box.label(text=title)
            module.draw(box, context)


def register():
    bpy.utils.register_class(VIEW3D_PT_modelerkit)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_modelerkit)
