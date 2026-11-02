"""One toggle that locks or unlocks Blender's own Lock Location (X/Y/Z) on the selected objects and their children."""

import bpy


def _with_children(objects):
    return set(objects).union(*(o.children_recursive for o in objects))


def _all_locked(objects):
    return bool(objects) and all(all(o.lock_location) for o in objects)


class MODELERKIT_OT_toggle_lock_location(bpy.types.Operator):
    """Lock Location on every selected object and its children, or unlock them when they are all locked already"""
    bl_idname = "modelerkit.toggle_lock_location"
    bl_label = "Lock Location"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objects = _with_children(context.selected_objects)
        lock = not _all_locked(objects)
        for o in objects:
            o.lock_location = (lock, lock, lock)
        return {"FINISHED"}


def draw(layout, context):
    locked = _all_locked(_with_children(context.selected_objects))
    layout.operator(MODELERKIT_OT_toggle_lock_location.bl_idname,
                         text="Locked" if locked else "Lock Location",
                         icon="LOCKED" if locked else "UNLOCKED", depress=locked)


classes = (MODELERKIT_OT_toggle_lock_location,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
