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

**Dimensions**

Compares the task's measurements with the model, live. The file needs one top parent with `frame`, `lenses` and `temples` under it, and parts named `front_rim`, `lens_left`, `lens_right`, `temple_left` and `temple_right`. 1 Blender unit counts as 1 cm, whatever the scene's unit scale says.
- **Exact Dimensions:** on by default. A measurement must equal its spec at 0.1 mm. Off, these ranges apply: Frame ±3, Bridge ±2, Lens Height ±3, Temple ±10 mm.
- **Paste box:** paste a line like `Lens Height 40mm Bridge Width 19mm Temple Length 140mm Frame Width 140mm` to fill the fields, in any order. If it stays in the box, no measurement was found.
- **Frame Width, Bridge, Lens Height, Temple:** type the spec in mm, or leave 0 to skip it. What the model measures shows beside it, with a dot: green is in range, amber is close to a limit or blocking a fit, red is out, grey is no spec or a missing part. Frame Width is the rim only, so temples that flare past it don't count. Bridge is the gap between the lenses.
- **Lens Width:** a readout, with no spec.
- **Show / Hide Measurements:** draws the lines and values on the model in the 3D view. It adds nothing to the scene or an export.
- **Fit to Spec:** scales the top parent evenly about the world origin until every measurement fits, closest to the exact Frame Width. The panel shows the factor and the result first. It doesn't change the mesh or UVs. It's grey when everything already fits, and while there is Explode data (press **Reset** first). If no single scale can fit, it names the two measurements that clash, so fix the model's proportions.
- Warnings also show for a rotated top parent, a folded temple, overlapping lenses, and left and right sizes more than 0.5 mm apart.

**Close Lens Gap**

For a thin line beside the lens, when the rim's edge loop stops short of it. Click the rim so it is the active object. Lens meshes must be named `lens_...`.
- **Search Distance:** how close a loop must be to a lens to be found on its own. Selecting the loop in Edit Mode ignores this.
- **Offset:** how far past the lens the loop lands. The default, 0, sits exactly on the lens. Raise it only if the line returns; too high shows the flipped band from the front.
- **Check:** measures the gap and moves nothing. If some verts can't reach the lens, it selects them.
- **Close Gap:** slides the loop onto each lens along the rim's own edges, and the UVs follow. In Edit Mode, the selected edges or band of faces decide which loop; otherwise it uses the closest closed loop by each lens. On a rim cut along the lens line, both sides of the cut move together, and selecting one side finds the other. Pressing it again leaves verts already on the lens where they are. It finds which way to go from the faces pointing inward, or the selected band. If there are none, it treats -Y as the front of the frame.
- It never changes the lens or flipped faces. Custom normals can shift slightly.
- If any vert can't reach the lens, nothing moves and those verts are selected. It also refuses a lens with no closed loop, a rim with shape keys, and anything while Explode is above 0.

**UV & Material Names**
- **Single UV Map:** keeps only the active UV map on the selected meshes and names it `UVMap`.
- **Single Material from Root:** gives the selected parts of each product one material, named `Mat_<top parent name>`. Name the top parent after the SKU. A mesh shared by two products with Alt+D is left alone, with a warning, so Import Textures skips it too.

**SP Textures**
- **Folder:** the folder Painter exported into. The default, `//`, needs a saved file. It uses `<blend name>\Textures\` beside the `.blend` if that exists, which is where Painter's export goes when the `.spp` has the same name and folder as the `.blend`. Otherwise it uses the `.blend` file's own folder. A folder you pick yourself is used as it is.
- **Normal Map:** untick it before Import Textures to leave the normal map out. To remove one already connected, untick it and press Import Textures again.
- **Import Textures:** connects `<Material>_BaseColor`, `_Roughness`, `_Metallic` (or `_metalness`), `_Normal` and `_Transmissive` to each material with the same name. Capitals don't matter, and neither does a leading `Mat_`, so `Mat_ABC` picks up `ABC_basecolor.png`. It uses the selected objects, or the whole scene if nothing is selected.
- **Reload Textures:** reads already imported images again after a new Painter export. For a new map, press Import Textures. If a file was deleted it warns with the name, and that texture may show pink.
- **Install Painter Export:** copies a small script into Painter's startup folder, replacing an older copy. Restart Painter, then use **File > Export Textures to Project Folder**. It writes every texture set to `<spp folder>\<spp name>\Textures\` as 2048 PNGs with the names Import Textures expects. Tested on Painter 12.1; it needs a Painter version that includes PySide6. The button is grey while Painter already has this version of the script, and comes back when an update changes it or the script is removed.

**Uninstall Modeler Kit:** in Edit > Preferences > Get Extensions (or Add-ons), expand Modeler Kit and press Uninstall Modeler Kit. It asks to confirm, then removes the add-on from Blender. Your scenes are not changed.

## Good to know

- If a button is grey, select a mesh first, or return to Object Mode.
- A material called `Mat_ABC.001` means something else in the file already uses `Mat_ABC`. Import Textures gives both the same textures, so rename one of the top parents and press Single Material from Root again.

## Developers

Build: `python build.py` (the zip goes to `dist/`).

Tests, on Blender 4.5 and 5.2. Run this once for each file in `tests/` (this example runs one of them):

    blender -b --factory-startup --python-exit-code 1 --python tests\test_modelerkit_blender.py
