"""Export to Project Folder

Adds File > "Export Textures to Project Folder".
Exports BaseColor, Roughness, Metallic, Normal (OpenGL) and Transmissive (grayscale) for every texture set
to <folder of the saved .spp>\\<.spp file name>\\Textures\\ as PNG, 2048, infinite dilation, with selectable bit depth and dithering.
Lives in python/startup so Painter loads it every session.
"""

import os

from PySide6 import QtGui, QtWidgets

import substance_painter.export as sp_export
import substance_painter.logging as sp_log
import substance_painter.project as sp_project
import substance_painter.textureset as sp_textureset
import substance_painter.ui as sp_ui

SUBFOLDER = "Textures"
PRESET_NAME = "ProjectFolder_BRMNT"
SIZE_LOG2 = 11  # 2048

_action = None


def _rgb_map(file_suffix, src_map):
    return {
        "fileName": "$textureSet_" + file_suffix,
        "channels": [
            {"destChannel": c, "srcChannel": c,
             "srcMapType": "documentMap", "srcMapName": src_map}
            for c in ("R", "G", "B")
        ],
    }


def _gray_map(file_suffix, src_map):
    return {
        "fileName": "$textureSet_" + file_suffix,
        "channels": [{
            "destChannel": "L",
            "srcChannel": "L",
            "srcMapType": "documentMap",
            "srcMapName": src_map,
        }],
    }


def _build_config(export_dir, bit_depth="8", dithering=False):
    return {
        "exportShaderParams": False,
        "exportPath": export_dir,
        "defaultExportPreset": PRESET_NAME,
        "exportPresets": [{
            "name": PRESET_NAME,
            "maps": [
                _rgb_map("BaseColor", "baseColor"),
                _gray_map("Roughness", "roughness"),
                _gray_map("Metallic", "metallic"),
                # Normal baked + height detail, OpenGL (Y+) convention.
                {
                    "fileName": "$textureSet_Normal",
                    "channels": [
                        {"destChannel": c, "srcChannel": c,
                         "srcMapType": "virtualMap", "srcMapName": "Normal_OpenGL"}
                        for c in ("R", "G", "B")
                    ],
                },
                # Transmissive is a colour channel: reading "L" exports black,
                # so take its R channel into a grayscale file.
                {
                    "fileName": "$textureSet_Transmissive",
                    "channels": [{
                        "destChannel": "L",
                        "srcChannel": "R",
                        "srcMapType": "documentMap",
                        "srcMapName": "transmissive",
                    }],
                },
            ],
        }],
        "exportList": [{"rootPath": ts.name()} for ts in sp_textureset.all_texture_sets()],
        "exportParameters": [{
            "parameters": {
                "fileFormat": "png",
                "bitDepth": bit_depth,
                "dithering": dithering,
                "sizeLog2": SIZE_LOG2,
                "paddingAlgorithm": "infinite",
            },
        }],
    }


def _message(title, text, error=False):
    box = QtWidgets.QMessageBox.critical if error else QtWidgets.QMessageBox.information
    box(sp_ui.get_main_window(), title, text)


def _create_export_dialog(export_dir):
    dialog = QtWidgets.QDialog(sp_ui.get_main_window())
    dialog.setWindowTitle("Export Textures to Project Folder")
    layout = QtWidgets.QVBoxLayout(dialog)
    form = QtWidgets.QFormLayout()
    depth = QtWidgets.QComboBox(dialog)
    depth.addItem("8-bit PNG", "8")
    depth.addItem("16-bit PNG", "16")
    form.addRow("Bit depth:", depth)
    dither = QtWidgets.QCheckBox("Enable dithering", dialog)
    dither.setChecked(False)
    form.addRow("", dither)
    layout.addLayout(form)
    details = QtWidgets.QLabel("Applies to all exported maps.\n2048 x 2048 PNG, OpenGL normal, infinite padding.\n\n" + export_dir, dialog)
    details.setWordWrap(True)
    layout.addWidget(details)
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel, parent=dialog)
    buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Export")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog, depth, dither


def export_to_project_folder():
    if not sp_project.is_open():
        _message("Export", "No project is open.", error=True)
        return
    spp = sp_project.file_path()
    if not spp:
        _message("Export", "Save the project first, so there is a folder to export into.", error=True)
        return

    name = os.path.splitext(os.path.basename(spp))[0]
    export_dir = os.path.join(os.path.dirname(spp), name, SUBFOLDER)
    dialog, depth, dither = _create_export_dialog(export_dir)
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        dialog.deleteLater()
        return
    bit_depth, dithering = depth.currentData(), dither.isChecked()
    dialog.deleteLater()
    os.makedirs(export_dir, exist_ok=True)

    try:
        result = sp_export.export_project_textures(_build_config(export_dir, bit_depth, dithering))
    except Exception as e:  # surface API errors instead of failing silently
        sp_log.error("Export to project folder failed: %s" % e)
        _message("Export", "Export failed:\n%s" % e, error=True)
        return

    if result.status != sp_export.ExportStatus.Success:
        _message("Export", "Export did not finish:\n%s" % result.message, error=True)
        return

    files = [f for paths in result.textures.values() for f in paths]
    sp_log.info("Exported %d textures to %s" % (len(files), export_dir))
    _message("Export", "Exported %d textures to:\n%s" % (len(files), export_dir))


def start_plugin():
    global _action
    _action = QtGui.QAction("Export Textures to Project Folder")
    _action.triggered.connect(export_to_project_folder)
    sp_ui.add_action(sp_ui.ApplicationMenu.File, _action)


def close_plugin():
    global _action
    if _action is not None:
        sp_ui.delete_ui_element(_action)
        _action = None


if __name__ == "__main__":
    start_plugin()
