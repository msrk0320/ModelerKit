"""Folded UV faces: faces whose UVs wind the other way than the rest of their island (negative signed area in a
positive island, or the reverse). They look like part of one island, but UVPackmaster splits each folded patch off
as an island of its own (SDNA-263221 front_rim: 375 folded faces became 9 extra islands). A whole island mirrored on
purpose is not folded: all its faces agree."""

import bmesh
import bpy
import numpy as np

AREA_EPS = 1e-12        # faces with no UV area are neither way round


def _uv_faces(mesh):
    """Signed UV area per polygon (shoelace over the loops) of the active UV layer."""
    uv = np.empty(len(mesh.loops) * 2)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    starts = np.empty(len(mesh.polygons), dtype=int)
    mesh.polygons.foreach_get("loop_start", starts)
    sizes = np.empty(len(mesh.polygons), dtype=int)
    mesh.polygons.foreach_get("loop_total", sizes)
    following = np.arange(1, len(uv) + 1)
    following[starts + sizes - 1] = starts
    cross = uv[:, 0] * uv[following, 1] - uv[following, 0] * uv[:, 1]
    return np.add.reduceat(cross, starts) / 2.0


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


def _islands(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        return np.array(uv_islands(bm, bm.loops.layers.uv.active))
    finally:
        bm.free()


def folded(mesh):
    """(polygon indices of folded faces, island id per polygon) of the active UV layer; ([], None) without UVs."""
    if not mesh.uv_layers.active or not mesh.polygons:
        return [], None
    area = _uv_faces(mesh)
    islands = _islands(mesh)
    out = []
    for island in np.unique(islands):
        faces = np.flatnonzero(islands == island)
        way = np.sign(area[faces].sum())
        out.extend(int(f) for f in faces if way * area[f] < -AREA_EPS)
    return sorted(out), islands


def _meshes(context):
    seen, out = set(), []
    for o in context.selected_objects:
        if o.type == "MESH" and o.data not in seen:
            seen.add(o.data)
            out.append(o)
    return out


def _select(obj, faces):
    """Select exactly these faces in Edit Mode, in the mesh and on their UVs (UV Sync Selection off needs both)."""
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active
    wanted = set(faces)
    for f in bm.faces:
        on = f.index in wanted
        f.select_set(on)
        for loop in f.loops if uv_layer else ():
            if hasattr(loop[uv_layer], "select"):       # UV-side selection; Blender 5 dropped it from BMLoopUV
                loop[uv_layer].select = on
                loop[uv_layer].select_edge = on
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


class MODELERKIT_OT_find_folded_uvs(bpy.types.Operator):
    """Select the UV faces that wind the other way than the rest of their island, which UVPackmaster splits off
    as islands of their own. Active UV map of the selected meshes"""
    bl_idname = "modelerkit.find_folded_uvs"
    bl_label = "Find Flipped UVs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode in ("OBJECT", "EDIT_MESH") and bool(_meshes(context))

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        found = {}
        for o in _meshes(context):
            folds, islands = folded(o.data)
            found[o] = (folds, islands)
        if context.view_layer.objects.active not in found:  # Edit Mode follows the active object
            context.view_layer.objects.active = next(iter(found))
        bpy.ops.object.mode_set(mode="EDIT")
        context.tool_settings.mesh_select_mode = (False, False, True)
        for o, (folds, _islands) in found.items():
            _select(o, folds)
        lines = []
        for o, (folds, islands) in found.items():
            if folds:
                lines.append("%s: %d flipped UV face(s) in %d island(s)" % (o.name, len(folds), len(set(islands[folds]))))
        if not lines:
            self.report({"INFO"}, "No flipped UV faces on the active UV map")
            return {"FINISHED"}
        self.report({"WARNING"}, "; ".join(lines) + ". Selected")
        return {"FINISHED"}


classes = (MODELERKIT_OT_find_folded_uvs,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
