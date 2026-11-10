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

Every section folds away: click its title.

The parts follow this tree. Left and right are the wearer's: left is +X, and the front faces -Y.

```
<SKU>
├─ frame:   front_rim, nose_pad_left/right, nose_bridge, hinge_frame_left/right
├─ lenses:  lens_left/right, rim_left/right
└─ temples
   ├─ temple_left:  temple_left_outer, temple_left_inner, temple_tip_outer_left, temple_tip_inner_left,
   │                hinge_temple_left, screw_left
   └─ temple_right: the same with _right
```

Required: `frame`, `lenses`, `temples`, `front_rim`, `lens_left`, `lens_right`, `temple_left`, `temple_right`, `temple_left_outer` and `temple_right_outer`. The rest are optional.

**Check Model**
- **Check Model:** lists what QA would flag, and changes nothing. A **Fix** button sits beside each problem it can fix; hover it to see what it does and the full list of parts.
  - Top parent and groups missing, or a part in the wrong group. Fix: Set Up Hierarchy.
  - A required part missing, or a name that isn't in the tree. Fix by hand, with Rename Active.
  - A `.001` ending. Fix: removes it, when the plain name is free.
  - A `_left` part sitting on the wearer's right, or the other way round. Fix: swaps left and right in those names.
  - Scale not applied. Fix: applies it.
  - No UV map, or more than one, or not called `UVMap`. Fix: Single UV Map.
  - Not one `Mat_<top parent>` material on every part. Fix: Single Material from Root.
  - Loose verts or edges, n-gons, flipped normals. Fixes: deletes them, triangulates the n-gons, recalculates normals outside.
  - UVs outside 0-1, and UVs overlapping among parts that share a material, including stacked left and right islands. No fix: move the islands yourself.
  - Texel density: the lowest and highest, in px/cm at 2048.
  - A right part that isn't a mirror of its left, as a note, because a logo on one side is fine. Fix: Copy Left to Right.
- Press Check Model again after changing the model by hand.

**Parts**
- **Set Up Hierarchy:** builds the top parent with `frame`, `lenses`, `temples`, `temple_left` and `temple_right`, and moves the selected parts under the right group by name. With nothing selected, it sorts every named part in the scene. Parts stay where they are. It reuses a top parent that is already there, or the active empty; otherwise it names the new one after the `.blend` file, so rename it to the SKU. Selected objects with other names are left alone, and listed.
- **Rename Active:** pick a part name from the list for the active object.
- **Copy Left to Right:** mirrors the active `_left` part, or every `_left` part under it (click `temple_left` for the whole temple), across X onto the `_right` part, replacing its mesh. A missing right part is made. UVs come along too, so the two sides share UV space; Check Model flags the overlap. It refuses meshes with shape keys.
- **Fold Temples:** swings both temples in about their hinges, to check the fold. The hinge is taken as the temple's front outer corner. Back to 0 puts them back exactly, even after Fit to Spec. It is grey while there is Explode data.

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

Compares the task's measurements with the model, live. The file needs one top parent with `frame`, `lenses` and `temples` under it, and parts named `front_rim`, `lens_left`, `lens_right`, `temple_left` and `temple_right`. 1 Blender unit counts as 1 cm, whatever the scene's unit scale says. Parts are measured as shown, so a Mirror or other modifier counts.
- **Load Spec / Save Spec:** Save Spec remembers the measurements and Exact Frame Fit on this computer, under the top parent's name (the SKU). Load Spec fills them back in. They are kept in Blender's config folder, not in the `.blend`.
- **Exact Frame Fit:** on by default. Frame Width must equal its spec at 0.1 mm. Off, it may be ±3 mm.
- **Paste box:** paste a line like `Lens Height 40mm Bridge Width 19mm Temple Length 140mm Frame Width 140mm` to fill the fields, in any order. If it stays in the box, no measurement was found.
- **Frame Width, Bridge, Lens Height, Temple:** type the spec in mm, or leave 0 to skip it. Bridge may be off by ±2, Lens Height ±3 and Temple ±10 mm; Frame Width follows Exact Frame Fit. What the model measures shows beside it, with a dot: green is in range, amber is close to a limit or blocking a fit, red is out, grey is no spec or a missing part. Frame Width is the rim only, so temples that flare past it don't count. Bridge is the gap between the lenses.
- **Lens Width:** a readout, with no spec.
- **Show / Hide Measurements:** draws the lines and values on the model in the 3D view. It adds nothing to the scene or an export.
- **Fit to Spec:** scales the top parent evenly about the world origin. With Exact Frame Fit on, it scales until Frame Width equals its spec exactly. The other measurements scale with it and may land outside their range; the panel shows the factor, the result and any measurement that will be out, first. It doesn't change the mesh or UVs. It's grey when nothing needs scaling, while the top parent is rotated, and while there is Explode data (press **Reset** first). With Exact Frame Fit off, or no Frame Width spec, it brings every measurement into range instead, as close to the exact Frame Width as it can, and if no single scale can, it names the two measurements that clash, so fix the model's proportions.
- Warnings also show for a rotated top parent, a folded temple, overlapping lenses, and left and right sizes more than 0.5 mm apart.
- **Copy Report:** copies the SKU, each spec, what the model measures, its status and the warnings as text, to paste into the task.

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
- **Export for Painter:** writes `<blend name>.fbx` beside the saved `.blend`: the selected objects, or every mesh when nothing is selected, with modifiers applied. Pressing it again overwrites the FBX. Save the Painter project in the same folder under the same name, and Import Textures finds its export without picking a folder.
- **Folder:** the folder Painter exported into. The default, `//`, needs a saved file. It uses `<blend name>\Textures\` beside the `.blend` if that exists, which is where Painter's export goes when the `.spp` has the same name and folder as the `.blend`. Otherwise it uses the `.blend` file's own folder. A folder you pick yourself is used as it is.
- **Normal Map:** untick it before Import Textures to leave the normal map out. To remove one already connected, untick it and press Import Textures again.
- **Import Textures:** connects `<Material>_BaseColor`, `_Roughness`, `_Metallic` (or `_metalness`), `_Normal` and `_Transmissive` to each material with the same name. Capitals don't matter, and neither does a leading `Mat_`, so `Mat_ABC` picks up `ABC_basecolor.png`. It uses the selected objects, or the whole scene if nothing is selected.
- **Reload Textures:** reads already imported images again after a new Painter export. For a new map, press Import Textures. If a file was deleted it warns with the name, and that texture may show pink.
- **Install Painter Export:** copies a small script into Painter's startup folder, replacing an older copy. Restart Painter, then use **File > Export Textures to Project Folder**. It writes every texture set to `<spp folder>\<spp name>\Textures\` as 2048 PNGs with the names Import Textures expects. Tested on Painter 12.1; it needs a Painter version that includes PySide6. The button is grey while Painter already has this version of the script, and comes back when an update changes it or the script is removed.

**Turntable**
- **Turntable:** spins every 3D view around its centre. Press again to stop. Only the view turns; the scene doesn't change.

**Uninstall Modeler Kit:** in Edit > Preferences > Get Extensions (or Add-ons), expand Modeler Kit and press Uninstall Modeler Kit. It asks to confirm, then removes the add-on from Blender. Your scenes are not changed.

## Good to know

- If a button is grey, select a mesh first, or return to Object Mode.
- A material called `Mat_ABC.001` means something else in the file already uses `Mat_ABC`. Import Textures gives both the same textures, so rename one of the top parents and press Single Material from Root again.

## Developers

Build: `python build.py` (the zip goes to `dist/`).

Tests, on Blender 4.5 and 5.2. Run this once for each file in `tests/` (this example runs one of them):

    blender -b --factory-startup --python-exit-code 1 --python tests\test_modelerkit_blender.py
