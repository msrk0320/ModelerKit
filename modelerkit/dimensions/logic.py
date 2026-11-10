"""Rules for the Dimensions panel: range status, and the uniform scale that fits. No bpy."""

from collections import namedtuple

KEYS = ("frame_width", "bridge", "lens_height", "temple_length")
LABELS = {"frame_width": "Frame Width", "bridge": "Bridge", "lens_height": "Lens Height",
          "temple_length": "Temple Length"}
TOLERANCE = {"frame_width": 3.0, "bridge": 2.0, "lens_height": 3.0, "temple_length": 10.0}  # mm, from the QA card
NEAR = 0.1  # the last 10% of the tolerance reads as close to the limit

Fit = namedtuple("Fit", "state factor after conflict")  # state: none, ok, fit, conflict

def specs_of(props):
    """{key: mm} from anything holding the four measurements as attributes (the scene's settings)."""
    return {k: getattr(props, k) for k in KEYS}


def tolerance_of(key, exact_frame=True):
    """Exact Frame Fit drops only Frame Width's range."""
    return 0.0 if exact_frame and key == "frame_width" else TOLERANCE[key]


def spec_text(key, spec, exact_frame=True):
    tolerance = tolerance_of(key, exact_frame)
    return "spec %g ±%g" % (spec, tolerance) if tolerance else "spec %g" % spec


def status(value, spec, tolerance):
    """unset (no spec), missing (nothing to measure), ok, near (in range, close to a limit) or out."""
    if not spec:
        return "unset"
    if value is None or value <= 0:
        return "missing"
    off = round(abs(round(value, 1) - round(spec, 1)), 6)  # QA shows one decimal
    if off > tolerance:
        return "out"
    return "near" if off > tolerance * (1 - NEAR) else "ok"


def fit(values, specs, exact_frame=True):
    """With Exact Frame Fit, the uniform factor that makes Frame Width exact, wherever that leaves the others.
    Otherwise, or without a Frame Width, the factor that puts every measurement in range, closest to the exact
    Frame Width (or to 1)."""
    specs = {k: round(v or 0.0, 1) for k, v in specs.items()}  # status compares at one decimal too
    keys = [k for k in KEYS if specs.get(k) and values.get(k) and values[k] > 0]
    if not keys:
        return Fit("none", None, None, ())
    if exact_frame and "frame_width" in keys:  # the rest may land off their tolerance
        if status(values["frame_width"], specs["frame_width"], 0.0) != "out":
            return Fit("ok", None, None, ())
        factor = specs["frame_width"] / values["frame_width"]
        return Fit("fit", factor, {k: values[k] * factor for k in keys}, ())
    if all(status(values[k], specs[k], tolerance_of(k, exact_frame)) != "out" for k in keys):
        return Fit("ok", None, None, ())
    low = {k: (specs[k] - TOLERANCE[k]) / values[k] for k in keys}
    high = {k: (specs[k] + TOLERANCE[k]) / values[k] for k in keys}
    low_key, high_key = max(low, key=low.get), min(high, key=high.get)
    if low[low_key] > high[high_key]:
        return Fit("conflict", None, None, (low_key, high_key))
    wanted = specs["frame_width"] / values["frame_width"] if "frame_width" in keys else 1.0
    factor = min(max(wanted, low[low_key]), high[high_key])
    return Fit("fit", factor, {k: values[k] * factor for k in keys}, ())


def statuses(values, specs, conflict=(), exact_frame=True):
    """Status per measurement. A conflict member still in range shows as near, since it blocks the fit."""
    found = {k: status(values.get(k), specs.get(k), tolerance_of(k, exact_frame)) for k in KEYS}
    for k in conflict:
        if found[k] == "ok":
            found[k] = "near"
    return found
