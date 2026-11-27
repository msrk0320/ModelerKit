"""Flip Faces: faces flipped on purpose (always whole UV islands), remembered so an export can turn them back.

The face attribute FLIP_ATTR (BOOLEAN, FACE) marks faces as flipped. In the working file the marked faces ARE
flipped. unflipped() turns them back for an export and copies the original mesh data back afterwards, so the
working file isn't changed (custom normals included). The attribute name is shared with the older add-on on
purpose, so files marked there keep their marks."""

import contextlib

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty

FLIP_ATTR = "madplugin_flip"
PACK_PROP = "madplugin_unflipped_for_pack"  # on a mesh whose marked faces are turned back for UV packing


def uv_islands(bm, uv_layer):
    """Island id per face (bm.faces order). Faces join across an edge when both corners of the edge carry
    exactly the same UVs on the two sides."""
    bm.faces.index_update()
    parent = list(range(len(bm.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        faces = e.link_faces
        if len(faces) != 2:
            continue
        a, b = faces
        ua = {loop.vert: tuple(loop[uv_layer].uv) for loop in a.loops if loop.vert in e.verts}
        ub = {loop.vert: tuple(loop[uv_layer].uv) for loop in b.loops if loop.vert in e.verts}
        if ua == ub:
            parent[find(a.index)] = find(b.index)
    return [find(f.index) for f in bm.faces]


def mesh_islands(mesh):
    """Island id per polygon of the active UV layer, or None without UVs."""
    if not mesh.uv_layers.active:
        return None
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        return uv_islands(bm, bm.loops.layers.uv.active)
    finally:
        bm.free()


def flags(mesh):
    """Flag per polygon (all False when the attribute is missing). In Edit Mode the attribute's data is empty, so
    the flags come from the edit mesh."""
    if mesh.is_editmode:
        faces = bmesh.from_edit_mesh(mesh).faces
        layer = faces.layers.bool.get(FLIP_ATTR)
        return [bool(f[layer]) for f in faces] if layer else [False] * len(faces)
    attr = mesh.attributes.get(FLIP_ATTR)
    if attr is None or attr.domain != "FACE" or attr.data_type != "BOOLEAN":
        return [False] * len(mesh.polygons)
    values = np.zeros(len(mesh.polygons), dtype=bool)
    attr.data.foreach_get("value", values)
    return values.tolist()


def set_flags(mesh, values):
    attr = mesh.attributes.get(FLIP_ATTR)
    if attr is not None and (attr.domain != "FACE" or attr.data_type != "BOOLEAN"):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(FLIP_ATTR, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", np.asarray(values, dtype=bool))


def flagged(mesh):
    """Indices of marked (flipped) faces."""
    return [i for i, v in enumerate(flags(mesh)) if v]


def grow_to_islands(mesh, faces):
    """The polygons plus every other face of their UV islands (just the polygons without UVs)."""
    faces = set(faces)
    islands = mesh_islands(mesh)
    if islands is None or not faces:
        return sorted(faces)
    keys = {islands[i] for i in faces}
    return [i for i, k in enumerate(islands) if k in keys]


def whole_islands(mesh, faces):
    """True when faces form complete UV islands."""
    return set(grow_to_islands(mesh, faces)) == set(faces)


def flip_faces(mesh, faces):
    """Flip polygons like Edit Mode > Mesh > Normals > Flip: winding reversed, custom normals turned with them.
    Object Mode only."""
    faces = sorted(set(faces))
    if not faces:
        return
    custom = mesh.has_custom_normals
    if custom:
        corner = [tuple(n.vector) for n in mesh.corner_normals]
        before = {(p.index, mesh.loops[li].vertex_index): corner[li] for p in mesh.polygons for li in p.loop_indices}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in faces], flip_multires=True)
    bm.to_mesh(mesh)
    bm.free()
    if custom:
        flip = set(faces)
        normals = []
        for p in mesh.polygons:
            s = -1.0 if p.index in flip else 1.0
            for li in p.loop_indices:
                n = before[(p.index, mesh.loops[li].vertex_index)]
                normals.append((n[0] * s, n[1] * s, n[2] * s))
        mesh.normals_split_custom_set(normals)
    mesh.update()


def winding(mesh):
    """Loop vertex indices as bytes: equal when two meshes have the same faces in the same winding."""
    lv = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", lv)
    return lv.tobytes()


@contextlib.contextmanager
def unflipped(objects):
    """Marked faces in the unflipped orientation for the duration (an export); the original mesh data is
    copied back afterwards with bmesh, which keeps custom normals exact."""
    saved, seen = [], set()
    try:
        for o in objects:
            if o.type != "MESH" or o.data.name in seen:
                continue
            seen.add(o.data.name)
            faces = flagged(o.data)
            if faces:
                saved.append((o, o.data.copy()))
                flip_faces(o.data, faces)
        yield
    finally:
        for o, backup in saved:
            bm = bmesh.new()
            bm.from_mesh(backup)
            bm.to_mesh(o.data)
            bm.free()
            o.data.update()
            bpy.data.meshes.remove(backup)


def unflipped_for_packing():
    """Meshes whose marked faces are turned back for UV packing right now."""
    return [me for me in bpy.data.meshes if me.get(PACK_PROP)]


def object_names(meshes):
    """The objects using these meshes, as the artist knows them (the mesh data is often just Mesh.003)."""
    meshes = set(meshes)
    return ", ".join(sorted(o.name for o in bpy.data.objects if o.data in meshes)) or ", ".join(
        sorted(me.name for me in meshes))


def packing_block():
    """Why an export or a mark must wait while faces are turned back for UV packing; None when not."""
    meshes = unflipped_for_packing()
    if not meshes:
        return None
    return ("Marked faces are turned back for UV packing on %s. Press Re-flip after Packing first"
            % object_names(meshes))


def inverted(mesh):
    """Per polygon: does it point inward, going by Recalculate Outside (Shift+N)."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    before = [f.normal.copy() for f in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    result = [b.dot(f.normal) < 0 for b, f in zip(before, bm.faces)]
    bm.free()
    return result


def wrong_facing(mesh):
    """Polygons that need flipping so every unmarked face points outward (Shift+N) and every marked face points
    inward, which is how marked faces sit in the working file."""
    return [i for i, (inv, marked) in enumerate(zip(inverted(mesh), flags(mesh))) if inv == (not marked)]


def _objects(context):
    return [o for o in (context.objects_in_mode if context.mode == "EDIT_MESH" else context.selected_objects)
            if o.type == "MESH"]


def _poll(context):
    return context.mode in ("OBJECT", "EDIT_MESH") and any(o.type == "MESH" for o in context.selected_objects)


class MODELERKIT_OT_mark_flipped(bpy.types.Operator):
    bl_idname = "modelerkit.mark_flipped"
    bl_label = "Mark Flipped"
    bl_description = ("Flip the selected faces (grown to whole UV islands; every face in Object Mode) and remember "
                      "them, so Export for Painter can send them unflipped. Unmark flips them back")
    bl_options = {"REGISTER", "UNDO"}

    unmark: BoolProperty(name="Unmark", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        blocked = packing_block()
        if blocked:  # marking now would mix flipped and turned-back faces
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        edit = context.mode == "EDIT_MESH"
        objects = _objects(context)
        if edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        changed = 0
        try:
            for me in {o.data for o in objects}:
                faces = [p.index for p in me.polygons if p.select] if edit else list(range(len(me.polygons)))
                values = flags(me)
                target = not self.unmark
                todo = [i for i in grow_to_islands(me, faces) if values[i] != target]
                for i in todo:
                    values[i] = target
                flip_faces(me, todo)
                set_flags(me, values)
                changed += len(todo)
        finally:
            if edit:
                bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, "%s %d face(s)" % ("Unmarked" if self.unmark else "Marked", changed))
        return {"FINISHED"}


class MODELERKIT_OT_select_marked(bpy.types.Operator):
    bl_idname = "modelerkit.select_marked"
    bl_label = "Select Marked"
    bl_description = "Select the faces marked flipped on the selected meshes (switches to Edit Mode, face select)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        if context.mode != "EDIT_MESH":
            active = context.view_layer.objects.active
            if active is None or active.type != "MESH" or not active.select_get():
                context.view_layer.objects.active = next(o for o in context.selected_objects if o.type == "MESH")
            bpy.ops.object.mode_set(mode="EDIT")
        context.tool_settings.mesh_select_mode = (False, False, True)
        count = 0
        for o in _objects(context):
            bm = bmesh.from_edit_mesh(o.data)
            layer = bm.faces.layers.bool.get(FLIP_ATTR)
            for elems in (bm.verts, bm.edges, bm.faces):
                for e in elems:
                    e.select_set(False)
            if layer:
                for f in bm.faces:
                    if f[layer]:
                        f.select_set(True)
                        count += 1
            bm.select_flush_mode()
            bmesh.update_edit_mesh(o.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, "Selected %d marked face(s)" % count)
        return {"FINISHED"}


class MODELERKIT_OT_fix_normals(bpy.types.Operator):
    bl_idname = "modelerkit.fix_normals"
    bl_label = "Fix Flipped Normals"
    bl_description = ("Flip every face that points the wrong way on the selected meshes, like Alt+N > Recalculate "
                      "Outside. Marked faces stay flipped. Lenses are left alone")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def execute(self, context):
        blocked = packing_block()
        if blocked:  # turned-back faces would be read as wrong facing
            self.report({"ERROR"}, blocked)
            return {"CANCELLED"}
        edit = context.mode == "EDIT_MESH"
        objects = _objects(context)
        if edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        fixed = 0
        try:
            # a lens is an open sheet with no inside, so "outside" is a guess there
            for me in {o.data for o in objects if not o.name.lower().startswith("lens_")}:
                faces = wrong_facing(me)
                flip_faces(me, faces)
                fixed += len(faces)
        finally:
            if edit:
                bpy.ops.object.mode_set(mode="EDIT")
        self.report({"INFO"}, "Flipped %d wrong-facing face(s)" % fixed)
        return {"FINISHED"}


class MODELERKIT_OT_unflip_for_packing(bpy.types.Operator):
    bl_idname = "modelerkit.unflip_for_packing"
    bl_label = "Unflip for Packing"
    bl_description = ("Turn the marked faces of the selected meshes back (marks kept), so a UV packer sees one "
                      "winding and keeps each island whole. Press again after packing to flip them back; Export "
                      "for Painter and Mark wait until then")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode in ("OBJECT", "EDIT_MESH") and (
            bool(unflipped_for_packing()) or any(o.type == "MESH" for o in context.selected_objects))

    def execute(self, context):
        edit = context.mode == "EDIT_MESH"
        if edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            back = unflipped_for_packing()
            if back:  # Re-flip: every mesh left unflipped, selected or not
                for me in back:
                    flip_faces(me, flagged(me))
                    del me[PACK_PROP]
                self.report({"INFO"}, "Re-flipped the marked faces on %s" % object_names(back))
                return {"FINISHED"}
            meshes = {o.data for o in context.selected_objects if o.type == "MESH" and flagged(o.data)}
            if not meshes:
                self.report({"WARNING"}, "No marked faces on the selected meshes; nothing to unflip")
                return {"CANCELLED"}
            for me in meshes:
                flip_faces(me, flagged(me))
                me[PACK_PROP] = True
            self.report({"WARNING"}, "Marked faces turned back on %s: pack the UVs, then press Re-flip after "
                                     "Packing" % object_names(meshes))
            return {"FINISHED"}
        finally:
            if edit:
                bpy.ops.object.mode_set(mode="EDIT")


def draw(layout, context):
    col = layout.column(align=True)
    row = col.row(align=True)
    row.operator(MODELERKIT_OT_mark_flipped.bl_idname, text="Mark Flipped", icon="CHECKBOX_HLT")
    row.operator(MODELERKIT_OT_mark_flipped.bl_idname, text="Unmark", icon="CHECKBOX_DEHLT").unmark = True
    col.operator(MODELERKIT_OT_select_marked.bl_idname, icon="RESTRICT_SELECT_OFF")
    col.operator(MODELERKIT_OT_fix_normals.bl_idname, icon="NORMALS_FACE")
    col.separator()
    packing = unflipped_for_packing()
    if packing:
        box = col.box()
        box.label(text="Turned back for packing: %s" % object_names(packing), icon="ERROR")
        box.operator(MODELERKIT_OT_unflip_for_packing.bl_idname, text="Re-flip after Packing", icon="FILE_REFRESH")
    else:
        col.operator(MODELERKIT_OT_unflip_for_packing.bl_idname, icon="UV")


CLASSES = (MODELERKIT_OT_mark_flipped, MODELERKIT_OT_select_marked, MODELERKIT_OT_fix_normals,
           MODELERKIT_OT_unflip_for_packing)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
