"""One UV map and SKU-named materials on the selected objects."""

import bpy


UV_NAME = "UVMap"


def _meshes(context):
    return {o.data for o in context.selected_objects if o.type == "MESH"}


def _root(obj):
    while obj.parent:
        obj = obj.parent
    return obj


class MADPLUGIN_OT_single_uv_map(bpy.types.Operator):
    """Keep only the active UV map on every selected mesh and name it UVMap"""
    bl_idname = "madplugin.single_uv_map"
    bl_label = "Single UV Map"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_meshes(context))

    def execute(self, context):
        changed = 0
        for me in _meshes(context):
            layers = me.uv_layers
            if not layers:
                continue
            keep = layers.active.name
            for name in [l.name for l in layers if l.name != keep]:
                layers.remove(layers[name])
            layers[0].name = UV_NAME
            changed += 1
        self.report({"INFO"}, f"{changed} mesh(es) now have one UV map named {UV_NAME}")
        return {"FINISHED"}


class MADPLUGIN_OT_name_materials_from_root(bpy.types.Operator):
    """Give each root's selected meshes one shared material named Mat_<root object name> (the SKU)"""
    bl_idname = "madplugin.name_materials_from_root"
    bl_label = "Single Material from Root"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        # Object Mode only: in Edit Mode the edit mesh writes its old material indices back on exit
        return context.mode == "OBJECT" and bool(_meshes(context))

    def execute(self, context):
        roots_of = {}
        for o in bpy.data.objects:
            if o.type == "MESH":
                roots_of.setdefault(o.data, set()).add(_root(o))
        # an Alt+D mesh used by several products can hold only one SKU material: leave it alone
        shared = {me for me, roots in roots_of.items() if len(roots) > 1}
        by_root = {}
        for o in context.selected_objects:
            if o.type == "MESH" and o.data not in shared:
                by_root.setdefault(_root(o), []).append(o)
        for root, objs in by_root.items():
            name = f"Mat_{root.name}"
            meshes = {o.data for o in objs}
            # the SKU's own material when it exists (renaming another onto it would give Mat_<SKU>.001); else the
            # first material on the root's meshes; a bare product gets a new one
            mat = bpy.data.materials.get(name) \
                or next((s.material for o in objs for s in o.material_slots if s.material), None) \
                or bpy.data.materials.new(name)
            if mat.name != name:
                # a material anything else still uses (other meshes, object-linked slots, curves) is copied, so
                # renaming it cannot rename another product's
                users = bpy.data.user_map(subset={mat})[mat] - meshes - set(objs)
                if users:
                    mat = mat.copy()
                mat.name = name
            for me in meshes:
                me.materials.clear()
                me.materials.append(mat)
                me.polygons.foreach_set("material_index", [0] * len(me.polygons))
                me.update()
        skipped = sorted(me.name for me in shared if any(o.data is me for o in context.selected_objects))
        if skipped:
            self.report({"WARNING"}, f"{len(by_root)} root(s) now use one material; left alone, used by several "
                                     f"products: {', '.join(skipped)}")
            return {"FINISHED"}
        self.report({"INFO"}, f"{len(by_root)} root(s) now use one material")
        return {"FINISHED"}


class VIEW3D_PT_madplugin_uv_material(bpy.types.Panel):
    bl_label = "UV & Material Names"
    bl_idname = "VIEW3D_PT_madplugin_uv_material"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Modeler Kit"
    bl_order = 7

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator(MADPLUGIN_OT_single_uv_map.bl_idname, icon="UV")
        col.operator(MADPLUGIN_OT_name_materials_from_root.bl_idname, icon="MATERIAL")


classes = (MADPLUGIN_OT_single_uv_map, MADPLUGIN_OT_name_materials_from_root, VIEW3D_PT_madplugin_uv_material)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
