"""Import / reload textures written by Painter's 'Export Textures to Project Folder'."""

import ctypes
import os
import re
import shutil
import sys

import bpy


# Map suffix written by the Painter plugin -> (Principled BSDF input, colour space).
# Files are named <TextureSet>_<Suffix>.png, texture set name == material name.
MAPS = {
    "BaseColor": ("Base Color", "sRGB"),
    "Roughness": ("Roughness", "Non-Color"),
    "Metallic": ("Metallic", "Non-Color"),
    "Normal": ("Normal", "Non-Color"),
    "Transmissive": ("Transmission Weight", "Non-Color"),
}
# Lowercase file suffix -> MAPS key. Delivery packs call the metal map <SKU>_metalness.
SUFFIXES = {**{k.lower(): k for k in MAPS}, "metalness": "Metallic"}
EXTS = (".png", ".tga", ".tif", ".tiff", ".exr", ".jpg", ".jpeg")
NODE_PREFIX = "SPLink_"
PAINTER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "painter", "export_to_project_folder.py")


def _folder(context):
    path = context.scene.mk_sp_texture_folder
    if path == "//" and bpy.data.filepath:
        # Default folder: Painter's exporter writes to <spp folder>\<spp name>\Textures, so look there first
        # for an .spp saved beside the .blend under the same name.
        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        export = os.path.join(os.path.dirname(bpy.data.filepath), stem, "Textures")
        if os.path.isdir(export):
            return export
    return os.path.normpath(bpy.path.abspath(path)) if path else ""


def _folder_problem(context):
    """Why the texture folder can't be used, or "" when it can. An unsaved .blend would read "//" as the folder
    Blender was launched from."""
    if not context.scene.mk_sp_texture_folder:
        return "Pick a texture folder"
    if context.scene.mk_sp_texture_folder.startswith("//") and not bpy.data.filepath:
        return "Save the .blend first, or pick a texture folder"
    folder = _folder(context)
    return "" if os.path.isdir(folder) else "Texture folder not found: %s" % folder


def _scan(folder):
    """Return {texture_set_lower: {suffix: filepath}}."""
    found = {}
    pattern = re.compile(r"^(.*)_(%s)$" % "|".join(SUFFIXES), re.IGNORECASE)
    for f in os.listdir(folder):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in EXTS:
            continue
        m = pattern.match(stem)
        if not m:
            continue
        suffix = SUFFIXES[m.group(2).lower()]
        found.setdefault(_set_key(m.group(1)), {})[suffix] = os.path.join(folder, f)
    return found


def _set_key(name):
    # Mat_<SKU> and <SKU> are the same set: the material carries Mat_, delivered textures don't.
    return re.sub(r"^mat_", "", name.lower())


def _material_key(mat):
    # Blender adds .001 etc. on duplicate names; Painter never sees those.
    return _set_key(re.sub(r"\.\d{3}$", "", mat.name))


def _target_materials(context):
    objs = context.selected_objects or context.scene.objects
    mats = []
    for ob in objs:
        for slot in getattr(ob, "material_slots", []):
            if slot.material and slot.material not in mats:
                mats.append(slot.material)
    return mats


def _principled(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return bsdf


def _load_image(path, colorspace):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    img.reload()  # check_existing may hand back a stale copy
    return img


def _wire(mat, maps):
    bsdf = _principled(mat)  # also enables nodes, so node_tree exists
    nt = mat.node_tree

    # Drop nodes from a previous import so re-importing stays clean.
    for n in [n for n in nt.nodes if n.name.startswith(NODE_PREFIX)]:
        nt.nodes.remove(n)

    x = bsdf.location.x - 700
    y = bsdf.location.y
    for i, (suffix, path) in enumerate(sorted(maps.items(), key=lambda kv: list(MAPS).index(kv[0]))):
        socket, colorspace = MAPS[suffix]
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = tex.label = NODE_PREFIX + suffix
        tex.image = _load_image(path, colorspace)
        tex.location = (x, y - i * 300)

        if suffix == "Normal":
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.name = nmap.label = NODE_PREFIX + "NormalMap"
            nmap.location = (x + 350, y - i * 300)
            nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            nt.links.new(tex.outputs["Color"], bsdf.inputs[socket])


class MODELERKIT_OT_import(bpy.types.Operator):
    bl_idname = "modelerkit.import_textures"
    bl_label = "Import Textures"
    bl_description = ("Wire <Material>_BaseColor/Roughness/Metallic/Normal/Transmissive "
                      "into the Principled BSDF of each material with a matching name "
                      "(selected objects, or the whole scene if nothing is selected)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        problem = _folder_problem(context)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        folder = _folder(context)

        sets = _scan(folder)
        if not sets:
            self.report({"ERROR"}, "No <Set>_<Map> textures found in %s" % folder)
            return {"CANCELLED"}

        done, missing = [], []
        for mat in _target_materials(context):
            maps = sets.get(_material_key(mat))
            if maps:
                # _wire drops the previous import's nodes, so unticking also removes a normal map already connected.
                use_normal = context.scene.mk_sp_import_normal
                _wire(mat, {k: v for k, v in maps.items() if use_normal or k != "Normal"})
                done.append(mat.name)
            else:
                missing.append(mat.name)

        if not done:
            self.report({"ERROR"}, "No material name matches a texture set. Sets: %s"
                        % ", ".join(sorted(sets)))
            return {"CANCELLED"}
        msg = "Imported textures into %d material(s)" % len(done)
        if missing:
            msg += "; no textures for: %s" % ", ".join(missing)
        self.report({"WARNING"} if missing else {"INFO"}, msg)
        return {"FINISHED"}


class MODELERKIT_OT_reload(bpy.types.Operator):
    bl_idname = "modelerkit.reload_textures"
    bl_label = "Reload Textures"
    bl_description = "Re-read from disk every image loaded from the texture folder"

    def execute(self, context):
        problem = _folder_problem(context)
        if problem:
            self.report({"ERROR"}, problem)
            return {"CANCELLED"}
        folder = _folder(context)

        count, missing = 0, []
        for img in bpy.data.images:
            if img.source != "FILE" or not img.filepath:
                continue
            path = os.path.normpath(bpy.path.abspath(img.filepath, library=img.library))
            if os.path.normcase(os.path.dirname(path)) != os.path.normcase(folder):
                continue
            if img.packed_file:
                continue  # packed images would reload the packed copy, not the new export
            if not os.path.exists(path):
                missing.append(os.path.basename(path))
                continue  # keep the pixels in memory: reloading would turn the texture pink
            img.reload()
            count += 1

        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

        if count == 0 and not missing:
            self.report({"WARNING"}, "No loaded images come from this folder - use Import Textures first")
            return {"CANCELLED"}
        parts = ["Reloaded %d texture(s)" % count] if count else []
        if missing:
            parts.append("Missing from the folder: %s" % ", ".join(missing))
        msg = "; ".join(parts)
        self.report({"WARNING"} if missing else {"INFO"}, msg)
        if count == 0:
            return {"CANCELLED"}
        return {"FINISHED"}


def _painter_folder():
    """Painter's user folder. Asks Windows for Documents because OneDrive can move it away from the home folder."""
    docs = os.path.expanduser("~/Documents")
    if sys.platform == "win32":
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # 5 = CSIDL_PERSONAL
            docs = buf.value
    return os.path.join(docs, "Adobe", "Adobe Substance 3D Painter")


class MODELERKIT_OT_install_painter_export(bpy.types.Operator):
    bl_idname = "modelerkit.install_painter_export"
    bl_label = "Install Painter Export"
    bl_description = ("Copy the script behind Painter's File > Export Textures to Project Folder "
                      "into Painter's startup folder, replacing an older copy")

    def execute(self, context):
        painter = _painter_folder()
        if not os.path.isdir(painter):
            self.report({"ERROR"}, "Painter's folder not found: %s. Start Painter once, then try again" % painter)
            return {"CANCELLED"}
        startup = os.path.join(painter, "python", "startup")
        try:
            os.makedirs(startup, exist_ok=True)
            shutil.copyfile(PAINTER_SCRIPT, os.path.join(startup, os.path.basename(PAINTER_SCRIPT)))
        except OSError as e:
            self.report({"ERROR"}, "Could not install into %s: %s" % (startup, e))
            return {"CANCELLED"}
        self.report({"INFO"}, "Installed. Restart Painter, then use File > Export Textures to Project Folder")
        return {"FINISHED"}


def draw(layout, context):
    col = layout.column(align=True)
    col.prop(context.scene, "mk_sp_texture_folder", text="")
    col.separator()
    col.prop(context.scene, "mk_sp_import_normal")
    col.operator(MODELERKIT_OT_reload.bl_idname, icon="FILE_REFRESH")
    col.operator(MODELERKIT_OT_import.bl_idname, icon="IMPORT")
    col.separator()
    col.operator(MODELERKIT_OT_install_painter_export.bl_idname, icon="EXPORT")


CLASSES = (MODELERKIT_OT_import, MODELERKIT_OT_reload, MODELERKIT_OT_install_painter_export)


def register():
    bpy.types.Scene.mk_sp_texture_folder = bpy.props.StringProperty(
        name="Texture Folder",
        description="Folder Painter exported into (<spp folder>\\<spp name>\\Textures)",
        subtype="DIR_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},  # without it Blender paints the "//" default red
        default="//",  # browse starts in the .blend's folder
    )
    bpy.types.Scene.mk_sp_import_normal = bpy.props.BoolProperty(
        name="Normal Map",
        description="Connect the normal map on Import Textures. Untick and import again to remove one already connected",
        default=True,
    )
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.mk_sp_import_normal
    del bpy.types.Scene.mk_sp_texture_folder
