"""Dimensions section: the task's measurements, what the model measures, and Fit to Spec."""

import json
import os

import bpy

from .. import explode_slider
from . import logic, measure, overlay

STATUS_ICON = {"ok": "STRIP_COLOR_04", "near": "STRIP_COLOR_03", "out": "STRIP_COLOR_01", "unset": "STRIP_COLOR_09",
               "missing": "STRIP_COLOR_09"}


def _on_paste(self, _context):
    found = logic.parse(self.paste)
    if found:
        for key, value in found.items():
            setattr(self, key, value)
        self["paste"] = ""  # direct, so this callback doesn't run again


def _on_change(_self, _context):
    measure.redraw()


class MODELERKIT_Dimensions(bpy.types.PropertyGroup):
    exact_frame: bpy.props.BoolProperty(name="Exact Frame Fit", default=True, update=_on_change,
                                        description="On: Frame Width must equal its spec at QA's 0.1 mm, and Fit to Spec "
                                                    "lands on it. Off: Frame Width may be ±3 mm like the others")
    frame_width: bpy.props.FloatProperty(name="Frame Width", min=0.0, max=1000.0, precision=1, update=_on_change)
    bridge: bpy.props.FloatProperty(name="Bridge", min=0.0, max=1000.0, precision=1, update=_on_change)
    lens_height: bpy.props.FloatProperty(name="Lens Height", min=0.0, max=1000.0, precision=1, update=_on_change)
    temple_length: bpy.props.FloatProperty(name="Temple Length", min=0.0, max=1000.0, precision=1, update=_on_change)
    paste: bpy.props.StringProperty(name="Paste", description="Paste the Dimensions line from the task page",
                                    update=_on_paste)
    show: bpy.props.BoolProperty(name="Show Measurements", description="Draw the measurements on the model in the 3D view",
                                 update=_on_change)


class MODELERKIT_OT_dimensions_fit(bpy.types.Operator):
    bl_idname = "modelerkit.dimensions_fit"
    bl_label = "Fit to Spec"
    bl_description = "Scale the whole model about the world origin so Frame Width is exact"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if explode_slider.has_data():
            self.report({"ERROR"}, "Press Explode > Reset first: it would restore the old size.")
            return {"CANCELLED"}
        measure.mark_dirty()
        res = measure.result(context.scene)
        if res.error:
            self.report({"ERROR"}, res.error)
            return {"CANCELLED"}
        if measure.rotated(res.root):
            self.report({"ERROR"}, "Clear the rotation on %s first: the measurements assume it faces front." % res.root.name)
            return {"CANCELLED"}
        props = context.scene.mk_dimensions
        fit = logic.fit(res.values, logic.specs_of(props), props.exact_frame)
        if fit.state != "fit":
            self.report({"ERROR"}, "Nothing to fit." if fit.state != "conflict" else "No single scale fits: fix the model's proportions.")
            return {"CANCELLED"}
        res.root.location *= fit.factor
        res.root.scale *= fit.factor
        context.view_layer.update()
        measure.mark_dirty()
        self.report({"INFO"}, "Scaled ×%.3f" % fit.factor)
        return {"FINISHED"}


def specs_file():
    """Saved specs live in this computer's Blender config, never in the file or the add-on."""
    return os.path.join(bpy.utils.user_resource("CONFIG", path="modelerkit"), "specs.json")


def _saved():
    try:
        with open(specs_file(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _root(op, context):
    roots = measure.find_roots(context.scene)
    if len(roots) != 1:
        op.report({"ERROR"}, "Needs one top parent named after the SKU")
        return None
    return roots[0]


class MODELERKIT_OT_dimensions_save_spec(bpy.types.Operator):
    bl_idname = "modelerkit.dimensions_save_spec"
    bl_label = "Save Spec"
    bl_description = "Remember these measurements on this computer under the top parent's name (the SKU)"

    def execute(self, context):
        root = _root(self, context)
        if root is None:
            return {"CANCELLED"}
        props = context.scene.mk_dimensions
        saved = _saved()
        saved[root.name] = {**logic.specs_of(props), "exact_frame": props.exact_frame}
        os.makedirs(os.path.dirname(specs_file()), exist_ok=True)
        with open(specs_file(), "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=1, sort_keys=True)
        self.report({"INFO"}, "Saved the spec for %s" % root.name)
        return {"FINISHED"}


_items = []  # Blender needs the enum strings kept alive while the menu is open


def _spec_items(_self, _context):
    _items[:] = [(sku, sku, "") for sku in sorted(_saved())] or [("", "No saved specs", "")]
    return _items


class MODELERKIT_OT_dimensions_load_spec(bpy.types.Operator):
    bl_idname = "modelerkit.dimensions_load_spec"
    bl_label = "Load Spec"
    bl_description = "Fill the measurements with a spec saved on this computer"
    bl_property = "sku"
    bl_options = {"REGISTER", "UNDO"}

    sku: bpy.props.EnumProperty(name="SKU", items=_spec_items)

    def execute(self, context):
        spec = _saved().get(self.sku)
        if not spec:
            return {"CANCELLED"}
        props = context.scene.mk_dimensions
        for key, value in spec.items():
            setattr(props, key, value)
        return {"FINISHED"}


def report_text(context):
    props = context.scene.mk_dimensions
    res = measure.result(context.scene)
    specs = logic.specs_of(props)
    found = logic.statuses(res.values, specs, exact_frame=props.exact_frame)
    lines = [res.root.name if res.root else res.error]
    for key in logic.KEYS:
        value = res.values.get(key)
        spec = logic.spec_text(key, specs[key], props.exact_frame) if specs[key] else "no spec"
        lines.append("%s: %s, model %s (%s)" % (logic.LABELS[key], spec, "%.1f" % value if value is not None else "-",
                                                found[key]))
    if res.lens_width is not None:
        lines.append("Lens Width: %.1f" % res.lens_width)
    return "\n".join(lines + list(res.notes))


class MODELERKIT_OT_dimensions_copy_report(bpy.types.Operator):
    bl_idname = "modelerkit.dimensions_copy_report"
    bl_label = "Copy Report"
    bl_description = "Copy the specs, what the model measures and any warnings, as text to paste in the task"

    def execute(self, context):
        measure.mark_dirty()
        context.window_manager.clipboard = report_text(context)
        self.report({"INFO"}, "Report copied")
        return {"FINISHED"}


def draw(layout, context):
    props = context.scene.mk_dimensions
    row = layout.row(align=True)
    row.operator_menu_enum(MODELERKIT_OT_dimensions_load_spec.bl_idname, "sku", text="Load Spec", icon="IMPORT")
    row.operator(MODELERKIT_OT_dimensions_save_spec.bl_idname, text="Save Spec", icon="FILE_TICK")
    layout.prop(props, "paste", text="", icon="PASTEDOWN", placeholder="Paste task Dimensions line")
    if props.paste:
        layout.label(text="No measurements found in that text", icon="ERROR")
    layout.prop(props, "exact_frame")
    specs = logic.specs_of(props)
    if not any(specs.values()):
        layout.label(text="Enter measurements", icon="INFO")
    res = measure.result(context.scene)
    if res.error:
        layout.label(text=res.error, icon="ERROR")
    fit = logic.fit(res.values, specs, props.exact_frame)
    found = logic.statuses(res.values, specs, fit.conflict, props.exact_frame)
    for key in logic.KEYS:
        row = layout.row(align=True)
        row.alert = found[key] == "out"
        split = row.split(factor=0.62, align=True)
        split.prop(props, key, text=logic.LABELS[key].replace(" Length", ""))  # the sidebar truncates the full name
        value = res.values.get(key)
        split.label(text="%.1f" % value if value is not None else "-", icon=STATUS_ICON[found[key]])
    if res.lens_width is not None:
        layout.label(text="Lens Width: %.1f" % res.lens_width)
    layout.prop(props, "show", toggle=True, icon="HIDE_OFF" if props.show else "HIDE_ON",
                text="Hide Measurements" if props.show else "Show Measurements")
    exploded = explode_slider.has_data()
    row = layout.row()
    row.enabled = fit.state == "fit" and not exploded and not (res.root and measure.rotated(res.root))
    text = {"fit": "Fit to Spec (×%.3f)" % (fit.factor or 1.0), "ok": "Fit to Spec: already fits",
            "conflict": "Fit to Spec: not possible", "none": "Fit to Spec"}[fit.state]
    row.operator(MODELERKIT_OT_dimensions_fit.bl_idname, text=text, icon="FULLSCREEN_ENTER")
    if exploded:
        layout.label(text="Press Explode > Reset before scaling", icon="ERROR")
    if fit.state == "fit":
        box = layout.box()
        box.label(text="After the fit: " + ", ".join("%.1f" % fit.after[k] for k in logic.KEYS if k in fit.after))
        after = logic.statuses(fit.after, specs, exact_frame=props.exact_frame)
        off = [logic.LABELS[k] for k in logic.KEYS if after[k] == "out"]
        if off:
            box.label(text="Out of range after: " + ", ".join(off), icon="ERROR")
    elif fit.state == "conflict":
        box = layout.box()
        box.alert = True
        a, b = (logic.LABELS[k] for k in fit.conflict)
        box.label(text="%s and %s" % (a, b), icon="ERROR")
        box.label(text="can't both fit. Fix the model's proportions.")
    for note in res.notes:
        layout.label(text=note, icon="ERROR")
    layout.operator(MODELERKIT_OT_dimensions_copy_report.bl_idname, icon="COPYDOWN")


CLASSES = (MODELERKIT_Dimensions, MODELERKIT_OT_dimensions_fit, MODELERKIT_OT_dimensions_save_spec,
           MODELERKIT_OT_dimensions_load_spec, MODELERKIT_OT_dimensions_copy_report)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.mk_dimensions = bpy.props.PointerProperty(type=MODELERKIT_Dimensions)
    measure.register()
    overlay.start()


def unregister():
    overlay.stop()
    measure.unregister()
    del bpy.types.Scene.mk_dimensions
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
