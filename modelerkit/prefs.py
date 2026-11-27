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
        index = next((i for i, repo in enumerate(repos) if repo.module == parts[1]), None)
        if index is None:
            self.report({"ERROR"}, "Its repository is gone; remove it in Preferences > Get Extensions")
            return {"CANCELLED"}
        return bpy.ops.extensions.package_uninstall(repo_index=index, pkg_id=parts[2])


class MODELERKIT_OT_add_update_repository(bpy.types.Operator):
    bl_idname = "modelerkit.add_update_repository"
    bl_label = "Turn On Updates"
    bl_description = "Add the Modeler Kit repository back, so Blender offers each new version"

    @classmethod
    def poll(cls, context):
        from . import has_update_repository
        if has_update_repository():
            cls.poll_message_set("Updates are already on")
            return False
        return True

    def execute(self, context):
        from . import add_update_repository
        add_update_repository()
        return {"FINISHED"}


class MODELERKIT_AP_prefs(bpy.types.AddonPreferences):
    bl_idname = __package__

    update_repo_added: bpy.props.BoolProperty(options={"HIDDEN"})  # the repository was added once on first enable

    def draw(self, context):
        row = self.layout.row()
        row.operator(MODELERKIT_OT_add_update_repository.bl_idname, icon="URL")
        row.operator(MODELERKIT_OT_uninstall.bl_idname, icon="TRASH")


classes = (MODELERKIT_OT_uninstall, MODELERKIT_OT_add_update_repository, MODELERKIT_AP_prefs)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
