# Virtual Reactor: Plan

Detailed documents:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the parts fit together (components, interfaces, runtime loop, conventions, repo layout, dependency graph)
- [docs/TECH-DEBT-REVIEW.md](docs/TECH-DEBT-REVIEW.md): Codex's tech-debt register TD-01..09 (2026-09-25), tracked in TODO
- [docs/ARCHITECTURE-REVIEW.md](docs/ARCHITECTURE-REVIEW.md): Codex's review (2026-09-25). Its findings are folded into the documents below and tracked in TODO under "Contracts"
- [docs/TOOLING.md](docs/TOOLING.md): every repo and tool in use or considered, installed versions, existing simulators, and upgrade/reuse candidates (surveyed 2026-09-25)
- [docs/WORKFLOWS.md](docs/WORKFLOWS.md): step-by-step procedures (building a library, changing physics, web work, scenarios, new reactors, releases, multi-agent rules)
- [docs/plans/](docs/plans/): one plan per area: [01 physics core](docs/plans/01-physics-core.md), [02 OpenMC pipeline](docs/plans/02-openmc-pipeline.md),
  [03 library format](docs/plans/03-library-format.md), [04 3D explorer](docs/plans/04-3d-explorer.md), [05 operator UI](docs/plans/05-operator-ui.md),
  [06 instructor](docs/plans/06-instructor.md), [07 validation](docs/plans/07-validation.md), [08 ARMI](docs/plans/08-armi-integration.md), [09 open release](docs/plans/09-open-release.md)

## Goal

An **open reactor modeller**: open-source software where anyone can take a reactor model,
generate its physics library with OpenMC, and then run it live in the browser.
They can operate it from a control room or fly through the core and watch the 3D power distribution respond.

The TRIGA Mark II is the **first test case**, not the product.
Any reactor that fits a **supported model capability** (v1: `point-kinetics/lumped-thermal-v1`) needs only new input data, no code.
A reactor that needs different physics needs a new capability, which is legitimate code work, not a broken promise.
Later, checking the TRIGA against measured data from a real reactor proves that the method works.

## Design principles

- **Reactor-agnostic from the start.** No TRIGA constants in the simulation or view code.
  Everything reactor-specific comes from the library file (geometry, rods, kinetics parameters, feedback coefficients, power shapes, trip setpoints).
- **An open, documented library format.** This format is the contract between the offline side (OpenMC, maybe ARMI) and the live side (browser).
  Anyone can produce a library with their own tools.
- **Open source under the MIT license** (provisional, chosen 2026-09-25; matches OpenMC). Final check before the first outside contribution.
- **Honest about accuracy.** Each library declares the capabilities it needs and the domain it was checked over (including joint rod states, not only single-axis ranges).
  The runtime reports a validity status (`supported`, `unvalidated`, `out-of-domain`) with reason codes, not just a range warning.

## Why it's worth building

| Existing tool | Good at | Missing |
|---|---|---|
| **JSI Research Reactor Simulator** (for the same TRIGA) | Point kinetics, xenon, feedback for this exact reactor; source on GitHub | Windows desktop only, hand-built for one reactor, no 3D core, no OpenMC link |
| Web simulators (TH462/Reactor-Dynamics; whatisnuclear's design doc) | Run in the browser (whatisnuclear never got past design) | Hand-set parameters, no transport data, no 3D core; copyleft or unbuilt |
| IAEA basic-principles simulators | Full plant behavior for training | Closed, Windows-only, 2D panels, can't load your own model |
| Commercial full-scope simulators | Exact plant replicas | Proprietary, expensive |
| PyRK and other point-kinetics codes | Correct time-dependent physics | No UI, no geometry |
| OpenMC plus its plotter or ParaView | Detailed 3D geometry and flux | Steady-state only, not interactive |
| MOOSE, Griffin and similar | Full 3D coupled transients | Cluster-scale, hours per run, not interactive |

The gap: point-kinetics simulators exist, including one for the JSI TRIGA itself.
What doesn't exist is an open, browser-based tool that turns **any OpenMC model** into a live, operable reactor
with a 3D core showing transport-computed power shapes. The new parts are the library format and the OpenMC → library pipeline, not the kinetics.

Surveyed 2026-09-25. Details, licenses and the full tool list are in [docs/TOOLING.md](docs/TOOLING.md).

## Core technique: precomputed shapes, live amplitude

1. **Offline (OpenMC, slow):** run the reactor over a grid of states (rod heights, fuel temperature, maybe xenon).
   Record k-eff, kinetics parameters and a 3D mesh tally of power at each state.
2. **Live (browser, fast):** point kinetics gives the total power over time.
3. **Combine:** interpolate the stored power shape for the current state and scale it by the live power.

This is close to the quasi-static method.
It fails when the flux shape changes faster than the grid can follow, or when the true state falls outside the grid.
Document those limits in the app.

## Architecture

The simulation is separate from every view.

```
         commands (move rod, scram, set pump)
  Views ─────────────────────────────────────▶ Simulation core
    ▲                                              │
    └──────────── state snapshot (N Hz) ◀──────────┘
```

- **Simulation core (headless):** point kinetics, thermal model, xenon/iodine, scram logic, fault injection.
  Deterministic given the same inputs and seed, so tests and rewind work.
- **State snapshot:** power, period, reactivity broken down by source, rod heights, temperatures, alarms, sim time.
- **History buffer:** past snapshots, used for rewind and plots.
- **Data library:** OpenMC outputs converted to compact files the browser loads (JSON plus binary mesh arrays).

## Views

All views read the same live state. None of them owns the physics.

1. **Operator:** instruments only (rod position indicators, linear and log power, period, temperatures, alarms, scram).
   You can't see inside the core.
2. **Explorer (noclip):** free-fly 3D camera, cutaways and see-through walls.
   Overlays for power, fuel temperature, flux and xenon. Click any element to inspect it.
3. **Instructor (later):** pause, rewind, time speed-up, and fault injection (stuck rod, pump trip, failed instrument).

Default layout: split screen, operator panel plus a live 3D inset, with a key to swap them.
A realism toggle hides the 3D inset during scenarios.

## Tech choices (tentative)

- **Offline pipeline:** Python and OpenMC in a dedicated WSL2 conda env `openmc-vr` (cloned from `openmc-mcnp`, which stays untouched), ENDF/B-VIII.0 at `/root/nuclear_data`.
- **Simulation core:** TypeScript, so it runs in the browser with no server.
  Prototype the physics in Python first for milestone 1, then port it and check the port against the Python version.
- **3D:** three.js.
- **UI and build:** Vite, matching the other web projects.
- **Relation to OpenMC Studio:** separate project.
  Studio builds and runs OpenMC models. This project turns a finished model into something you can operate live.
  A possible link: Studio gets an "export simulator library" button. Possibly share the geometry-to-3D loader too.
- **ARMI:** a strong candidate for the "any reactor" input side (describe a design as a blueprint, sweep it, write a library).
  Start with plain OpenMC scripts, then bring in ARMI once the library format is stable.

## First test case: TRIGA Mark II

- Small and well documented, with published benchmark models.
- Pulse operation is an ideal demo: a large reactivity step, a millisecond power spike, then shutdown by the fuel temperature coefficient.
- Measured pulse data exists for validation, and many universities run TRIGAs.

## Milestones

1. **Physics prototype (no UI).** Point kinetics plus fuel temperature feedback, reproducing a TRIGA pulse
   (peak power, pulse width, energy released) against published data. This is the go/no-go check.
   
   **Status (2026-09-27): GO for M1 as redefined by the user** ([run 3](docs/validation/m1-c1-results.md), protocol [m1-run3-protocol.md](docs/validation/m1-run3-protocol.md)).
   With cited inputs and no calibration, the engine reproduces the published pulse model within 3% and each core's measured peak powers within about 5%
   (cores 242 and 246, on the trace-derived $ axis, $1.30–1.75). Check A1 failed by 0.6% at $1.5; the user judged its bound mis-specified (delayed-neutron
   return raises the peak above Fuchs–Hansen, documented in the repo before the run), and the failure stays on record.
   The history below (C1 NO-GO, C2, C7) explains how the criterion and the $ axis changed.
   - Code verification passed: the engine matches Nordheim–Fuchs to < 0.1% under its assumptions, plus the other analytic checks (`physics_ref/tests/`).
   - A first comparison with the JSI pulse database (`validation/pulse_comparison.py`) gave sim/exp median peak-power ratios of 0.51–5.92
     across $1.10–2.20, with disagreeing scaling exponents. It pooled 31 core configurations without screening or condition matching,
     and the library's values are unverified estimates. So it can't decide validity either way.
   - An earlier "GO" (commit `0903af4`) rested on the single $2.00 point and was withdrawn after review: `docs/reviews/2026-09-26-m1-go-review.md`.
   - **C1 done (2026-09-26), proposal: NO-GO for M1 as stated** ([results](docs/validation/m1-c1-results.md), protocol fixed in advance).
     Held-out core 246 errs by ×1.85 typical after a one-parameter calibration, and core 242 by ×2.4; the calibration had to go outside its allowed range.
     Measured peak power grows as (ρ−$1)^3.1–3.8, the model as ^2.0 (Nordheim–Fuchs). The leading hypothesis is too-weak temperature dependence
     of the assumed UZrH heat capacity and feedback (Fuchs–Hansen regime). Next: C2 (real cp(T), α(T)), then re-run C1 unchanged. The decision is the user's.
2. **OpenMC library.** TRIGA model, then rod-worth curves, β_eff, Λ, temperature coefficients,
   and 3D power shapes over the state grid.
3. **Static 3D viewer.** Load the geometry and one power tally, colour the core by power, noclip camera.
4. **Link them.** Move rods, power responds, the 3D view updates live.
5. **Operator panel and scenarios.** Startup, steady power, pulse, scram, xenon transient after a power drop.
6. **Instructor view.** Rewind, time speed-up, fault injection.
7. **Validation (stretch).** Compare against measured TRIGA data, ideally from a reactor the user can access.
8. **Second reactor.** Build a library for a different kind of reactor (for example a PWR assembly-level core or a small modular design)
   using only new input data and no code changes. This proves the tool is general. Which reactor is still open.
9. **Open release.** Public repo, docs for the library format, a library-authoring guide, example libraries.
   Consider the ARMI route to libraries here.

## Open questions

- License: **MIT for now** (decided 2026-09-25). Revisit only if a reason appears: e.g. Apache-2.0 for its patent grant, or GPL if we ever need to reuse GPL code.
- What types of reactors should the library format cover? Point kinetics suits small, tightly coupled cores.
  Large cores with shifting flux shapes may need more shape dimensions or a warning.

- Reference core: **decided, the JSI TRIGA Mark II (Ljubljana) benchmark** (the user chose TRIGA because it's so well known). UTK has no research reactor, so validation uses published data.
- How fine the state grid needs to be (rod steps × temperatures), and how much OpenMC time that costs.
- Whether xenon needs its own shape dimension, or whether amplitude alone is enough at TRIGA power levels.
- Hosting: a local-only app, or a published artifact for NE403 demos?
