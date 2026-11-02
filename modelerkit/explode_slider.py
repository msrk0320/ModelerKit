"""Explode objects and loose mesh pieces apart with one slider, then reset the data."""

import bpy
from mathutils import Vector


KEY = "_explode_rest"      # world-space rest position of each object's origin
KEY_C = "_explode_center"  # world-space rest bbox centre of each object
KEY_S = "_explode_size"    # largest dimension of the object's world bounding box at rest
KEY_N = "_explode_name"    # name of the object the rest data belongs to (Shift+D copies custom properties)
SK = "Explode"             # shape key that moves loose mesh islands apart
KEY_P = "_explode_placed"  # the local location the slider last gave the object: anything else is the user's own move
KEY_I = "_explode_active"  # on the mesh's shape keys: which key was active before the Explode key was built
KEY_B = "_explode_basis"   # on the mesh's shape keys: the Basis was added by this tool, not the user's
TIE = 0.02                 # centres closer than this share of the layout's spread count as one place


def explode_key(o):
    keys = o.data.shape_keys if o.type == 'MESH' else None
    return keys.key_blocks.get(SK) if keys else None


def exploded(objs):
    """Objects the slider has moved or split: they hold rest data or an Explode shape key."""
    return [o for o in objs if KEY in o or explode_key(o)]


def traces(o):
    """This tool's custom properties on an object or scene (the pre-texture gate looks for the same prefix)."""
    return [k for k in o.keys() if k.startswith("_explode")]


def remove_key(o):
    """Delete the Explode shape key (the pieces go back together), and the Basis if nothing else is left."""
    kb = explode_key(o)
    if kb is None:
        return
    o.shape_key_remove(kb)
    keys = o.data.shape_keys
    active = keys.get(KEY_I, 0)
    if KEY_I in keys:
        del keys[KEY_I]
    added_basis = KEY_B in keys
    if added_basis:
        del keys[KEY_B]
    if added_basis and len(keys.key_blocks) == 1:
        o.shape_key_clear()
    else:
        o.active_shape_key_index = active
    o.use_shape_key_edit_mode = False  # shortcut: assumes the user had it off (Blender's default)


def targets(context):
    if context.scene.mk_explode_selected_only:
        objs = context.selected_objects
    else:  # parts hidden since they were moved still go back with the slider
        shown = set(context.visible_objects)
        objs = list(shown) + [o for o in context.scene.objects if o not in shown and has_rest(o)]
    return [o for o in objs if o.type == 'MESH']


def bbox_center(o):
    return o.matrix_world @ (sum((Vector(c) for c in o.bound_box), Vector()) / 8)


def depth(o):
    """Parent chain length: placing objects in this order keeps a moving parent from carrying a placed child."""
    n = 0
    while o.parent:
        n, o = n + 1, o.parent
    return n


def has_rest(o):
    """True if o holds rest data of its own; a copy holds its source's, under the source's name."""
    owner = o.get(KEY_N, o.name)
    return KEY in o and KEY_C in o and (owner == o.name or owner not in bpy.data.objects)


def bbox_size(o):
    """Largest side of the object's world bounding box: the room it needs to clear its neighbours."""
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))


def rest_bounds(o, moving=()):
    """World bounding box (lo, hi) at the rest position: the current box less the slider's move."""
    move = o.matrix_world.translation - Vector(o[KEY]) - parent_shift(o, moving)
    pts = [o.matrix_world @ Vector(c) - move for c in o.bound_box]
    return (Vector(min(p[i] for p in pts) for i in range(3)), Vector(max(p[i] for p in pts) for i in range(3)))


def side_by_side(a, b):
    """True when the boxes are apart on Y or Z, so they don't block each other along X."""
    return any(a[1][i] < b[0][i] or b[1][i] < a[0][i] for i in (1, 2))


def parent_shift(o, moving=()):
    """How far the nearest exploded ancestor has moved: o rides along, so that part of its position isn't its rest.
    Zero when that ancestor is itself being placed (`moving`): o is then placed on its own target."""
    p = o.parent
    while p and not has_rest(p):
        p = p.parent
    return p.matrix_world.translation - Vector(p[KEY]) if p and p not in moving else Vector()


def capture(o):
    shift = parent_shift(o)
    o[KEY] = tuple(o.matrix_world.translation - shift)
    o[KEY_C] = tuple(bbox_center(o) - shift)
    o[KEY_S] = bbox_size(o)
    if KEY_P in o:
        del o[KEY_P]  # a copy holds its source's


def hand_move(o):
    """How far the user moved o since the slider placed it, in world space. Measured on its local location, which a
    moving parent doesn't change."""
    if KEY_P not in o:
        return Vector()
    move = o.location - Vector(o[KEY_P])
    return o.parent.matrix_world.to_3x3() @ o.matrix_parent_inverse.to_3x3() @ move if o.parent else move


def keep_hand_moves(objs):
    """Move the rest position along with whatever the user moved while exploded; children go with their parent."""
    moved = {}
    for o in sorted(objs, key=depth):
        p = o.parent
        while p and p not in moved:
            p = p.parent
        moved[o] = hand_move(o) + (moved[p] if p else Vector())
        if moved[o].length > 1e-4:
            o[KEY] = tuple(Vector(o[KEY]) + moved[o])
            o[KEY_C] = tuple(Vector(o[KEY_C]) + moved[o])


def clear(objs):
    for o in objs:
        for k in (KEY, KEY_C, KEY_S, KEY_N, KEY_P):
            if k in o:
                del o[k]


def island_key(o):
    """Return the Explode shape key, building it from the mesh's loose parts if missing. The pieces move along world
    X, whatever the object's rotation or (negative) scale."""
    me, kb = o.data, explode_key(o)
    if kb:
        return kb
    if not me.vertices:
        return None
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    roots = [find(i) for i in range(len(me.vertices))]
    lo, hi = {}, {}
    to_world = o.matrix_world.to_3x3()
    for v, r in zip(me.vertices, roots):
        c = to_world @ v.co
        if r not in lo:
            lo[r], hi[r] = c.copy(), c.copy()
        else:
            for i in range(3):
                lo[r][i] = min(lo[r][i], c[i])
                hi[r][i] = max(hi[r][i], c[i])
    if len(lo) < 2:
        return None  # single piece, nothing to separate
    mid = (Vector(min(v[i] for v in lo.values()) for i in range(3))
           + Vector(max(v[i] for v in hi.values()) for i in range(3))) / 2
    added_basis, active = not me.shape_keys, o.active_shape_key_index
    if added_basis:
        o.shape_key_add(name="Basis", from_mix=False)
    kb = o.shape_key_add(name=SK, from_mix=False)
    kb.slider_min, kb.slider_max = 0.0, 10.0
    o.use_shape_key_edit_mode = True
    me.shape_keys[KEY_I] = active
    if added_basis:
        me.shape_keys[KEY_B] = 1
    to_local = to_world.inverted_safe()
    shift = {r: to_local @ Vector((((lo[r] + hi[r]) / 2 - mid).x, 0, 0)) for r in lo}
    for i, r in enumerate(roots):
        kb.data[i].co = me.vertices[i].co + shift[r]
    return kb


def set_island_value(o, value):
    # Edit Mode writes its own copy of the shape keys back on exit, so a key built or switched under it is lost.
    editing = o.mode == 'EDIT'
    kb = island_key(o) if value > 0 and not editing else explode_key(o)
    if kb:
        kb.value = value
        if not editing:
            # Edit Mode edits and shows the active key: Explode while the pieces are apart, the mesh itself at rest.
            o.active_shape_key_index = o.data.shape_keys.key_blocks.find(SK) if value else 0


def update(self, context):
    sc = context.scene
    f = sc.mk_explode_factor
    objs = targets(context)
    if f == 0:  # at rest means everything, also parts moved under an earlier selection
        objs += [o for o in sc.objects if o.type == 'MESH' and has_rest(o) and o not in objs]
    if not objs:
        return
    for o in objs:
        if not has_rest(o):
            capture(o)  # added, copied or newly selected since the last capture
        o[KEY_N] = o.name  # a renamed object keeps its rest data
    keep_hand_moves(objs)
    for o in objs:
        set_island_value(o, f)

    centers = {o: Vector(o[KEY_C]) for o in objs}
    sizes = {o: o[KEY_S] for o in objs}

    # The spread is added to the rest layout, so 0 is the rest pose and the order is kept. Parts at the same X that
    # sit side by side share a rank and move together; overlapping parts (nested ones) still get their own.
    ranked = sorted(objs, key=lambda o: (centers[o].x, o.name))
    places = [centers[o].x for o in ranked]
    moving = set(objs)
    bounds = {o: rest_bounds(o, moving) for o in ranked}
    tie = TIE * (places[-1] - places[0])
    rank, ranks, group = 0, [], []
    for i, o in enumerate(ranked):
        if i and (places[i] - places[i - 1] > tie
                  or not all(side_by_side(bounds[o], bounds[g]) for g in group)):
            rank, group = rank + 1, []
        group.append(o)
        ranks.append(rank)
    step = f * max(sizes.values())
    offsets = {}
    for o, r in zip(ranked, ranks):
        offsets[o] = Vector(((r - rank / 2) * step, 0, 0))

    # Place objects
    for o in sorted(objs, key=depth):
        o.matrix_world.translation = Vector(o[KEY]) + offsets[o] + parent_shift(o, moving)
        if o.children:
            context.view_layer.update()  # a descendant is placed from its parent's matrix, which must not be stale

    context.view_layer.update()
    if f == 0:
        clear(objs)  # all back at rest: forget it, so moves made from here on are kept by the next explode
        for o in objs:
            if o.mode != 'EDIT':  # Edit Mode would write the key back on exit; Reset takes it from there
                remove_key(o)  # a leftover key blocks Apply Modifier and ends up in exports
    else:
        for o in objs:
            o[KEY_P] = tuple(o.location)


def can_run(cls, context, ok, why):
    """Operator poll: Object Mode (shape keys changed under Edit Mode are overwritten on exit) and something to do."""
    if context.mode != 'OBJECT':
        why, ok = "Return to Object Mode first", False
    if not ok:
        cls.poll_message_set(why)
    return bool(ok)


def poll_has_explode_data(cls, context):
    """True if any object or scene has explode data (shape keys or custom properties)."""
    return can_run(cls, context,
                   any(traces(o) or explode_key(o) for o in bpy.data.objects)
                   or any(traces(sc) or sc.mk_explode_factor for sc in bpy.data.scenes),
                   "Nothing to reset")


class MODELERKIT_OT_explode_reset(bpy.types.Operator):
    bl_idname = "modelerkit.explode_reset"
    bl_label = "Reset"
    bl_description = ("Put every part back where it started and remove all explode data from the file")
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(poll_has_explode_data)

    def execute(self, context):
        # Restore positions in every scene, because the rest data below goes from all of them (parents before children)
        objs = exploded(o for o in bpy.data.objects if o.users_scene)
        keep_hand_moves([o for o in objs if has_rest(o)])
        for o in sorted(objs, key=depth):
            if has_rest(o):
                o.matrix_world.translation = Vector(o[KEY])
                if o.children:
                    o.users_scene[0].view_layers[0].update()
            remove_key(o)

        # Remove ALL explode data from ALL objects (not just exploded ones)
        for o in bpy.data.objects:
            for k in traces(o):
                del o[k]

        # Remove ALL explode data from ALL scenes (including legacy keys)
        for sc in bpy.data.scenes:
            for k in traces(sc):
                del sc[k]

        for sc in bpy.data.scenes:
            sc.mk_explode_factor = 0.0
        return {'FINISHED'}


def draw(layout, context):
    col = layout.column()
    row = col.row()
    row.active = bool(targets(context)) and context.mode == 'OBJECT'  # greyed out when it can't do its whole job
    row.prop(context.scene, "mk_explode_factor", slider=True)
    col.prop(context.scene, "mk_explode_selected_only")
    col.operator("modelerkit.explode_reset")


classes = (MODELERKIT_OT_explode_reset,)


def register():
    bpy.types.Scene.mk_explode_factor = bpy.props.FloatProperty(
        name="Explode", min=0.0, max=10.0, soft_max=5.0, default=0.0, update=update,
        description="1 = parts about one part-size apart; higher spreads them further")
    bpy.types.Scene.mk_explode_selected_only = bpy.props.BoolProperty(
        name="Selected Only", default=False,
        description="Move only the selected meshes instead of every visible mesh")
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    for p in ("mk_explode_factor", "mk_explode_selected_only"):
        delattr(bpy.types.Scene, p)
