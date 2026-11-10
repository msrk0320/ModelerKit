# Modeler Kit to-do

Ideas for the next release (1.8.0). None of these are built yet.

## Features

Each one needs a test in `tests/` and a README entry.

1. **Check Model:** one button listing wrong part names, missing `frame`/`lenses`/`temples`, unapplied scale, extra UV maps, missing or duplicate materials, flipped normals, loose verts, n-gons, with a fix button beside each.
2. **Set Up Hierarchy:** builds the top parent with the three groups and sorts the selected parts into them.
3. **Rename Parts:** click `front_rim`, `lens_left`, `temple_right` and so on instead of typing.
4. **Left/Right check:** flags a `_left` part sitting on the right side (can live inside Check Model).
5. **Mirror check and Copy Left to Right.**
6. **UV check:** overlaps, islands outside 0-1, plus a texel density readout.
7. **Export for Painter:** FBX written beside the `.blend`, matching the folder Import Textures reads.
8. **Spec presets** by SKU (stored locally, never in the repo) and **Copy Report** for Dimensions.
9. **Fold / Unfold Temples** slider.
10. **Collapsible sections** on the panel.
11. **Turntable preview:** needs a real Blender window to check, so do this one last.

## Wiring for every new button

- Add the module to `MODULES` in `modelerkit/__init__.py` and to the section list in `modelerkit/panel.py`.
- Add the new operator and property ids to `test_every_button_on_the_panel_exists` in `tests/test_modelerkit_blender.py`, or it fails.
- Add an undo test there for each button that changes the scene.

## Release

- Bump `version` in `modelerkit/blender_manifest.toml` to 1.8.0 (new buttons = minor).
- Run all tests on 4.5 and 5.2, then `python build.py`.
- Commit source, `dist/index.json` and the new zip together.
