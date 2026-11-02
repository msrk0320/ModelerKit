"""Modeler Kit: Explode, Lock Location, UV & Material Names and SP Textures in one sidebar tab."""

from . import explode_slider, lock_location, sp_texture_link, uv_material

MODULES = (explode_slider, lock_location, uv_material, sp_texture_link)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
