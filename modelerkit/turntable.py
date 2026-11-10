"""Turntable: spins every 3D view around its centre to see the product from all sides. Nothing in the scene changes."""

import math

import bpy
from mathutils import Quaternion

STEP = math.radians(1.5)
INTERVAL = 1 / 30


def _spin():
    turn = Quaternion((0, 0, 1), STEP)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                view = area.spaces.active.region_3d
                view.view_rotation = turn @ view.view_rotation
                area.tag_redraw()
    return INTERVAL


def running():
    return bpy.app.timers.is_registered(_spin)


class MODELERKIT_OT_turntable(bpy.types.Operator):
    """Spin the 3D view around the product, or stop it. Only the view moves"""
    bl_idname = "modelerkit.turntable"
    bl_label = "Turntable"

    def execute(self, context):
        if running():
            bpy.app.timers.unregister(_spin)
        else:
            bpy.app.timers.register(_spin, first_interval=INTERVAL)
        return {"FINISHED"}


def draw(layout, context):
    on = running()
    layout.operator(MODELERKIT_OT_turntable.bl_idname, text="Stop Turntable" if on else "Turntable",
                    icon="PAUSE" if on else "PLAY", depress=on)


def register():
    bpy.utils.register_class(MODELERKIT_OT_turntable)


def unregister():
    if running():
        bpy.app.timers.unregister(_spin)
    bpy.utils.unregister_class(MODELERKIT_OT_turntable)
