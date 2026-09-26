# Plan 04: Explorer view (3D noclip)

The 3D view where you can fly through the reactor and see what the instruments can't.
Milestones: M3 (static viewer using the synthetic library), M4 (live).

## What it shows

- The reactor from the library's render geometry: tank, reflector, grid plates, fuel elements, rods, thimble, detectors.
- Overlays coloured per fuel element and axial bin, chosen from a menu:
  - **Bin power** (shape fraction × live power, W) or **power density** (bin power ÷ bin volume, W/m³). The legend always says which.
  - **Fuel temperature:** v1 has one lumped value, so this is uniform until the thermal model gets nodes. Say so in the UI rather than faking a spatial temperature.
  - **Xenon** (same limitation: core average in v1).
  - **Uncertainty:** the relative uncertainty of each bin, straight from the library.
- **Cherenkov glow:** a blue glow around the core, scaled from live power (log scale).
  It's the visible sign of power in a pool reactor, so it's worth doing well. Pulses produce a bright flash.
- Rods move live, from rod positions in the snapshot.
- A HUD with sim time, power, period and the validity status (`supported` / `unvalidated` / `outOfDomain`, with reasons).

## Camera and controls

| Mode | Controls | Use |
|---|---|---|
| Orbit | Drag to rotate, scroll to zoom, right-drag to pan | Default, and easiest on a laptop |
| Noclip | WASD + mouse look (pointer lock), Q/E down/up, Shift faster | Flying through the core |
| Presets | Number keys: top view, side cutaway, "diver's view" from the pool surface | Teaching, repeatable screenshots |

- **Cutaways:** one or two clipping planes (three.js supports them per material), with a slider for position.
  Clipped solids get capped, so the cut surface looks solid rather than hollow.
- **X-ray mode:** the water, tank and reflector become transparent so the core shows through.
- **Click to inspect:** a raycast returns the element ID. The side panel shows the element's ID, material, bin powers (plus uncertainty), its share of total power and the nearest rod.
  Clicking a rod shows its position and worth. With the instructor's permission, you can drive it from there, but that goes through the command bus like any other view.

## Rendering approach

- **three.js** (r186 as of 2026-09) with **`WebGLRenderer` (WebGL2)**. WebGPU isn't needed at this scene size, and staying on WebGL2 keeps custom GLSL usable.
- **Geometry adapter:** start with the library's **primitives** (enough for the TRIGA), behind an adapter interface.
  Reusing OpenMC Studio's WebGL2 BVH CSG ray tracer is a **separate later evaluation** (picking, cutaways, depth compositing with meshes, moving rods, overlay mapping),
  and must not block the first simulation slice (see [TOOLING.md](../TOOLING.md) §4 and §6).
- Fuel elements use **InstancedMesh**, one draw call for all of them.
  Per-bin colours live in a small **data texture** (elements × axial bins). A shader looks up the colour from each fragment's element index and height.
  An update is one texture upload, not a mesh rebuild.
- **Colour maps:** perceptually uniform ones (viridis/inferno for magnitude, a diverging map for "change from reference").
  Linear/log toggle, and a legend with units that always shows.
- **Performance:** render only when something changes, or while the camera moves or the sim runs.
  Target 60 fps on a normal laptop GPU, and degrade to 30 fps with effects off.

## Data flow

```
library.geometry ──▶ scene builder (once) ──▶ three.js scene
library.shapes   ──┐
snapshot.truth ────┴─▶ shape interpolator ──▶ data texture ──▶ shader
                         (in the worker; sends only when changed)
```

Shape interpolation runs **in the worker**, next to the physics, so the main thread only uploads finished values.

## M3 plan (static, synthetic library)

1. Vite + TypeScript + three.js scaffold in `web/`. Dev port from `VR_PORT` (default 5187; see [WORKFLOWS](../WORKFLOWS.md) section 0).
2. Load `schema/vectors/synthetic-core/` and build the scene from primitives.
3. Colour by the reference shape, with a legend.
4. Orbit camera, then noclip, then cutaway, then click to inspect.
5. Swap in the real TRIGA library as soon as M2 produces one.

## Accessibility and teaching

- Colour-blind-safe maps, and every value you can inspect is also shown as a number.
- Keyboard shortcuts listed in an overlay (`?`).
- Presets and a "screenshot with legend" button, for putting views on NE403 slides.

## Open questions

- Should the explorer model the pool surface and the room, or stop at the tank? Start at the tank. Add the room only if it helps show scale.
- A VR/WebXR mode later? three.js supports it, but it's well past v1.
