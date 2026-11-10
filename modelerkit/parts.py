"""Parts: the product's hierarchy and part names, Copy Left to Right, and the Fold Temples slider."""

import os
import re

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import explode_slider
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
FOLD_BASIS = "_mk_fold_basis"  # the temple's local matrix before folding
FOLD_PIVOT = "_mk_fold_pivot"  # the hinge, in the temple's parent space, so Fit to Spec scaling the root keeps it valid

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


def _left_sources(context):
    o = context.active_object
    if o is None:
        return []
    return [m for m in meshes_of(o) if side(measure.base_name(m)) == "left"]


class MODELERKIT_OT_rename_part(bpy.types.Operator):
    """Give the active object one of the part names"""
    bl_idname = "modelerkit.rename_part"
    bl_label = "Rename Part"
    bl_property = "part"
    bl_options = {"REGISTER", "UNDO"}

    part: bpy.props.EnumProperty(name="Part", items=[(n, n, "") for n in NAMES])

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        o = context.active_object
        o.name = self.part
        if o.name != self.part:
            self.report({"WARNING"}, "Another object is already called %s, so this one is %s" % (self.part, o.name))
        return {"FINISHED"}


class MODELERKIT_OT_copy_left_to_right(bpy.types.Operator):
    """Mirror the active left part (and the left parts under it) across X onto the right side, replacing the right
    part's mesh. The UVs are copied too, so the two sides share UV space"""
    bl_idname = "modelerkit.copy_left_to_right"
    bl_label = "Copy Left to Right"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Return to Object Mode first")
            return False
        if not _left_sources(context):
            cls.poll_message_set("Click a _left part")
            return False
        return True

    def execute(self, context):
        sources = _left_sources(context)
        keyed = [o.name for o in sources if o.data.shape_keys]
        if keyed:
            self.report({"ERROR"}, "Remove the shape keys first (Explode > Reset if they are Explode's): %s"
                        % ", ".join(keyed))
            return {"CANCELLED"}
        done = copy_left_to_right(context, sources)
        self.report({"INFO"}, "Mirrored onto %s" % ", ".join(done))
        return {"FINISHED"}


def folded(scene):
    return any(FOLD_BASIS in o for o in scene.objects)


def _temples(context):
    root = product_root(context)
    return [t for t in (find(root, "temple_left"), find(root, "temple_right")) if t] if root else []


def update_fold(scene, context):
    angle = scene.mk_temple_fold
    for t in _temples(context):
        if FOLD_BASIS not in t:
            if not angle:
                continue
            bounds = world_bounds(meshes_of(t))
            if bounds is None:
                continue
            lo, hi = bounds
            # shortcut: the hinge is taken as the temple's front outer corner; use the real hinge if folds look off
            hinge = Vector((hi.x if side(measure.base_name(t)) == "left" else lo.x, lo.y, (lo.z + hi.z) / 2))
            parent_space = (t.parent.matrix_world @ t.matrix_parent_inverse).inverted() if t.parent else Matrix()
            t[FOLD_BASIS] = [v for row in t.matrix_basis for v in row]
            t[FOLD_PIVOT] = tuple(parent_space @ hinge)
        basis = Matrix([t[FOLD_BASIS][i:i + 4] for i in range(0, 16, 4)])
        pivot = Vector(t[FOLD_PIVOT])
        turn = angle if side(measure.base_name(t)) == "left" else -angle  # both tips swing in behind the lenses
        t.matrix_basis = Matrix.Translation(pivot) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Translation(-pivot) @ basis
        if not angle:
            del t[FOLD_BASIS], t[FOLD_PIVOT]
    context.view_layer.update()


def draw(layout, context):
    col = layout.column(align=True)
    col.operator_menu_enum(MODELERKIT_OT_rename_part.bl_idname, "part", text="Rename Active", icon="SORTALPHA")
    col.operator(MODELERKIT_OT_copy_left_to_right.bl_idname, icon="MOD_MIRROR")
    row = layout.row()
    row.enabled = context.mode == "OBJECT" and not explode_slider.has_data()  # both move parts from stored rests
    row.prop(context.scene, "mk_temple_fold", slider=True)


CLASSES = (MODELERKIT_OT_rename_part, MODELERKIT_OT_copy_left_to_right)


def register():
    bpy.types.Scene.mk_temple_fold = bpy.props.FloatProperty(
        name="Fold Temples", subtype="ANGLE", min=0.0, max=1.745, default=0.0, update=update_fold,
        description="Swing both temples in about their hinges, to check the fold. Back to 0 restores them exactly")
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.mk_temple_fold
