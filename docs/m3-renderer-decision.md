# M3 renderer decision (TD-07)

Status: **decided for M3 on 2026-09-27** (cloud session), following the direction already set in TODO and [plan 04](plans/04-3d-explorer.md): primitives now, CSG reuse evaluated later.
The spike below is the "focused integration check" that TD-07 asks for: picking, cutaways, moving rods and overlays.
Code: `web/src/views/explorer/`. App: `web/src/app/`.

## Decision

1. **Renderer for M3: three.js `WebGLRenderer` (WebGL2), drawing the library's analytic primitives as meshes.**
   three.js **0.186.1** (r186, MIT) is pinned exactly, with `@types/three` **0.186.0** (MIT) for the types.
2. **A geometry adapter sits between the library and the renderer:** `ViewerModel` (`model.ts`) holds the primitives, rod travel, reference rods and the base shape.
   The viewer never reads the engine's `Library` class. A later renderer (for example Studio's CSG ray tracer) reads the same model.
3. **Picking is exact, on the analytic solids, not on triangles.** The picking contract is below. A CSG ray tracer answers the same question the same way, so the contract survives a renderer change.
4. **CSG reuse (Studio's WebGL2 BVH ray tracer) is deferred to a reuse gate.** Nothing in M3 depends on it. The gate criteria and the record a reuse needs are in the last section.

## Options considered

| Option | For | Against |
|---|---|---|
| **A. three.js meshes from primitives (chosen)** | Small: about 1,000 lines with the UI, controls and picking. The library format has only cylinders, annuli and boxes. Instancing gives few draw calls. Clipping planes and stencil caps are standard three.js. Works with overlays, rods and later effects (glow, X-ray). | Curved surfaces are tessellated (48 segments). A general CSG model (OpenMC cells with arbitrary surfaces) would not fit. |
| B. Reuse Studio's WebGL2 BVH CSG ray tracer | Exact surfaces, general CSG, already scales to 10,000+ parts. | A second codebase to own, before we need general CSG. Depth compositing with three.js meshes, moving rods and per-bin overlays are all integration work. TD-07 asks for a versioned module or a recorded vendored snapshot first. |
| C. Own analytic ray-marching shader | Exact cylinders, and exact cut faces with no stencil. | New GLSL to write and test, harder to mix with meshes and overlays, and no gain over A for this geometry. |

## Spike results (2026-09-27)

Both shipped libraries were checked: the synthetic core (36 primitives) and `triga-jsi-242` (119 primitives, 56 elements, 4 rods).

| TD-07 check | Result | Evidence |
|---|---|---|
| **Picking** | Every element-tagged and rod-tagged primitive of both libraries is picked by its index with a ray from above. In Chromium, a real mouse click on the screen position of element C10 picked primitive #15 (the expected one), and the panel showed its data. | `model.test.ts`; browser run |
| **Cutaways** | One clipping plane on every material. Stencil caps per solid material (not water). A ray into a cut solid enters through the cut face (`onCut`) at the plane. In Chromium, the caps change about 213,000 of 982,000 pixels and show filled cross-sections of the reflector, fuel, cladding, rods and thimble. | `scene.test.ts`, `model.test.ts`; screenshots with caps on and off |
| **Moving rods** | A rod instance moves up by position × travel. Picking follows it: a withdrawn rod is picked at its new height and not at the old one. In Chromium, the withdrawn transient rod shows above the core. | `scene.test.ts`, `model.test.ts`; screenshot |
| **Overlays** | Per-element colour on the fuel instances (viridis, reference power share); other materials keep their colours; the overlay clears. | `scene.test.ts`; screenshot |
| **Draw calls** | 6 for both libraries (one per group of equal primitives); `triga-jsi-242` is about 50,000 triangles. | `scene.test.ts`; app status line |
| **Coordinates** | Library z-up maps to three.js y-up as (x, y, z) → (x, z, −y), with no mirror. Bounds of every drawn primitive match the library to 1e-4 cm (three.js stores float32). | `scene.test.ts` |

Performance: headless Chromium with SwiftShader (software GL) took 0.67 ms of CPU per `render()` call for `triga-jsi-242`.
This is not a GPU frame time, so it does not test the 60 fps target of plan 04. That needs a named reference laptop (TODO "Performance budgets").

The build is 633 KB of JavaScript (166 KB gzipped), nearly all of it three.js. Vite warns about chunks above 500 KB. Code splitting can come with the other views.

## Picking contract

`pick(model, origin, direction, { rods, cut, pickable })` in library coordinates (cm, z up) returns the first primitive the ray enters, or `null`:

- `index`: the primitive's position in `geometry.primitives` (primitives have no `id`; the `element` and `rod` tags come from the model).
- `t` and `point`: the entry distance and point.
- `onCut`: true when the ray enters the solid through the cutaway face.

Rules: rods are at their current positions. The cutaway's removed half-space is ignored. Materials the viewer marks not pickable (water, void) are skipped.
A solid that contains the ray origin is skipped, so from inside a solid (noclip) you pick what is ahead.

## Known limits (follow-ups, not blocking M3)

- **Caps use the material colour,** not the overlay colour, so a cut fuel element shows fuel colour on its cut face.
- **The per-bin overlay (elements × axial bins, plan 04) is not done:** M3 colours whole elements. The per-bin data texture is TODO M3 "Colour elements by one power tally" ([agy]).
- One cutaway plane; no X-ray mode, no Cherenkov glow, no HUD; the rod sliders are view-only until M4 drives them from runtime snapshots.
- The annulus normals are smooth around the ring and sharp at the corners. The shading is good enough for M3.

## Update policy

- **three.js:** pinned exactly in `web/package.json` and the lockfile. An upgrade is a dispatcher decision (web/README).
  Steps: bump both `three` and `@types/three`, run `python3 scripts/premerge.py`, run the explorer in a browser, and compare the views with the screenshots in the PR that did the upgrade.
- **The lockfile is regenerated with npm 11** (the npm that ships with Node 24). npm 10 drops the `libc` fields of the native bindings, which is churn, not a change.

## The later reuse gate (for Studio's CSG ray tracer)

Evaluate reuse only when a library needs geometry that the three primitive types cannot describe, or when the tessellated view is shown to mislead.
At that gate, TD-07 requires one of:
- **A versioned shared module:** a package with a version, a licence and an owner, consumed through `ViewerModel` and the picking contract above.
- **A vendored snapshot:** record the Studio commit, every local change, the required notices, and how upstream fixes get evaluated.

Either way, the result must pass the same checks as this spike (picking by index, cutaways with solid faces, moving rods, overlays) on both shipped libraries.
