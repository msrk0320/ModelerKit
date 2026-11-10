"""Dimensions section: the task's measurements, what the model measures, and Fit to Spec."""

import bpy

from .. import explode_slider
from . import logic, measure, overlay

STATUS_ICON = {"ok": "STRIP_COLOR_04", "near": "STRIP_COLOR_03", "out": "STRIP_COLOR_01", "unset": "STRIP_COLOR_09",
               "missing": "STRIP_COLOR_09"}


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


CLASSES = (MODELERKIT_Dimensions, MODELERKIT_OT_dimensions_fit, MODELERKIT_OT_dimensions_copy_report)


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
