"""Modeler Kit: Explode, Lock Location, UV & Material Names and SP Textures in one sidebar panel."""

from . import explode_slider, lock_location, panel, sp_texture_link, uv_material

MODULES = (explode_slider, lock_location, uv_material, sp_texture_link, panel)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
