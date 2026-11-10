"""The product's hierarchy and part names, and the Check Model fixes that build the tree and copy left to right."""

import os
import re

import bmesh
import bpy
from mathutils import Matrix, Vector

from .dimensions import measure

# The modeling SOP's tree. Wearer's left is +X; the front faces -Y.
TOP = ("frame", "lenses", "temples")
TREE = {
    "frame": ("front_rim", "nose_pad_left", "nose_pad_right", "nose_bridge", "hinge_frame_left", "hinge_frame_right"),
    "lenses": ("lens_left", "lens_right", "rim_left", "rim_right"),
    "temples": ("temple_left", "temple_right"),
    "temple_left": ("temple_left_outer", "temple_left_inner", "temple_tip_outer_left", "temple_tip_inner_left",
                    "hinge_temple_left", "screw_left"),
    "temple_right": ("temple_right_outer", "temple_right_inner", "temple_tip_outer_right", "temple_tip_inner_right",
                     "hinge_temple_right", "screw_right"),
}
GROUP_OF = {part: group for group, members in TREE.items() for part in members}
GROUPS = TOP + ("temple_left", "temple_right")
NAMES = TOP + tuple(GROUP_OF)
REQUIRED = TOP + ("front_rim", "lens_left", "lens_right", "temple_left", "temple_right", "temple_left_outer",
                  "temple_right_outer")
MIRROR_X = Matrix.Scale(-1, 4, (1, 0, 0))

_SIDE = re.compile(r"(?<![a-z])(left|right)(?![a-z])")


def side(name):
    m = _SIDE.search(name)
    return m.group(1) if m else None


def other_side(name):
    return _SIDE.sub(lambda m: "right" if m.group(1) == "left" else "left", name)


def product_root(context):
    roots = measure.find_roots(context.scene)
    return roots[0] if len(roots) == 1 else None


def find(root, name):
    return next((o for o in root.children_recursive if measure.base_name(o) == name), None)


def meshes_of(o):
    return [m for m in [o] + list(o.children_recursive) if m.type == "MESH"]


def world_bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return None
    return Vector(min(p[i] for p in pts) for i in range(3)), Vector(max(p[i] for p in pts) for i in range(3))


def _empty(name, parent, collection):
    o = bpy.data.objects.new(name, None)
    collection.objects.link(o)
    o.parent = parent
    return o


def _reparent(o, parent):
    world = o.matrix_world.copy()
    o.parent = parent
    o.matrix_parent_inverse = Matrix()
    o.matrix_world = world


def set_up_hierarchy(context, objects):
    """Make sure the top parent and its groups exist, and move the named parts among objects under the right group.
    Returns the root and the names it didn't know."""
    root = product_root(context)
    active = context.active_object
    if root is None and active and active.type == "EMPTY" and active.parent is None:
        root = active
    collection = root.users_collection[0] if root else context.collection
    if root is None:
        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        root = _empty(stem or "Model_name", None, collection)
    known = [o for o in objects if o is not root and measure.base_name(o) in NAMES]
    unknown = sorted(o.name for o in objects if o is not root and measure.base_name(o) not in NAMES)
    by_name = {}
    for o in known:
        by_name.setdefault(measure.base_name(o), o)
    nodes = {}
    for name in GROUPS:  # parents before children
        parent = root if name in TOP else nodes[GROUP_OF[name]]
        node = find(root, name) or by_name.get(name)
        if node is None:
            node = _empty(name, parent, collection)
        elif node.parent is not parent:
            context.view_layer.update()
            _reparent(node, parent)
        nodes[name] = node
    context.view_layer.update()
    for o in known:
        name = measure.base_name(o)
        if name not in GROUPS and o.parent is not nodes[GROUP_OF[name]]:
            _reparent(o, nodes[GROUP_OF[name]])
    context.view_layer.update()
    return root, unknown


def copy_left_to_right(context, sources):
    """Mirror each left mesh across world X onto its right twin, replacing the twin's mesh or making it."""
    root = product_root(context)
    done = []
    for src in sources:
        name = other_side(measure.base_name(src))
        me = src.data.copy()
        me.name = name
        me.transform(MIRROR_X, shape_keys=True)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)  # mirroring turns the faces inside out
        bm.to_mesh(me)
        bm.free()
        dst = (find(root, name) if root else None) or bpy.data.objects.get(name)
        if dst is not None and dst.type == "MESH":
            old, dst.data = dst.data, me
            if not old.users:
                bpy.data.meshes.remove(old)
        else:
            dst = src.copy()
            dst.data = me
            dst.name = name
            for collection in src.users_collection:
                collection.objects.link(dst)
            parent = src.parent and (bpy.data.objects.get(other_side(measure.base_name(src.parent))) or src.parent)
            if root and name in GROUP_OF:
                parent = find(root, GROUP_OF[name]) or parent
            dst.parent = parent
            dst.matrix_parent_inverse = Matrix()
            context.view_layer.update()
        dst.matrix_world = MIRROR_X @ src.matrix_world @ MIRROR_X
        done.append(dst.name)
    context.view_layer.update()
    return done
