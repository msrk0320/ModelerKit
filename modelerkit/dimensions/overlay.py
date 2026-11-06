"""Draws the measurements over the model in the 3D view, laid out like the QA card. Nothing is added to the scene."""

from collections import namedtuple

import blf
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import logic, measure

Item = namedtuple("Item", "key status lines outlines anchor value_text spec_text")

COLORS = {"ok": (0.37, 0.83, 0.54, 1.0), "near": (0.95, 0.72, 0.29, 1.0), "out": (1.0, 0.42, 0.42, 1.0),
          "unset": (0.7, 0.7, 0.7, 1.0), "missing": (0.7, 0.7, 0.7, 1.0)}
OFFSET = 0.07   # of the frame's width, how far lines sit outside the model
TICK = 0.15     # of OFFSET, how far end ticks run past their line
_handle = None


def _segments_of_box(box):
    low, high = box
    corner = [Vector((x, y, z)) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)]
    pairs = ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7))
    return [(corner[a], corner[b]) for a, b in pairs]


def _span(a, b, tick_a, tick_b):
    """A dimension line a..b with end ticks reaching back to the model at tick_a and tick_b."""
    return [(a, b), (tick_a, a), (tick_b, b)]


def _lines(key, boxes, off):
    """(line segments, part boxes) for one measurement, or None when its parts are missing."""
    left, right = boxes.get("lens_left"), boxes.get("lens_right")
    lenses = [b for b in (left, right) if b]
    front = boxes.get("rim") or (lenses[0] if lenses else None)
    tick = off * TICK
    if key == "frame_width" and boxes.get("rim"):
        low, high = boxes["rim"]
        z = high.z + off
        return (_span(Vector((low.x, low.y, z + tick)), Vector((high.x, low.y, z + tick)),
                      Vector((low.x, low.y, high.z)), Vector((high.x, low.y, high.z))), [boxes["rim"]])
    if key == "bridge" and left and right:
        inner_low, inner_high = min(left[1].x, right[1].x), max(left[0].x, right[0].x)
        y, top = front[0].y, front[1].z
        z = top + off * 0.45
        return (_span(Vector((inner_low, y, z)), Vector((inner_high, y, z)),
                      Vector((inner_low, y, top - off)), Vector((inner_high, y, top - off))), [left, right])
    if key == "lens_height" and lenses:
        lens = max(lenses, key=lambda b: b[1].z - b[0].z)
        plus = lens[0].x + lens[1].x >= 0
        x = (front[1].x + off) if plus else (front[0].x - off)
        edge = lens[1].x if plus else lens[0].x
        y = front[0].y
        return (_span(Vector((x, y, lens[0].z)), Vector((x, y, lens[1].z)),
                      Vector((edge, y, lens[0].z)), Vector((edge, y, lens[1].z))), lenses)
    temples = [b for b in (boxes.get("temple_left"), boxes.get("temple_right")) if b]
    if key == "temple_length" and temples:
        low, high = max(temples, key=lambda b: b[1].y - b[0].y)
        x = (high.x + off) if low.x + high.x >= 0 else (low.x - off)
        z = high.z + off * 0.4
        return (_span(Vector((x, low.y, z)), Vector((x, high.y, z)),
                      Vector((x, low.y, high.z)), Vector((x, high.y, high.z))), temples)
    return None


def geometry(res, specs):
    """The Items to draw for a measure.Result. Pure geometry, so tests need no GPU."""
    if res.error:
        return []
    fit = logic.fit(res.values, specs)
    found = logic.statuses(res.values, specs, fit.conflict)
    front = res.boxes.get("rim") or res.boxes.get("lens_left") or res.boxes.get("lens_right")
    size = (front[1].x - front[0].x) if front else 0.0
    if not size:
        size = max((b[1].y - b[0].y for b in res.boxes.values()), default=0.0)
    off = size * OFFSET
    items = []
    for key in logic.KEYS:
        value = res.values.get(key)
        placed = _lines(key, res.boxes, off) if value is not None and value > 0 else None
        if placed is None:
            continue
        lines, parts = placed
        status = found[key]
        problem = status == "out" or key in fit.conflict
        spec = specs.get(key)
        items.append(Item(key, status, lines, [s for b in parts for s in _segments_of_box(b)] if problem else [],
                          (lines[0][0] + lines[0][1]) / 2, "%.1f" % value,
                          logic.spec_text(key, spec) if spec else ""))
    return items


def _draw_segments(shader, segments, region, rv3d, color, width):
    points = []
    for a, b in segments:
        pa, pb = location_3d_to_region_2d(region, rv3d, a), location_3d_to_region_2d(region, rv3d, b)
        if pa is not None and pb is not None:  # None: behind the view
            points += [pa, pb]
    if points:
        gpu.state.line_width_set(width)
        batch = batch_for_shader(shader, "LINES", {"pos": points})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)


def place_label(at, away, size, gap, placed):
    """Lower-left corner for a label beside a line at screen point at, on the side away from the model, moved up past
    labels already placed (a list of (x, y, w, h), which this appends to). All in pixels."""
    w, h = size
    if abs(away[0]) > abs(away[1]):
        x, y = (at[0] + gap if away[0] > 0 else at[0] - gap - w), at[1] - h / 2
    else:
        x, y = at[0] - w / 2, (at[1] - gap - h if away[1] < 0 else at[1] + gap)
    while any(x < px + pw and px < x + w and y < py + ph and py < y + h for px, py, pw, ph in placed):
        y = max(py + ph for px, py, pw, ph in placed
                if x < px + pw and px < x + w and y < py + ph and py < y + h) + 1
    placed.append((x, y, w, h))
    return x, y


def _text_size(font, text, size):
    blf.size(font, size)
    return blf.dimensions(font, text)


def _draw_text(item, region, rv3d, placed):
    at = location_3d_to_region_2d(region, rv3d, item.anchor)
    if at is None:
        return
    tick, end = (location_3d_to_region_2d(region, rv3d, p) for p in item.lines[1])
    away = (end - tick) if tick is not None and end is not None else (0.0, 1.0)
    scale = bpy.context.preferences.system.ui_scale
    font, big, small = 0, 17 * scale, 11 * scale
    value_w, value_h = _text_size(font, item.value_text, big)
    spec_w, spec_h = _text_size(font, item.spec_text, small) if item.spec_text else (0.0, 0.0)
    line_gap = 4 * scale if item.spec_text else 0.0
    width, height = max(value_w, spec_w), value_h + spec_h + line_gap
    x, y = place_label(at, away, (width, height + 4 * scale), 6 * scale, placed)  # room for descenders and shadow
    blf.enable(font, blf.SHADOW)
    blf.shadow(font, 3, 0.0, 0.0, 0.0, 0.9)
    blf.size(font, big)
    blf.color(font, *COLORS[item.status])
    blf.position(font, x + (width - value_w) / 2, y + spec_h + line_gap, 0)
    blf.draw(font, item.value_text)
    if item.spec_text:
        blf.size(font, small)
        blf.color(font, 0.85, 0.85, 0.85, 1.0)
        blf.position(font, x + (width - spec_w) / 2, y, 0)
        blf.draw(font, item.spec_text)
    blf.disable(font, blf.SHADOW)


def _draw():
    context = bpy.context
    props = getattr(context.scene, "mk_dimensions", None)
    region, rv3d = context.region, context.region_data
    if props is None or not props.show or region is None or rv3d is None:
        return
    items = geometry(measure.result(context.scene), logic.specs_of(props))
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    for item in items:
        _draw_segments(shader, item.outlines, region, rv3d, COLORS["out"], 2.0)
        _draw_segments(shader, item.lines, region, rv3d, COLORS[item.status], 3.0 if item.status == "out" else 2.0)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")
    placed = []
    for item in items:
        _draw_text(item, region, rv3d, placed)


def start():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")


def stop():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
