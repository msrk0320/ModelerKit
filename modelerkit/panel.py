"""The one Modeler Kit sidebar panel: every tool as a section of buttons."""

import bpy

from . import explode_slider, lock_location, sp_texture_link, uv_material


class MODELERKIT_OT_uninstall(bpy.types.Operator):
    bl_idname = "modelerkit.uninstall"
    bl_label = "Uninstall Modeler Kit"
    bl_description = "Remove the Modeler Kit add-on from Blender"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        parts = __package__.split(".")
        if parts[0] != "bl_ext":
            self.report({"ERROR"}, "Not installed as an extension; remove it in Preferences > Add-ons")
            return {"CANCELLED"}
        repos = context.preferences.extensions.repos
        index = next(i for i, repo in enumerate(repos) if repo.module == parts[1])
        return bpy.ops.extensions.package_uninstall(repo_index=index, pkg_id=parts[2])


class VIEW3D_PT_modelerkit(bpy.types.Panel):
    bl_label = "Modeler Kit"
    bl_idname = "VIEW3D_PT_modelerkit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modeler Kit"

    def draw(self, context):
        layout = self.layout
        for title, module in (("Explode", explode_slider), ("Lock", lock_location),
                              ("UV & Material Names", uv_material), ("SP Textures", sp_texture_link)):
            box = layout.box()
            box.label(text=title)
            module.draw(box, context)
        layout.operator(MODELERKIT_OT_uninstall.bl_idname, icon="TRASH")


def register():
    bpy.utils.register_class(MODELERKIT_OT_uninstall)
    bpy.utils.register_class(VIEW3D_PT_modelerkit)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_modelerkit)
    bpy.utils.unregister_class(MODELERKIT_OT_uninstall)
