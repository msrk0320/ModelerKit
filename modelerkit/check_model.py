"""Check Model: lists what QA would flag on the product, with a Fix button beside each problem it can fix."""

from collections import namedtuple

import bmesh
import bpy
import numpy as np
from bpy.app.handlers import persistent
from mathutils import Vector, kdtree

from . import parts, uv_material
from .dimensions import measure

UV_GRID = 1024        # overlap test resolution
# pixel centres sit a hair off the grid, unevenly per axis, so neither snapped UVs nor 45° diagonals put one on the edge
# two triangles share (where both would count it)
JITTER = np.array([0.0031416, 0.0027183])
TEXTURE = 2048        # Painter export size, for the texel density readout
MIRROR_TOLERANCE = 0.01  # cm: 0.1 mm

Issue = namedtuple("Issue", "level text fix objects")  # level: error or info; fix: key of FIXES or ""

_issues = None  # the last check's issues, or None before one ran


def _name_list(names, most=3):
    names = sorted(names)
    return ", ".join(names[:most]) + (" +%d" % (len(names) - most) if len(names) > most else "")


def _structure(context, root):
    issues = []
    if root is None:
        roots = measure.find_roots(context.scene)
        if roots:
            return [Issue("error", "%d top parents: %s" % (len(roots), _name_list(o.name for o in roots)), "", ())]
        return [Issue("error", "No top parent with frame, lenses and temples", "hierarchy", ())]
    tree = list(root.children_recursive)
    present = {measure.base_name(o) for o in tree}
    missing = [n for n in parts.REQUIRED if n not in present]
    if missing:
        issues.append(Issue("error", "Missing: " + _name_list(missing, 4), "", missing))
    unknown = [o.name for o in tree if measure.base_name(o) not in parts.NAMES]
    if unknown:
        issues.append(Issue("error", "Not a part name: " + _name_list(unknown), "", unknown))
    taken = {o.name for o in bpy.data.objects}
    numbered = [o.name for o in tree if o.name != measure.base_name(o) and measure.base_name(o) in parts.NAMES]
    free = [n for n in numbered if measure.base_name(bpy.data.objects[n]) not in taken]
    if free:
        issues.append(Issue("error", "Numbered name: " + _name_list(free), "drop_number", free))
    if len(free) < len(numbered):
        issues.append(Issue("error", "Duplicate name: " + _name_list(set(numbered) - set(free)), "", ()))
    misplaced = []
    for o in tree:
        name = measure.base_name(o)
        want = "" if name in parts.TOP else parts.GROUP_OF.get(name)
        got = measure.base_name(o.parent) if o.parent is not root else ""
        if want is not None and got != want:
            misplaced.append(o.name)
    if misplaced:
        issues.append(Issue("error", "In the wrong group: " + _name_list(misplaced), "hierarchy", misplaced))
    return issues


def _sides(root):
    """Parts named for one side that sit on the other. Wearer's left is +X."""
    swapped = []
    centre = root.matrix_world.translation.x
    for o in root.children_recursive:
        name_side = parts.side(measure.base_name(o))
        bounds = parts.world_bounds(parts.meshes_of(o)) if name_side else None
        if bounds:
            x = (bounds[0].x + bounds[1].x) / 2 - centre
            if (x < 0) == (name_side == "left") and abs(x) > 1e-4:
                swapped.append(o.name)
    return [Issue("error", "On the wrong side: " + _name_list(swapped), "swap_side", swapped)] if swapped else []


def _world_verts(o):
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    m = np.array(o.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def _farthest(points, others):
    tree = kdtree.KDTree(len(others))
    for i, p in enumerate(others):
        tree.insert(p, i)
    tree.balance()
    return max((tree.find(p)[2] for p in points), default=0.0)


def _mirrors(root):
    issues = []
    for left in root.children_recursive:
        if left.type != "MESH" or parts.side(measure.base_name(left)) != "left":
            continue
        right = parts.find(root, parts.other_side(measure.base_name(left)))
        if right is None or right.type != "MESH":
            continue
        a = _world_verts(left) * (-1, 1, 1)
        b = _world_verts(right)
        if len(a) != len(b):
            off = "%d vs %d verts" % (len(a), len(b))
        else:
            gap = max(_farthest(a, b), _farthest(b, a)) if len(a) else 0.0
            off = "off by %.2f mm" % (gap * measure.MM) if gap > MIRROR_TOLERANCE else ""
        if off:
            issues.append(Issue("info", "%s is not a mirror of %s (%s)" % (right.name, left.name, off), "copy_left",
                                [left.name]))
    return issues


def _transforms_and_data(root, meshes):
    issues = []
    scaled = [o.name for o in meshes if any(abs(s - 1) > 1e-4 for s in o.scale)]
    if scaled:
        issues.append(Issue("error", "Scale not applied: " + _name_list(scaled), "apply_scale", scaled))
    no_uv = [o.name for o in meshes if not o.data.uv_layers]
    if no_uv:
        issues.append(Issue("error", "No UV map: " + _name_list(no_uv), "", no_uv))
    extra = [o.name for o in meshes if o.data.uv_layers and (len(o.data.uv_layers) > 1
                                                             or o.data.uv_layers[0].name != uv_material.UV_NAME)]
    if extra:
        issues.append(Issue("error", "Not one UV map called %s: %s" % (uv_material.UV_NAME, _name_list(extra)),
                            "single_uv", extra))
    want = "Mat_" + root.name if root else None
    wrong = [o.name for o in meshes if [m.name if m else None for m in o.data.materials] != [want]]
    if root and wrong:
        issues.append(Issue("error", "Not one material %s: %s" % (want, _name_list(wrong)), "material",
                            [o.name for o in meshes]))
    return issues


def _topology(meshes):
    found = {"loose": [], "ngons": [], "normals": []}
    for o in meshes:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        if any(not v.link_edges for v in bm.verts) or any(not e.link_faces for e in bm.edges):
            found["loose"].append(o.name)
        if any(len(f.verts) > 4 for f in bm.faces):
            found["ngons"].append(o.name)
        manifold = all(e.is_manifold for e in bm.edges)
        if any(e.is_manifold and not e.is_contiguous for e in bm.edges) or (
                manifold and bm.faces and bm.calc_volume(signed=True) < 0):
            found["normals"].append(o.name)
        bm.free()
    text = {"loose": "Loose verts or edges", "ngons": "N-gons", "normals": "Flipped normals"}
    return [Issue("error", "%s: %s" % (text[k], _name_list(v)), k, v) for k, v in found.items() if v]


def _uv_triangles(o):
    me = o.data
    loops = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", loops)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)[loops].reshape(-1, 3, 2)


def _overlapping(groups):
    """Names whose UV triangles cover the same spot as another's, from a grid of UV_GRID pixel centres."""
    covered = np.zeros((UV_GRID, UV_GRID), dtype=bool)
    owner = np.full((UV_GRID, UV_GRID), -1, dtype=np.int64)
    hit = set()
    for index, (_name, tris) in enumerate(groups):
        t = tris * UV_GRID - 0.5 - JITTER  # pixel centres at whole numbers
        lo = np.maximum(np.ceil(t.min(axis=1)), 0).astype(int)
        hi = np.minimum(np.floor(t.max(axis=1)), UV_GRID - 1).astype(int)
        for i in np.nonzero((lo <= hi).all(axis=1))[0]:  # triangles too small to hold a pixel centre can't be seen
            (ax, ay), (bx, by), (cx, cy) = t[i]
            area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if not area:
                continue
            ys, xs = np.mgrid[lo[i][1]:hi[i][1] + 1, lo[i][0]:hi[i][0] + 1]
            sign = 1 if area > 0 else -1
            inside = ((sign * ((bx - ax) * (ys - ay) - (by - ay) * (xs - ax)) >= 0)
                      & (sign * ((cx - bx) * (ys - by) - (cy - by) * (xs - bx)) >= 0)
                      & (sign * ((ax - cx) * (ys - cy) - (ay - cy) * (xs - cx)) >= 0))
            ys, xs = ys[inside], xs[inside]
            again = covered[ys, xs]
            if again.any():
                hit.add(index)
                hit.update(owner[ys[again], xs[again]].tolist())
            covered[ys, xs] = True
            owner[ys, xs] = index
    return sorted(groups[i][0] for i in hit)


def _uvs(meshes):
    issues = []
    with_uv = [o for o in meshes if o.data.uv_layers.active and o.data.polygons]
    triangles = {o.name: _uv_triangles(o) for o in with_uv}
    outside = [n for n, t in triangles.items() if len(t) and (t.min() < -1e-4 or t.max() > 1 + 1e-4)]
    if outside:
        issues.append(Issue("error", "UVs outside 0-1: " + _name_list(outside), "", outside))
    by_material = {}
    for o in with_uv:
        # shortcut: a mesh counts under its first material; Check Model flags meshes with more than one anyway
        mat = o.data.materials[0].name if o.data.materials and o.data.materials[0] else ""
        by_material.setdefault(mat, []).append((o.name, triangles[o.name]))
    for mat, groups in sorted(by_material.items()):
        names = _overlapping(groups)
        if names:
            issues.append(Issue("error", "UVs overlap%s: %s" % (" in " + mat if mat else "", _name_list(names)), "",
                                names))
    density = {}
    for o in with_uv:
        co = _world_verts(o)
        verts = np.empty(len(o.data.loop_triangles) * 3, dtype=np.int64)
        o.data.loop_triangles.foreach_get("vertices", verts)
        tri = co[verts].reshape(-1, 3, 3)
        area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum() / 2
        uv = triangles[o.name]
        u, v = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
        uv_area = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]).sum() / 2
        if area > 0 and uv_area > 0:
            density[o.name] = TEXTURE * (uv_area / area) ** 0.5  # px per cm, 1 Blender unit = 1 cm
    if density:
        low, high = min(density, key=density.get), max(density, key=density.get)
        issues.append(Issue("info", "Texel density at %d: %.0f (%s) to %.0f px/cm (%s)"
                            % (TEXTURE, density[low], low, density[high], high), "", ()))
    return issues


def check(context):
    root = parts.product_root(context)
    issues = _structure(context, root)
    meshes = [o for o in (root.children_recursive if root else context.scene.objects) if o.type == "MESH"]
    if root:
        issues += _sides(root)
    issues += _transforms_and_data(root, meshes) + _topology(meshes) + _uvs(meshes)
    if root:
        issues += _mirrors(root)
    return issues


def _objects(names):
    return [bpy.data.objects[n] for n in names if n in bpy.data.objects]


def _edit_bmesh(objs, change):
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        change(bm)
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()


def _delete_loose(bm):
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_edges], context="VERTS")


def _swap_sides(context, objs):
    for o in objs:  # through a temporary name, so a swapped pair doesn't collide
        o.name = "_mk_swap_" + o.name
    for o in objs:
        o.name = parts.other_side(measure.base_name(o)[len("_mk_swap_"):])


def _run_on(op, objs):
    with bpy.context.temp_override(selected_objects=objs, selected_editable_objects=objs, active_object=objs[0],
                                   object=objs[0]):
        op()


FIXES = {
    "hierarchy": ("Set up the hierarchy and sort every named part into it",
                  lambda context, objs: parts.set_up_hierarchy(context, list(context.scene.objects))),
    "drop_number": ("Remove the .001 ending", lambda context, objs: [setattr(o, "name", measure.base_name(o))
                                                                     for o in objs]),
    "swap_side": ("Swap left and right in these names", _swap_sides),
    "copy_left": ("Replace the right part with a mirror of the left",
                  lambda context, objs: parts.copy_left_to_right(context, objs)),
    "apply_scale": ("Apply the scale", lambda context, objs: _run_on(
        lambda: bpy.ops.object.transform_apply(location=False, rotation=False, scale=True), objs)),
    "single_uv": ("Keep the active UV map, named UVMap (Single UV Map)",
                  lambda context, objs: _run_on(bpy.ops.modelerkit.single_uv_map, objs)),
    "material": ("Give every part one Mat_<top parent> material (Single Material from Root)",
                 lambda context, objs: _run_on(bpy.ops.modelerkit.name_materials_from_root, objs)),
    "loose": ("Delete the loose verts and edges", lambda context, objs: _edit_bmesh(objs, _delete_loose)),
    "ngons": ("Triangulate the n-gons", lambda context, objs: _edit_bmesh(objs, lambda bm: bmesh.ops.triangulate(
        bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY"))),
    "normals": ("Recalculate the normals outside", lambda context, objs: _edit_bmesh(
        objs, lambda bm: bmesh.ops.recalc_face_normals(bm, faces=bm.faces))),
}


class MODELERKIT_OT_check_model(bpy.types.Operator):
    """List naming, hierarchy, side, mirror, scale, UV, material and mesh problems on the product. Changes nothing"""
    bl_idname = "modelerkit.check_model"
    bl_label = "Check Model"

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Return to Object Mode first")
            return False
        return True

    def execute(self, context):
        global _issues
        _issues = check(context)
        errors = sum(i.level == "error" for i in _issues)
        self.report({"WARNING"} if errors else {"INFO"}, "%d problem(s)" % errors if errors else "All checks pass")
        return {"FINISHED"}


class MODELERKIT_OT_check_model_fix(bpy.types.Operator):
    bl_idname = "modelerkit.check_model_fix"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if _issues and properties.index < len(_issues):
            issue = _issues[properties.index]
            return "%s.\n%s" % (FIXES[issue.fix][0], ", ".join(issue.objects) or issue.text)
        return "Fix this problem"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        global _issues
        if not _issues or self.index >= len(_issues) or not _issues[self.index].fix:
            return {"CANCELLED"}
        issue = _issues[self.index]
        objs = _objects(issue.objects)
        if issue.objects and not objs:
            self.report({"ERROR"}, "Those objects are gone; press Check Model again")
            return {"CANCELLED"}
        try:
            FIXES[issue.fix][1](context, objs)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e).strip())
            return {"CANCELLED"}
        _issues = check(context)
        return {"FINISHED"}


def draw(layout, context):
    layout.operator(MODELERKIT_OT_check_model.bl_idname, icon="CHECKMARK")
    if _issues is None:
        return
    if not any(i.level == "error" for i in _issues):
        layout.label(text="All checks pass", icon="CHECKMARK")
    for index, issue in enumerate(_issues):
        row = layout.row(align=True)
        row.label(text=issue.text, icon="ERROR" if issue.level == "error" else "INFO")
        if issue.fix:
            row.operator(MODELERKIT_OT_check_model_fix.bl_idname, text="Fix").index = index


@persistent
def _forget(_dummy):
    global _issues
    _issues = None


CLASSES = (MODELERKIT_OT_check_model, MODELERKIT_OT_check_model_fix)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.app.handlers.load_post.append(_forget)


def unregister():
    bpy.app.handlers.load_post.remove(_forget)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
