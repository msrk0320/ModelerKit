# Modeler Kit to-do

Everything from the 1.8.0 list is built and tested headless on Blender 4.5.

## Still to check in a real Blender window

- The folding sections on the panel, and the Fix buttons' hover text.
- **Turntable:** the spin itself (headless has no 3D view).
- **Check Model** speed on a heavy model: about 5 s at 100k triangles.

## Ideas

- Copy Left to Right keeps the right part's own UVs only when its faces still match the mirror one for one; otherwise
  the two sides stack. It could pack the right side's islands into free UV space instead.
