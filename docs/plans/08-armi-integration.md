# Plan 08: ARMI integration (later)

Using TerraPower's ARMI as a second, more general way to produce libraries.
It isn't on the critical path. Start only after M2 works with plain scripts and the library format has settled.

## Why

With plain scripts, each new reactor needs a hand-written OpenMC model and run config.
ARMI already has a standard way to describe reactors (blueprints: core, assemblies, blocks, components on hex or Cartesian grids)
and a plugin system for driving analysis codes. An ARMI route would make "any reactor → library" a matter of writing a blueprint.

## What to check first (decision gate)

1. **Is there an ARMI ↔ OpenMC plugin?** **Answered 2026-09-25: yes, [terrapower/armicontrib-openmc](https://github.com/terrapower/armicontrib-openmc)** (Apache-2.0).
   It builds OpenMC models from ARMI hex or Cartesian reactors and reads results back, but "only supports a subset of OpenMC geometries".
   It's thin (4 commits) and was last pushed 2025-09-24, while ARMI itself is at 0.6.4 and very active.
   So the likely work is **updating it for current ARMI and extending it for TRIGA**, then offering the changes upstream.
2. **Can ARMI describe a TRIGA well?** TRIGA fuel sits on a hexagonal lattice of rings, so the grid fits.
   Check how blueprints handle graphite dummy elements, the central thimble, control rods with followers and the pool.
3. **How mature and active is ARMI now?** Release cadence, Python version support, license.

Write the findings here and decide: **use** / **write a plugin** / **skip for now**.

## If we go ahead

```
 ARMI blueprint ──▶ ARMI reactor object ──▶ [plugin] ──▶ OpenMC model ──▶ existing pipeline (runs → extract → build)
```

- The plugin's job is only **ARMI reactor → `openmc.Model`** plus a parameter mapping (rod positions, temperatures).
  Everything after that is the existing pipeline, unchanged.
- **Test:** the JSI TRIGA through the ARMI route must reproduce the plain-script library within statistical noise.
- **Second reactor (M8):** a design that's easier to describe in ARMI than by hand is where the ARMI route pays off.
- If the plugin is general, it's worth offering to the ARMI project as a contribution.

## Risks

- ARMI is large and its design assumptions come from fast reactors. Fitting a small thermal pool reactor into it may take more work than it saves.
- Two model routes can drift apart. The TRIGA cross-check keeps them honest.
