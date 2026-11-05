"""Slides the rim's edge loop next to each lens onto the lens surface, along the rim's own edges, so no sliver of
rim shows between a flipped band and the lens. All or nothing per rim: the lens, flips and rim shape never change."""

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

from . import explode_slider


class Refused(Exception):
    """The rim can't be processed; the message says why. Nothing was changed."""


def _lenses(rim):
    return [o for o in bpy.data.objects if o is not rim and o.type == "MESH" and o.name.startswith("lens_")]


def _lens_trees(lenses):
    """World-space BVH per lens sheet."""
    trees = []
    for o in lenses:
        m, d = o.matrix_world, o.data
        trees.append(BVHTree.FromPolygons([m @ v.co for v in d.vertices], [tuple(p.vertices) for p in d.polygons]))
    return trees


def _nearest_lens(trees, p):
    """(index of the closest lens, distance to it)."""
    return min(((i, t.find_nearest(p)[3]) for i, t in enumerate(trees)), key=lambda r: r[1])


def _rings(edges):
    """Connected runs of these edges, as (verts, edge indices, closed)."""
    by_vert = {}
    for e in edges:
        for v in e.verts:
            by_vert.setdefault(v, []).append(e)
    seen, rings = set(), []
    for start in by_vert:
        if start in seen:
            continue
        seen.add(start)
        verts, todo = [], [start]
        while todo:
            v = todo.pop()
            verts.append(v)
            for e in by_vert[v]:
                other = e.other_vert(v)
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
        rings.append((verts, {e.index for v in verts for e in by_vert[v]}, all(len(by_vert[v]) == 2 for v in verts)))
    return rings


def _candidate_edges(bm, matrix, trees, search, use_selection):
    """Edges the loops are looked for in: the Edit Mode selection when there is one, else whatever hugs a lens."""
    if use_selection:
        selected = {f for f in bm.faces if f.select}
        if selected:
            return [e for e in bm.edges if sum(f in selected for f in e.link_faces) == 1]
        edges = [e for e in bm.edges if e.select]
        if edges:
            return edges
    close = {v for v in bm.verts if _nearest_lens(trees, matrix @ v.co)[1] < search}
    return [e for e in bm.edges if e.verts[0] in close and e.verts[1] in close]


def _pick_rings(rings, matrix, trees):
    """The closest closed ring per lens. Stray pieces are ignored unless a lens has no closed ring at all."""
    best, open_lenses = {}, set()
    for ring in rings:
        verts, _, closed = ring
        hits = [_nearest_lens(trees, matrix @ v.co) for v in verts]
        lens = hits[0][0]
        if not closed:
            open_lenses.add(lens)
            continue
        mean = sum(h[1] for h in hits) / len(hits)
        if lens not in best or mean < best[lens][0]:
            best[lens] = (mean, ring)
    if open_lenses - set(best):
        raise Refused("The loop next to a lens isn't closed: raise Search Distance, or select the loop in Edit Mode")
    if not best:
        raise Refused("No edge loop next to a lens: raise Search Distance, or select the loop in Edit Mode")
    return [r for _, r in best.values()]


def _inward_faces(bm):
    """Faces pointing inward, going by Recalculate Outside. Works on a copy, so this rim's flips stay."""
    copy = bm.copy()
    before = [f.normal.copy() for f in copy.faces]
    bmesh.ops.recalc_face_normals(copy, faces=list(copy.faces))
    inward = {i for i, (b, f) in enumerate(zip(before, copy.faces)) if b.dot(f.normal) < 0}
    copy.free()
    return inward


def _forward_first(cross, band, matrix):
    """The two cross edges as (forward, back). Forward leads away from the band; without a band, to the frame front."""
    touching = [e for e in cross if any(f.index in band for f in e.link_faces)]
    if len(touching) == 1:
        back = touching[0]
        return (cross[0] if back is cross[1] else cross[1]), back
    v = cross[0].verts[0] if cross[0].verts[0] in cross[1].verts else cross[0].verts[1]
    # shortcut: assumes -Y is the frame front; upgrade if a job arrives facing elsewhere
    return tuple(sorted(cross, key=lambda e: (matrix @ e.other_vert(v).co).y))


def _plan_vert(v, ring_edges, band, matrix, tree, offset):
    """(cross edge to slide along, fraction of it), or None when this vert can't reach the lens."""
    cross = [e for e in v.link_edges if e.index not in ring_edges]
    if len(cross) != 2:
        return None
    start = matrix @ v.co

    def hit_along(edge):
        delta = matrix @ edge.other_vert(v).co - start
        hit = tree.ray_cast(start, delta.normalized(), delta.length)
        return (hit[3] if hit[0] is not None else None), delta.length

    forward, back = _forward_first(cross, band, matrix)
    dist, length = hit_along(forward)
    if dist is not None:
        edge, slide = forward, dist + offset
    else:
        dist, back_length = hit_along(back)
        if dist is None:
            return None
        if dist >= offset:
            edge, slide, length = back, dist - offset, back_length
        else:
            edge, slide = forward, offset - dist
    return (edge, slide / length) if slide <= length else None


def _plan(bm, matrix, trees, search, offset, use_selection):
    """(moves as (vert, edge, fraction), verts that can't reach the lens, largest gap)."""
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    bm.edges.index_update()
    edges = _candidate_edges(bm, matrix, trees, search, use_selection)
    rings = _pick_rings(_rings(edges), matrix, trees)
    band = {f.index for f in bm.faces if f.select} if use_selection else set()
    band = band or _inward_faces(bm)
    moves, failed, gap = [], [], 0.0
    for verts, ring_edges, _ in rings:
        for v in verts:
            lens, dist = _nearest_lens(trees, matrix @ v.co)
            gap = max(gap, dist)
            move = _plan_vert(v, ring_edges, band, matrix, trees[lens], offset)
            if move:
                moves.append((v, *move))
            else:
                failed.append(v)
    return moves, failed, gap


def _slide_uvs(moves, uv_layers):
    """Every UV island at a moved vert follows the slide, so a seam along the edge doesn't stretch one side."""
    for layer in uv_layers:
        new = {}
        for v, edge, t in moves:
            other = edge.other_vert(v)
            for face in edge.link_faces:
                here = next(lp for lp in face.loops if lp.vert is v)
                there = next(lp for lp in face.loops if lp.vert is other)
                old = here[layer].uv.copy()
                target = old.lerp(there[layer].uv, t)
                for lp in v.link_loops:
                    if (lp[layer].uv - old).length < 1e-5:
                        new[lp] = target
        for lp, uv in new.items():
            lp[layer].uv = uv


def _select_only(bm, verts):
    for seq in (bm.faces, bm.edges, bm.verts):
        for item in seq:
            item.select = False
    for v in verts:
        v.select = True
    bm.select_flush_mode()


def _run(op, context, apply):
    rim = context.active_object
    settings = context.scene
    if rim.name.startswith("lens_"):
        op.report({"ERROR"}, "The active object is a lens: click the rim")
        return {"CANCELLED"}
    lenses = _lenses(rim)
    # exploded parts sit away from their rest place, so a slide would close the gap against the wrong spot
    if explode_slider.exploded([rim] + lenses):
        op.report({"ERROR"}, "Move the Explode slider back to 0 first")
        return {"CANCELLED"}
    if rim.data.shape_keys:
        op.report({"ERROR"}, "%s has shape keys: remove them first" % rim.name)
        return {"CANCELLED"}
    trees = _lens_trees(lenses)
    if not trees:
        op.report({"ERROR"}, "No lens found: lens meshes must be named lens_...")
        return {"CANCELLED"}
    editing = rim.mode == "EDIT"
    if editing:
        bm = bmesh.from_edit_mesh(rim.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(rim.data)
    try:
        try:
            moves, failed, gap = _plan(bm, rim.matrix_world, trees, settings.mk_lens_gap_search,
                                       settings.mk_lens_gap_offset, editing)
        except Refused as refused:
            op.report({"ERROR"}, str(refused))
            return {"CANCELLED"}
        if failed:
            _select_only(bm, failed)
            context.tool_settings.mesh_select_mode = (True, False, False)
        elif apply:
            _slide_uvs(moves, list(bm.loops.layers.uv.values()))
            for v, edge, t in moves:
                v.co = v.co.lerp(edge.other_vert(v).co, t)
        if failed or apply:
            if editing:
                bmesh.update_edit_mesh(rim.data)
            else:
                bm.to_mesh(rim.data)
                rim.data.update()
    finally:
        if not editing:
            bm.free()
    if failed:
        op.report({"ERROR"}, "%d of %d verts can't reach the lens along their edges. Nothing moved; they are selected "
                  "(see them in Edit Mode). Fix them by hand." % (len(failed), len(failed) + len(moves)))
        return {"CANCELLED"} if apply else {"FINISHED"}
    op.report({"INFO"}, ("Closed: %d verts moved, largest gap was %.4f" if apply else
                         "Check: %d verts can reach the lens, largest gap %.4f") % (len(moves), gap))
    return {"FINISHED"}


class _RimOperator:
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = context.active_object
        return o is not None and o.type == "MESH" and o.mode in {"OBJECT", "EDIT"}


class MODELERKIT_OT_check_lens_gap(_RimOperator, bpy.types.Operator):
    """Measure the gap on the active rim and show which verts can't reach the lens. Moves nothing"""
    bl_idname = "modelerkit.check_lens_gap"
    bl_label = "Check"

    def execute(self, context):
        return _run(self, context, False)


class MODELERKIT_OT_close_lens_gap(_RimOperator, bpy.types.Operator):
    """Slide the active rim's edge loop onto each lens. In Edit Mode, the selected loop or band decides which loop"""
    bl_idname = "modelerkit.close_lens_gap"
    bl_label = "Close Gap"

    def execute(self, context):
        return _run(self, context, True)


def draw(layout, context):
    layout.prop(context.scene, "mk_lens_gap_search")
    layout.prop(context.scene, "mk_lens_gap_offset")
    row = layout.row(align=True)
    row.operator(MODELERKIT_OT_check_lens_gap.bl_idname, icon="VIEWZOOM")
    row.operator(MODELERKIT_OT_close_lens_gap.bl_idname, icon="MOD_SHRINKWRAP")


classes = (MODELERKIT_OT_check_lens_gap, MODELERKIT_OT_close_lens_gap)


def register():
    bpy.types.Scene.mk_lens_gap_search = bpy.props.FloatProperty(
        name="Search Distance", default=0.02, min=0.0, step=0.1, precision=4,
        description="How close a loop must be to a lens to be found on its own. Selecting the loop ignores this")
    bpy.types.Scene.mk_lens_gap_offset = bpy.props.FloatProperty(
        name="Offset", default=0.0007, min=0.0, step=0.01, precision=4,
        description="How far past the lens surface the loop lands. Too low can let the line return, too high shows "
                    "the band from the other side")
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.mk_lens_gap_offset
    del bpy.types.Scene.mk_lens_gap_search
