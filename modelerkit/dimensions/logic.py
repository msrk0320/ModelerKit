"""Rules for the Dimensions panel: parsing the task page's line, range status, and the uniform scale that fits. No bpy."""

import re
from collections import namedtuple

KEYS = ("frame_width", "bridge", "lens_height", "temple_length")
LABELS = {"frame_width": "Frame Width", "bridge": "Bridge", "lens_height": "Lens Height",
          "temple_length": "Temple Length"}
TOLERANCE = {"frame_width": 0.0, "bridge": 2.0, "lens_height": 3.0, "temple_length": 10.0}  # mm; QA needs the frame exact
NEAR = 0.1  # the last 10% of the tolerance reads as close to the limit

Fit = namedtuple("Fit", "state factor after conflict")  # state: none, ok, fit, conflict

_FIELD = re.compile(r"(frame\s*width|bridge(?:\s*width)?|lens\s*height|temple\s*length)\s*[:=]?\s*(\d+(?:\.\d+)?)",
                    re.IGNORECASE)


def specs_of(props):
    """{key: mm} from anything holding the four measurements as attributes (the scene's settings)."""
    return {k: getattr(props, k) for k in KEYS}


def parse(text):
    """{key: mm} for every measurement named in text, such as the task page's Dimensions line."""
    return {next(k for k in KEYS if k[0] == name[0].lower()): float(number) for name, number in _FIELD.findall(text or "")}


def spec_text(key, spec):
    return "spec %g ±%g" % (spec, TOLERANCE[key]) if TOLERANCE[key] else "spec %g" % spec


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


def fit(values, specs):
    """The uniform factor that makes Frame Width exact, wherever that leaves the others. Without a Frame Width, the
    factor closest to 1 that puts every measurement with a spec in range."""
    specs = {k: round(v or 0.0, 1) for k, v in specs.items()}  # status compares at one decimal too
    keys = [k for k in KEYS if specs.get(k) and values.get(k) and values[k] > 0]
    if not keys:
        return Fit("none", None, None, ())
    if "frame_width" in keys:  # the rest may land off their tolerance
        if status(values["frame_width"], specs["frame_width"], TOLERANCE["frame_width"]) != "out":
            return Fit("ok", None, None, ())
        factor = specs["frame_width"] / values["frame_width"]
        return Fit("fit", factor, {k: values[k] * factor for k in keys}, ())
    if all(status(values[k], specs[k], TOLERANCE[k]) != "out" for k in keys):
        return Fit("ok", None, None, ())
    low = {k: (specs[k] - TOLERANCE[k]) / values[k] for k in keys}
    high = {k: (specs[k] + TOLERANCE[k]) / values[k] for k in keys}
    low_key, high_key = max(low, key=low.get), min(high, key=high.get)
    if low[low_key] > high[high_key]:
        return Fit("conflict", None, None, (low_key, high_key))
    factor = min(max(1.0, low[low_key]), high[high_key])
    return Fit("fit", factor, {k: values[k] * factor for k in keys}, ())


def statuses(values, specs, conflict=()):
    """Status per measurement. A conflict member still in range shows as near, since it blocks the fit."""
    found = {k: status(values.get(k), specs.get(k), TOLERANCE[k]) for k in KEYS}
    for k in conflict:
        if found[k] == "ok":
            found[k] = "near"
    return found
