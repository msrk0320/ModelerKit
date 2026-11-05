"""The add-on's entry in Preferences: the Uninstall button lives here, not on the panel."""

import bpy


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


class MODELERKIT_AP_prefs(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        self.layout.operator(MODELERKIT_OT_uninstall.bl_idname, icon="TRASH")


classes = (MODELERKIT_OT_uninstall, MODELERKIT_AP_prefs)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
