# Kitchen 3D

A 3D model of an L-shaped kitchen, built in code with Blender, plus a browser viewer.

Live viewer: https://shkr.github.io/kitchen-3d/

- `blender/kitchen.py` builds the model (in mm), renders the shots and exports `out/kitchen.blend` and `out/kitchen.glb`:
  `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python blender/kitchen.py -- --engine eevee --res 1600`
- `web/build.py` inlines the .glb into `web/viewer.html` to make one self-contained page (`out/kitchen-viewer.html`).
- `web/deploy.sh "<message>"` rebuilds that page and publishes it here as `index.html`.
- `renders/` holds the latest renders.

Measurements are shown in feet and inches. The raised slab over the washing machine (3ft 3in) is an estimate.
