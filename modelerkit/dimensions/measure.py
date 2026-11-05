"""Measures the product the way the QA card reports it, from world-space vertices. 1 Blender unit = 1 cm, exported raw
to the GLB, so scale_length is ignored. Local vertices are cached per object until the depsgraph says they changed."""

from collections import namedtuple

import bmesh
import bpy
import numpy as np
from bpy.app.handlers import persistent
from mathutils import Vector

MM = 10.0
GROUPS = {"frame", "lenses", "temples"}
PARTS = {"rim": "front_rim", "lens_left": "lens_left", "lens_right": "lens_right", "temple_left": "temple_left",
         "temple_right": "temple_right"}
SIDE_MISMATCH = 0.5  # mm between left and right before it is worth a note

Result = namedtuple("Result", "root values lens_width boxes notes error")

_result = {}     # scene name -> Result, until mark_dirty()
_verts = {}      # object session_uid -> local vertices (n, 3): a name can move to another object


def base_name(o):
    return o.name.split(".")[0]


def find_roots(scene):
    return [o for o in scene.objects if o.parent is None and GROUPS <= {base_name(c) for c in o.children}]


def _meshes(root, name):
    """Meshes at or under the object called name in the root's tree: a part may be a mesh or a group."""
    tree = list(root.children_recursive)
    node = next((o for o in tree if base_name(o) == name), None)
    return [] if node is None else [o for o in [node] + list(node.children_recursive) if o.type == "MESH"]


def _local_verts(o):
    cached = _verts.get(o.session_uid)
    if cached is not None:
        return cached
    if o.mode == "EDIT":  # the mesh datablock lags behind until Edit Mode is left
        cached = np.array([v.co[:] for v in bmesh.from_edit_mesh(o.data).verts], dtype=np.float64).reshape(-1, 3)
    else:
        cached = np.empty(len(o.data.vertices) * 3, dtype=np.float64)
        o.data.vertices.foreach_get("co", cached)
        cached = cached.reshape(-1, 3)
    _verts[o.session_uid] = cached
    return cached


def _box(objects):
    """World (min, max) of the objects' vertices, or None."""
    lows, highs = [], []
    for o in objects:
        local = _local_verts(o)
        if len(local):
            m = np.array(o.matrix_world)
            world = local @ m[:3, :3].T + m[:3, 3]
            lows.append(world.min(axis=0))
            highs.append(world.max(axis=0))
    if not lows:
        return None
    return Vector(np.min(lows, axis=0)), Vector(np.max(highs, axis=0))


def _extent(box, axis):
    return None if box is None else (box[1][axis] - box[0][axis]) * MM


def _largest(a, b):
    return max((v for v in (a, b) if v is not None), default=None)


def _measure(scene):
    roots = find_roots(scene)
    if len(roots) != 1:
        why = "No product root with frame, lenses and temples." if not roots else "%d product roots: %s." % (
            len(roots), ", ".join(o.name for o in roots))
        return Result(None, {}, None, {}, [], why)
    root = roots[0]
    boxes = {part: _box(_meshes(root, name)) for part, name in PARTS.items()}
    left, right = boxes["lens_left"], boxes["lens_right"]
    bridge = None
    if left and right:
        bridge = (max(left[0].x, right[0].x) - min(left[1].x, right[1].x)) * MM
    values = {
        "frame_width": _extent(boxes["rim"], 0),
        "bridge": bridge,
        "lens_height": _largest(_extent(left, 2), _extent(right, 2)),
        "temple_length": _largest(_extent(boxes["temple_left"], 1), _extent(boxes["temple_right"], 1)),
    }
    lens_width = _largest(_extent(left, 0), _extent(right, 0))
    return Result(root, values, lens_width, {k: v for k, v in boxes.items() if v}, _notes(root, boxes), None)


def _notes(root, boxes):
    notes = []
    if any(abs(a) > 1e-4 for a in root.rotation_euler):
        notes.append("The root is rotated, so these numbers are unreliable.")
    for label, axes, a, b in (("Lens", (0, 2), "lens_left", "lens_right"), ("Temple", (1,), "temple_left", "temple_right")):
        if boxes[a] and boxes[b] and any(abs(_extent(boxes[a], i) - _extent(boxes[b], i)) > SIDE_MISMATCH for i in axes):
            notes.append("%s sizes differ between left and right." % label)
    left, right = boxes["lens_left"], boxes["lens_right"]
    if left and right and max(left[0].x, right[0].x) <= min(left[1].x, right[1].x):
        notes.append("The lenses overlap, so there is no Bridge to measure.")
    for side in ("temple_left", "temple_right"):
        box = boxes[side]
        if box and _extent(box, 0) > _extent(box, 1):  # the temple length is its Y extent, so it must be open
            notes.append("%s looks folded, so Temple Length is unreliable." % side)
    return notes


def result(scene):
    found = _result.get(scene.name)
    if found is None:
        found = _result[scene.name] = _measure(scene)
    return found


def mark_dirty():
    """Forget measurements and cached vertices."""
    _result.clear()
    _verts.clear()


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in (window.screen.areas if window.screen else ()):
            if area.type == "VIEW_3D":
                area.tag_redraw()


@persistent
def _on_depsgraph(scene, depsgraph):
    changed = False
    for update in depsgraph.updates:
        # A deleted or relinked part only tags its collection or the scene
        if not isinstance(update.id, (bpy.types.Object, bpy.types.Collection, bpy.types.Scene)):
            continue
        changed = True
        if update.is_updated_geometry and isinstance(update.id, bpy.types.Object):
            _verts.pop(update.id.original.session_uid, None)
    if changed:
        _result.clear()
        redraw()


@persistent
def _on_reset(*_args):
    mark_dirty()


def register():
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        handlers.append(_on_reset)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        if _on_reset in handlers:
            handlers.remove(_on_reset)
    mark_dirty()
