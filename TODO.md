# Virtual Reactor: TODO

Running list. Check items off, add new ones at the bottom of their section, and note the date when something finishes.
Design lives in [PLAN.md](PLAN.md). Details per area in [docs/plans/](docs/plans/); overall structure in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Now

- [ ] Download the JSI pulse database ([trigapulse.ijs.si](http://trigapulse.ijs.si/), 493 pulses) into `validation/data/jsi-pulses/` with a citation; ask the listed contact about redistribution terms
- [ ] Get access to the ICSBEP handbook entry `IEU-COMP-THERM-003` (cores 132 and 133) and list what it publishes (k-eff, rod worths, specs)
- [ ] Create the `openmc-vr` conda env in WSL (clone of `openmc-mcnp` + pytest + jsonschema), then try OpenMC 0.16 there; leave the shared env alone ([TOOLING §2](docs/TOOLING.md))
- [ ] Find the JSI Research Reactor Simulator's source repo, confirm its license, and decide how to use it as an independent comparison
- [ ] First commit and private GitHub repo `bluetyde/virtual-reactor` (local `git init` done 2026-09-25; waiting on the user's go-ahead)

## Contracts (before M1 code) · from the [architecture review](docs/ARCHITECTURE-REVIEW.md) and [tech-debt register](docs/TECH-DEBT-REVIEW.md)

Review findings are tracked here, one task each. Status of a finding: proposed → accepted → documented → implemented → verified.
Close a task only with evidence (a passing test or a recorded decision); a plan edit alone means "documented", not "verified".
All ten architecture findings and TD-01..09 are **accepted and documented** (2026-09-25); none is implemented yet.

- [ ] Initialization rules: S = 0 for critical equilibrium, reject ρ ≥ 0 source equilibria, explicit initial precursors, poisons and temperatures ([01](docs/plans/01-physics-core.md))
- [ ] Reference-state contract: stored reference state and reactivity, tables as deltas, labelled calibration ([03](docs/plans/03-library-format.md))
- [ ] Power, shape and density definitions; tally basis; bin volumes; deposition assumption ([03](docs/plans/03-library-format.md))
- [ ] Model capabilities (`point-kinetics/lumped-thermal-v1`) and validity statuses with reason codes
- [ ] Command scheduling and acknowledgements, event ordering, trip channel declarations, typed predicate format ([ARCHITECTURE](docs/ARCHITECTURE.md), [05](docs/plans/05-operator-ui.md))
- [ ] Checkpoint contents, session pins and solver restart boundaries ([06](docs/plans/06-instructor.md))
- [ ] Binary array descriptors, base vs delta shapes, per-table interpolation and range behavior ([03](docs/plans/03-library-format.md))
- [x] 2026-09-25: Normative [`docs/library-format.md`](docs/library-format.md) v0.1.0 + `schema/library.schema.json` with 28 stable error codes (TD-02: implemented + verified in Python; TypeScript side pending)
- [x] 2026-09-25: Synthetic fixture `schema/vectors/synthetic-core` (generated, deterministic) + 30 invalid fixtures covering every error code; stdlib validator `pipeline/library/validate.py`; 10 tests pass on Windows Python 3.14 and WSL Python 3.11
- [ ] Initial-conditions part of the fixture: the library holds the reference state; the explicit initial-state definition (equilibrium or supplied inventories) belongs to the engine and scenarios, next with the headless slice
- [x] 2026-09-25: Scaffold part 1: `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md`, `.gitattributes` (LF), `.gitignore`, `pyproject.toml` (fast checks need no packages), `pipeline/environment.yml` (`openmc-vr`, pinned)
- [ ] Scaffold part 2: create the `openmc-vr` env from the file; `web/` with a committed `package-lock.json`; CI (or the local pre-merge check) runs the fast tests + web build (TD-03)
- [ ] Headless slice: load → initialize → move rod → advance → snapshot → checkpoint → replay; then a minimal panel and primitive viewer.
      Checkpoint restore must match uninterrupted execution including noise and trips; built with the first stateful runtime, not deferred to M6 (TD-05)
- [ ] Independent checks: a deliberately perturbed coefficient or event time must fail an independent test; vector changes need a reason (TD-04)
- [ ] Basic resource bounds in the first worker and recorder; an accelerated synthetic session stays within a measured memory budget (TD-08)
- [ ] Browser end-to-end check on the same fixture: malformed library, a trip, pause/resume, replay. Only then expand the transport grid
- [ ] Performance budgets on a named reference laptop: library memory, load time, command latency, replay latency, solver throughput

## Milestone 1: Physics prototype (Python, no UI) · [plan](docs/plans/01-physics-core.md)

- [ ] Point-kinetics solver, six delayed groups (stiff solver; check against analytic step-response inverse-period values)
- [ ] Lumped fuel temperature model (adiabatic first, then with heat removal)
- [ ] Prompt fuel temperature feedback coefficient
- [ ] Reproduce a TRIGA pulse and compare with published data
- [ ] Add xenon/iodine and check equilibrium xenon worth and the post-shutdown peak time
- [ ] Unit tests for all of the above
- [ ] Go/no-go decision written into PLAN.md

## Milestone 2: OpenMC library · [plan](docs/plans/02-openmc-pipeline.md)

- [ ] **Gate before any large sweep (TD-06):** changing model content invalidates a run; changing only extraction rebuilds derived data; an interrupted run can't be read as complete

- [ ] Build or adapt the TRIGA OpenMC model; check k-eff against the benchmark
- [ ] Integral and differential rod-worth curves for each control rod
- [ ] β_eff and Λ
- [ ] Fuel and coolant temperature coefficients
- [ ] 3D power mesh tallies over the state grid; estimate compute cost first
- [ ] Export script: OpenMC outputs → browser data files

## Milestone 3: Static 3D viewer · [plan](docs/plans/04-3d-explorer.md)

- [ ] Renderer decision recorded (primitives now; CSG reuse later as shared module or vendored snapshot with an update policy), with a focused check of picking, cutaways, moving rods and overlays (TD-07)

- [ ] Vite + three.js scaffold
- [ ] Load core geometry (fuel elements, rods, reflector, tank)
- [ ] Colour elements by one power tally
- [ ] Noclip camera, cutaway plane, click-to-inspect

## Milestone 4: Link simulation and view

- [ ] Port the simulation core to TypeScript and match the Python results
- [ ] State snapshot and command interface
- [ ] Interpolate power shapes by rod height and temperature
- [ ] Live 3D updates while rods move

## Milestone 5: Operator panel and scenarios · [plan](docs/plans/05-operator-ui.md)

- [ ] Instrument panel (rod positions, linear and log power, period, temperatures, alarms)
- [ ] Scram logic and trip setpoints
- [ ] Scenarios: startup, steady power, pulse, scram, xenon transient
- [ ] Split-screen layout and realism toggle

## Milestone 6: Instructor view · [plan](docs/plans/06-instructor.md)

- [ ] History buffer, rewind, time speed-up
- [ ] Fault injection: stuck rod, pump trip, failed instrument

## Milestone 7: Validation (stretch) · [plan](docs/plans/07-validation.md)

- [ ] Compare against measured data from a real TRIGA

## Milestone 8: Second reactor

- [ ] Choose a second reactor of a different type (open)
- [ ] Build its library with no changes to simulation or view code; record anything that forced a code change

## Milestone 9: Open release · [plan](docs/plans/09-open-release.md)

- [ ] Confirm the license (MIT, provisional since 2026-09-25) and check that every reused file is permissive with its notice kept
- [ ] Public repo, README, docs for the library format, library-authoring guide
- [ ] Ship example libraries (TRIGA plus the second reactor)

## Ideas / later

- Share the 3D geometry loader with OpenMC Studio
- Reuse Studio's WebGL2 BVH CSG ray tracer for the explorer (shared module or copied code); decide in M3 ([TOOLING §6](docs/TOOLING.md))
- Update `terrapower/armicontrib-openmc` for current ARMI instead of writing a new plugin (plan 08)
- Contribute the JSI TRIGA model (`IEU-COMP-THERM-003`) to `mit-crpg/benchmarks`, which doesn't have it
- Studio (not this project): check whether MontePy 1.5.0 parses `<` tally chains
- Burnup-dependent parameters from OpenMC depletion
- NE403 demo mode
- ARMI as the offline driver (after milestone 2 works with plain scripts): check for an existing ARMI↔OpenMC plugin, otherwise consider writing one, so any reactor described as an ARMI blueprint can produce a simulator library

## Done

- [x] 2026-09-25: Project folder, README, PLAN and TODO created
- [x] 2026-09-25: Reference core decided (JSI TRIGA); ARCHITECTURE, WORKFLOWS and plans 01–09 written
- [x] 2026-09-25: Codex tech-debt register (TD-01..09) folded in: WORKFLOWS is canonical setup, `VR_PORT`, vector-change rule, resource limits, error codes, milestone gates
- [x] 2026-09-25: Codex architecture review folded into PLAN, ARCHITECTURE, WORKFLOWS, plans 01–07; contracts listed above
- [x] 2026-09-25: License set to MIT (provisional)
- [x] 2026-09-25: Tooling survey (docs/TOOLING.md). Existing simulators checked (JSI already has one; gap statement updated); benchmark ID confirmed `IEU-COMP-THERM-003`; ZrH S(α,β) covers 296–1200 K (no NJOY needed); OpenMC 0.15.3 has IFP tallies
