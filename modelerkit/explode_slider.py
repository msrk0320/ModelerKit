"""Explode objects and loose mesh pieces apart with one slider, then reset the data."""

import bpy
from mathutils import Vector


KEY = "_explode_rest"      # world-space rest position of each object's origin
KEY_C = "_explode_center"  # world-space rest bbox centre of each object
KEY_S = "_explode_size"    # largest dimension of the object's world bounding box at rest
KEY_N = "_explode_name"    # name of the object the rest data belongs to (Shift+D copies custom properties)
SK = "Explode"             # shape key that moves loose mesh islands apart
KEY_A = "_explode_axis"    # on the mesh's shape keys: the world axis the Explode key was built for
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
    if KEY_A in o.data.shape_keys:
        del o.data.shape_keys[KEY_A]
    if len(o.data.shape_keys.key_blocks) == 1:
        o.shape_key_clear()


def bake_and_remove_key(o):
    """Move the pieces' current offset into the mesh and its other shape keys, then delete the Explode key.
    Works on shared meshes too: linked duplicates show the same pieces anyway."""
    me, kb = o.data, explode_key(o)
    if kb is None:
        return
    co, ref = [0.0] * (3 * len(me.vertices)), [0.0] * (3 * len(me.vertices))
    kb.data.foreach_get("co", co)
    kb.relative_key.data.foreach_get("co", ref)
    f = 0.0 if kb.mute else kb.value
    offset = [(a - b) * f for a, b in zip(co, ref)]
    remove_key(o)
    for points in [me.vertices] + [k.data for k in (me.shape_keys.key_blocks if me.shape_keys else ())]:
        points.foreach_get("co", co)
        points.foreach_set("co", [a + d for a, d in zip(co, offset)])
    me.update()


def targets(context):
    objs = context.selected_objects if context.scene.explode_selected_only else context.visible_objects
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


def rest_bounds(o):
    """World bounding box (lo, hi) at the rest position: the current box less the slider's move."""
    move = o.matrix_world.translation - Vector(o[KEY])
    pts = [o.matrix_world @ Vector(c) - move for c in o.bound_box]
    return (Vector(min(p[i] for p in pts) for i in range(3)), Vector(max(p[i] for p in pts) for i in range(3)))


def side_by_side(a, b, axis):
    """True when the boxes are apart across the axis (a left/right pair seen along Y or Z)."""
    return any(axis[i] == 0 and (a[1][i] < b[0][i] or b[1][i] < a[0][i]) for i in range(3))


def capture(o):
    o[KEY] = tuple(o.matrix_world.translation)
    o[KEY_C] = tuple(bbox_center(o))
    o[KEY_S] = bbox_size(o)


def clear(objs):
    for o in objs:
        for k in (KEY, KEY_C, KEY_S, KEY_N):
            if k in o:
                del o[k]


def axis_vector(direction):
    return Vector([float(direction == a) for a in "XYZ"])


def island_key(o, direction):
    """Return the Explode shape key, building it from the mesh's loose parts if missing. The pieces move along the
    world axis, whatever the object's rotation or (negative) scale; a key built for another axis is rebuilt."""
    me, kb = o.data, explode_key(o)
    if kb and me.shape_keys.get(KEY_A) == direction:
        return kb
    if kb:
        remove_key(o)
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
    if not me.shape_keys:
        o.shape_key_add(name="Basis", from_mix=False)
    kb = o.shape_key_add(name=SK, from_mix=False)
    kb.slider_min, kb.slider_max = 0.0, 10.0
    o.use_shape_key_edit_mode = True
    me.shape_keys[KEY_A] = direction
    axis, to_local = axis_vector(direction), to_world.inverted_safe()
    shift = {r: to_local @ (axis * (((lo[r] + hi[r]) / 2 - mid) @ axis)) for r in lo}
    for i, r in enumerate(roots):
        kb.data[i].co = me.vertices[i].co + shift[r]
    return kb


def set_island_value(o, value, build, direction):
    # Edit Mode writes its own copy of the shape keys back on exit, so a key built or switched under it is lost.
    editing = o.mode == 'EDIT'
    kb = island_key(o, direction) if build and not editing else explode_key(o)
    if kb:
        kb.value = value
        if not editing:
            # Edit Mode edits and shows the active key: Explode while the pieces are apart, the mesh itself at rest.
            o.active_shape_key_index = o.data.shape_keys.key_blocks.find(SK) if value else 0


def update(self, context):
    objs = targets(context)
    if not objs:
        return
    sc = context.scene
    f = sc.explode_factor
    for o in objs:
        if not has_rest(o):
            capture(o)  # added, copied or newly selected since the last capture
        o[KEY_N] = o.name  # a renamed object keeps its rest data
    for o in objs:
        set_island_value(o, f if sc.explode_islands else 0.0, sc.explode_islands and f > 0, sc.explode_direction)

    centers = {o: Vector(o[KEY_C]) for o in objs}
    sizes = {o: o[KEY_S] for o in objs}

    direction = sc.explode_direction
    anchor = sc.explode_anchor
    active = context.view_layer.objects.active

    # Along an axis: the spread is added to the rest layout, so 0 is the rest pose and the order is kept.
    # Parts at the same place on the axis that sit side by side (a left/right pair along Y or Z) share a rank
    # and move together; overlapping parts (nested ones) still get their own.
    axis = axis_vector(direction)
    ranked = sorted(objs, key=lambda o: (centers[o] @ axis, o.name))
    places = [centers[o] @ axis for o in ranked]
    bounds = {o: rest_bounds(o) for o in ranked}
    tie = TIE * (places[-1] - places[0])
    rank, ranks, group = 0, [], []
    for i, o in enumerate(ranked):
        if i and (places[i] - places[i - 1] > tie
                  or not all(side_by_side(bounds[o], bounds[g], axis) for g in group)):
            rank, group = rank + 1, []
        group.append(o)
        ranks.append(rank)
    step = f * max(sizes.values())
    offsets = {}
    for o, r in zip(ranked, ranks):
        offsets[o] = axis * ((r - rank / 2) * step)

    # Apply anchor if active object is in the moving set
    if anchor and active and active in objs:
        anchor_offset = offsets[active]
        for o in objs:
            offsets[o] = offsets[o] - anchor_offset

    # Place objects
    for o in sorted(objs, key=depth):
        o.matrix_world.translation = Vector(o[KEY]) + offsets[o]

    if f == 0:
        clear(objs)  # all back at rest: forget it, so moves made from here on are kept by the next explode
    context.view_layer.update()


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
                   any(traces(o) or explode_key(o) for o in bpy.data.objects) or any(traces(sc) for sc in bpy.data.scenes),
                   "Nothing to reset")


class OBJECT_OT_explode_reset(bpy.types.Operator):
    bl_idname = "object.explode_reset"
    bl_label = "Reset"
    bl_description = ("Put every part back where it started and remove all explode data from the file")
    bl_options = {'REGISTER', 'UNDO'}
    poll = classmethod(poll_has_explode_data)

    def execute(self, context):
        # Restore positions for objects with rest data (parents before children)
        objs = exploded(context.scene.objects)
        for o in sorted(objs, key=depth):
            if has_rest(o):
                o.matrix_world.translation = Vector(o[KEY])
            remove_key(o)

        # Remove ALL explode data from ALL objects (not just exploded ones)
        for o in bpy.data.objects:
            for k in traces(o):
                del o[k]

        # Remove ALL explode data from ALL scenes (including legacy keys)
        for sc in bpy.data.scenes:
            for k in traces(sc):
                del sc[k]
            if "_explode_mid" in sc:  # legacy: remove old centre data from files made with earlier versions
                del sc["_explode_mid"]

        # Set slider to 0 without triggering update callback (nothing left to restore)
        context.scene.explode_factor = 0.0
        return {'FINISHED'}


def draw(layout, context):
    col = layout.column()
    row = col.row()
    row.active = bool(targets(context))  # greyed out while there is nothing for it to move
    row.prop(context.scene, "explode_factor", slider=True)
    col.operator("object.explode_reset")


classes = (OBJECT_OT_explode_reset,)


def register():
    bpy.types.Scene.explode_factor = bpy.props.FloatProperty(
        name="Explode", min=0.0, max=10.0, soft_max=5.0, default=0.0, update=update,
        description="1 = parts about one part-size apart; higher spreads them further")
    bpy.types.Scene.explode_direction = bpy.props.EnumProperty(
        name="Direction", items=[
            ('X', "Along X", "Parts line up along world X axis"),
            ('Y', "Along Y", "Parts line up along world Y axis"),
            ('Z', "Along Z", "Parts line up along world Z axis"),
        ], default='X', update=update,
        description="How parts move apart")
    bpy.types.Scene.explode_anchor = bpy.props.BoolProperty(
        name="Keep Active Part in Place", default=False, update=update,
        description="When on, the active object stays at rest and others move relative to it")
    bpy.types.Scene.explode_selected_only = bpy.props.BoolProperty(
        name="Selected Only", default=False,
        description="Move only the selected meshes instead of every visible mesh")
    bpy.types.Scene.explode_islands = bpy.props.BoolProperty(
        name="Also Split Mesh Pieces", default=True,
        description="Also move the loose parts inside each mesh apart", update=update)
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    for p in ("explode_factor", "explode_direction", "explode_anchor", "explode_selected_only", "explode_islands"):
        delattr(bpy.types.Scene, p)
