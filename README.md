# Modeler Kit

A small Blender add-on for modeling and fixing products. Everything is on one panel.
Works on Blender 4.5 and newer.

## Install

1. In Blender, go to Edit > Preferences > Add-ons.
2. Click the arrow at the top right and choose **Install from Disk**.
3. Pick `modelerkit-<version>.zip`.
4. In the 3D view, press **N** and open the **Modeler Kit** tab.

## Automatic updates

Do this once so Blender updates Modeler Kit by itself:

1. Edit > Preferences > Get Extensions, open the **Repositories** menu (the arrow at the top right) and choose **Add Remote Repository**.
2. Paste `https://raw.githubusercontent.com/msrk0320/ModelerKit/master/dist/index.json`, tick **Check for Updates on Start**, and press Create.
3. Install **Modeler Kit** from that repository. When a new version is out, Blender shows **Update** on it.

## Buttons

**Explode**
- **Explode slider:** spreads the parts apart along the chosen axis, including loose pieces inside a mesh. Move it back to 0 to put everything together. Parts at the same place on that axis that sit apart on the other two, like a left and right pair, move together and stay level.
- **X / Y / Z:** the world axis to spread along. X is the default. You can switch while exploded, and the parts move to the new axis.
- **Selected Only:** the slider moves only what is selected at that moment, and children ride with a selected parent. Turn it on if the file has a head, a floor or a second product.
- **Reset:** puts everything back and removes all explode data from the file.
- You can move a part while it is exploded. The move is kept when the parts come back.
- While exploded, Blender can't apply a modifier to a mesh that was split. Move the slider back to 0 first.

**Lock**
- **Lock Location:** locks the selected objects and their children so they can't be moved by accident. Press again to unlock. This replaces any partial lock a part had of its own.
- Explode still moves locked parts.

**UV & Material Names**
- **Single UV Map:** keeps only the active UV map on the selected meshes and names it `UVMap`.
- **Single Material from Root:** gives the selected parts of each product one material, named `Mat_<top parent name>`. Name the top parent after the SKU. A mesh shared by two products with Alt+D is left alone, with a warning, so Import Textures skips it too.

**SP Textures**
- **Folder:** the folder Painter exported into. The default, `//`, needs a saved file. It uses `<blend name>\Textures\` beside the `.blend` if that exists, which is where Painter's export goes when the `.spp` has the same name and folder as the `.blend`. Otherwise it uses the `.blend` file's own folder. A folder you pick yourself is used as it is.
- **Normal Map:** untick it before Import Textures to leave the normal map out. To remove one already connected, untick it and press Import Textures again.
- **Import Textures:** connects `<Material>_BaseColor`, `_Roughness`, `_Metallic` (or `_metalness`), `_Normal` and `_Transmissive` to each material with the same name. Capitals don't matter, and neither does a leading `Mat_`, so `Mat_ABC` picks up `ABC_basecolor.png`. It uses the selected objects, or the whole scene if nothing is selected.
- **Reload Textures:** reads already imported images again after a new Painter export. For a new map, press Import Textures. If a file was deleted it warns with the name, and that texture may show pink.
- **Install Painter Export:** copies a small script into Painter's startup folder, replacing an older copy. Restart Painter, then use **File > Export Textures to Project Folder**. It writes every texture set to `<spp folder>\<spp name>\Textures\` as 2048 PNGs with the names Import Textures expects. Tested on Painter 12.1; it needs a Painter version that includes PySide6.

**Uninstall Modeler Kit** (bottom of the panel): asks to confirm, then removes the add-on from Blender. Your scenes are not changed.

## Good to know

- If a button is grey, select a mesh first, or return to Object Mode.
- A material called `Mat_ABC.001` means something else in the file already uses `Mat_ABC`. Import Textures gives both the same textures, so rename one of the top parents and press Single Material from Root again.

## Developers

Build: `python build.py` (the zip goes to `dist/`).

Tests, on Blender 4.5 and 5.2. Run this once for each file in `tests/` (this example runs one of them):

    blender -b --factory-startup --python-exit-code 1 --python tests\test_modelerkit_blender.py
