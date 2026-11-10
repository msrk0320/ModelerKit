"""Modeler Kit: Check Model, Explode, Lock Location, Dimensions, Close Lens Gap, UV & Material Names, SP Textures
and Turntable in one sidebar panel."""

import bpy

from . import (check_model, dimensions, explode_slider, lens_gap, lock_location, panel, prefs, sp_texture_link,
               turntable, uv_material)

MODULES = (explode_slider, lock_location, dimensions, lens_gap, uv_material, sp_texture_link, check_model,
           turntable, prefs, panel)


UPDATE_URL = "https://raw.githubusercontent.com/msrk0320/ModelerKit/master/dist/index.json"


def _add_update_repository():
    """Add the update repository once, so a drag-and-drop install keeps itself up to date."""
    repos = bpy.context.preferences.extensions.repos
    if not any(repo.remote_url == UPDATE_URL for repo in repos):
        bpy.ops.preferences.extension_repo_add(name="Modeler Kit", type="REMOTE", remote_url=UPDATE_URL,
                                               use_sync_on_startup=True)
    return None


def register():
    for module in MODULES:
        module.register()
    # the preferences are read-only while an add-on registers, so wait for the next idle tick
    bpy.app.timers.register(_add_update_repository, first_interval=1.0)


def unregister():
    if bpy.app.timers.is_registered(_add_update_repository):
        bpy.app.timers.unregister(_add_update_repository)
    for module in reversed(MODULES):
        module.unregister()
