# Plan 03: Reactor library format

> **The normative definition is now [../library-format.md](../library-format.md) (v0.1.0) and `schema/library.schema.json`.** This plan is design background; where they differ, the spec wins.

The open format that describes one reactor for the runtime.
It's the most important contract in the project, so it's designed first (v0) and changed carefully.
The final spec will be `docs/library-format.md`, with the machine-checkable version at `schema/library.schema.json`.

## Goals

- **Complete:** the runtime needs nothing else to simulate and display the reactor.
- **Tool-neutral:** nothing assumes OpenMC. An MCNP, Serpent or ARMI pipeline could produce it.
- **Small and fast to load:** JSON for structure, raw binary for big arrays. A TRIGA library should be a few MB.
- **Honest:** every number carries its source and, where one exists, its uncertainty. Every table records its valid range.

## Container

A folder, or the same folder zipped (`.vrlib`):

```
triga-jsi/
  manifest.json          everything except big arrays
  arrays/
    shapes.f32           power shapes, little-endian float32
    shapes_unc.f32       relative uncertainties
  geometry/
    render.json          render geometry (primitives), or
    meshes/*.glb         triangle meshes (later)
  validation/
    report.json          results produced by plan 07
  README.md              human description, sources, license of the data
```

## `manifest.json` sections (v0 draft)

```jsonc
{
  "schemaVersion": "0.1.0",
  "capabilities": ["point-kinetics/lumped-thermal-v1"],       // required model capabilities
  "reference": {                                              // every table below is a delta from this state
    "rods": { "transient": ..., "...": ... }, "Tfuel": ..., "Tcoolant": ..., "xenon": ...,
    "rho": { "value": ..., "unc": ..., "source": "transport" },
    "calibration": null                                         // or { "deltaRho": ..., "reason": "..." }, always labelled
  },
  "id": "triga-jsi",
  "name": "JSI TRIGA Mark II (benchmark core)",
  "provenance": {
    "generator": "virtual-reactor pipeline 0.1.0",
    "transportCode": "OpenMC x.y.z",
    "nuclearData": "ENDF/B-VIII.0",
    "model": "pipeline/models/triga_jsi.py @ <git hash>",
    "sources": [ { "id": "icsbep", "cite": "..." } ],
    "created": "2026-..."
  },

  "kinetics": {
    "beta":   { "values": [..6], "unc": [..6], "source": "..." },   // β_i (effective)
    "lambda": { "values": [..6], "source": "..." },                  // 1/s
    "genTime":{ "value": ..., "unc": ..., "source": "..." },         // Λ, s
    "sourceStrength": { "value": ..., "source": "..." }              // S, W-equivalent/s
  },

  "reactivity": {
    // (the reference reactivity lives in "reference" above; no separate "excess" field)
    "rods": [
      { "id": "transient", "name": "Pulse rod",
        "worth": { "x": [0, 0.1, ...], "rho": [...], "unc": [...] },  // integral worth vs fraction withdrawn
        "travelCm": ..., "speed": ...,                                // cm; fraction/s
        "scram": { "t": [...], "x": [...] },                          // position vs time after scram
        "fire":  { "withdrawTime": ... } }                            // only for pulse-capable rods
    ],
    "fuelTemp":    { "T": [...], "rho": [...], "unc": [...] },       // K → Δk/k, relative to reference
    "coolantTemp": { "T": [...], "rho": [...] },
    "xenon":       { "N": [...], "rho": [...] }                      // atoms/m³ → Δk/k
  },

  "thermal": {
    "fuel":    { "mass": ..., "cp": { "T": [...], "c": [...] } },
    "coolant": { "mass": ..., "cp": ... },
    "hA": ... /* optional exponent, dTRef: see library-format.md section 8 */, "heatExchanger": { "maxRemoval": ..., "model": "..." },
    "reference": { "Tfuel": ..., "Tcoolant": ... }
  },

  "poisons": {
    "fluxPerWatt": ..., "sigmaF": ..., "gammaI": ..., "gammaXe": ...,
    "lambdaI": ..., "lambdaXe": ..., "sigmaXe": ...
  },

  "plant": {
    "modes": ["steady", "pulse", "squareWave"],
    "trips":  [ { "signal": "power", "above": ... }, { "signal": "fuelTemp", "above": ... } ],
    "interlocks": [ { "id": "pulse-power-limit", "rule": "mode == 'pulse' requires power < ..." } ],
    "instruments": [ { "id": "linear", "signal": "power", "range": [..], "lag": ..., "noise": ... } ],
    "pumps": [ { "id": "primary", "affects": "heatExchanger" } ]
  },

  "shapes": {
    "bins": {
      "elements": ["B1", "C1", "..."],          // stable element IDs, also used by the geometry
      "axialEdgesCm": [...],
      "volumesCm3": [...]                     // per bin; needed for densities
    },
    "basis": "heating",                       // or "fission"; one per library
    "normalization": "fraction-of-total-power",
    "form": "separable",                        // or "grid"
    "reference": { "offset": 0 },               // byte offsets into shapes.f32
    "rodDeltas": { "transient": { "x": [...], "offsets": [...] }, "...": {} },
    "tempDelta": { "T": [...], "offsets": [...] },
    "validity": { "rods": {...}, "Tfuel": [..., ...],
                  "jointChecked": [ { "rods": {...}, "maxShapeErr": ..., "rhoErr": ... } ] }  // where superposition was actually tested
  },

  "geometry": { "render": "geometry/render.json", "units": "cm", "up": "z" },
  "validation": { "report": "validation/report.json" }
}
```

Every number above marked `...` comes from the pipeline or a cited source. **Nothing is made up and none is a placeholder in a shipped library.**

## Quantities and arrays

- **Shape entries are dimensionless fractions** of the modeled power. `P × fraction` is bin power in W. **Power density** additionally divides by the bin volume (W/m³).
- **Base shapes sum to 1. Delta arrays sum to 0.** A reconstructed shape must be finite, non-negative within a stated round-off tolerance, and normalized.
  Substantial negative values are a **failed approximation** and are reported, never clipped and renormalized in silence.
- **Every binary array has a descriptor:** file, SHA-256 digest, byte length, element type (`float32`), endianness (little), dimensions, order (C, element-major), offset.
  Loaders check bounds, finiteness, duplicate element IDs, element IDs missing from the geometry, missing files and non-monotonic tables.
  Zipped libraries have a size limit and only contained relative paths.
- **Each table declares its interpolation** (linear or monotone spline) and **out-of-range behavior** (`clamp-and-flag`, `extrapolate-and-flag` or `reject`).
- **Uncertainty** fields mean transport sampling uncertainty only, unless a field says interpolation or model error is included.
  Bins normalized together are correlated, so they aren't treated as independent.
- **Size is a target, not a guarantee:** two float32 arrays with N states and B bins take `8 × N × B` bytes. Measure real libraries against the budget.

## Render geometry

The runtime doesn't evaluate OpenMC's CSG. It gets geometry it can draw.

- **v0: primitives.** A list of cylinders, annuli and boxes, each with a material tag, an optional element ID and a transform.
  TRIGA is almost all cylinders, so this covers it exactly. The pipeline generates it from the same parameter dict as the OpenMC model.
- **Later, for any reactor:** a generic converter samples the OpenMC geometry with `openmc.lib.find_cell`.
  It builds triangle meshes per material (marching cubes) and writes glTF.
  This works for arbitrary CSG, and it's also the piece that could be shared with OpenMC Studio.
- Material tags map to display styles (fuel, clad, graphite, water, B₄C, steel) in the viewer, not in the library.

## Versioning rules

- `schemaVersion` follows semver. Optional fields are a **minor** bump. Removing or changing the meaning of a field is a **major** bump.
- **During 0.x, the runtime accepts only an explicit list of supported versions.** After 1.0: one major version, any minor up to what it knows, unknown fields ignored with a warning.
- Schema version and model capabilities are separate. A valid file needing an unsupported capability is rejected with that reason.
- `schema/vectors/` includes a tiny synthetic library for each version, used by tests on both sides.

## Normative spec and error codes

`docs/library-format.md` plus `schema/library.schema.json` are the **only normative definition**. Plans and code link to them instead of restating fields.
Semantic checks use **stable error codes** (e.g. `E_REF_NONZERO`, `E_SHAPE_NEGATIVE`, `E_OFFSET_BOUNDS`, `E_CAPABILITY_UNSUPPORTED`) shared by Python and TypeScript.
TypeScript types are generated from the schema where practical; semantic checks still need tests in both languages. No general schema-generation platform.

## Validation tools

- `pipeline/library/validate.py` and the matching `web/src/library/validate.ts` both check the JSON Schema.
  They also check what a schema can't: tables must be monotonic where needed, array lengths must match their bins, base shapes sum to 1 and deltas sum to 0, and every reconstruction at the grid points is non-negative.
- The builder refuses to write a library that fails validation, and publishes from a staging folder only after everything passes.
- `schema/vectors/` holds **valid and invalid** fixtures (bad offsets, unsupported capability, invalid reconstruction, unequal-volume bins).
  Python and TypeScript must give the same accept/reject decision and reason code for each.

## The synthetic test library

For M3 (viewer) and early M4, there's a small **fake reactor** with made-up but self-consistent numbers,
clearly labelled synthetic: `schema/vectors/synthetic-core/`.
It lets UI work start before OpenMC results exist, and it's the only place invented numbers are allowed.

## Open questions

- Store shapes as float16 to halve their size? Probably unnecessary for TRIGA. Revisit for large cores.
- Where do facility-specific plant numbers go (rod speeds, trip setpoints) when there's no published source?
  Proposal: allow them, but only with `"source": "assumed"`, and show that in the UI.
- Should uncertainty be propagated live (e.g. ± bands on the power plot)? Nice for teaching, but not v1.
