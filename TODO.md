# Virtual Reactor: TODO

Running list. Check items off, add new ones at the bottom of their section, and note the date when something finishes.
Design lives in [PLAN.md](PLAN.md). Details per area in [docs/plans/](docs/plans/); overall structure in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Flags: **[agy]** = a delegation candidate for Antigravity: large, mechanical, contract fixed, strong oracle ([antigravity-task step 0](docs/AGENT-TASKS.md); run step 0 again before dispatching).
Unflagged items are Claude's: judgment, data, small or precision-critical work. **[codex]** = a Codex review checkpoint; every milestone ends with one.

## Next (planned 2026-09-27, after the M1 GO)

Order matters: M2 replaces the `assumed` inputs that M1's caveats rest on, and the browser track can run in parallel. Owner per antigravity-task step 0 ([board](docs/AGENT-TASKS.md)).

**Track 1: M2, the OpenMC library (Claude; judgment, transport, nuclear data)**
1. [ ] **Open data only.** The ICSBEP handbook is licensed to named users and stays out of this work and the repo (user, 2026-09-27). Sources: the database core maps (element positions for cores 242/246); open JSI papers for fuel geometry and materials (svajger2024 Fig. 16 and Table 1, vavtar2021); public NRC TRIGA documents for the standard GA element; ENDF/B-VIII.0. Cite numbers; don't copy whole tables. Downloaded database files stay out of git.
2. [ ] Create the `openmc-vr` env in WSL Ubuntu from `pipeline/environment.yml` (the agent sandbox already has one; Ubuntu only has `openmc-mcnp`, `openmc-cad`).
3. [ ] TD-06 gate before any sweep: run manifests hash the model content, so a changed model invalidates a run and an interrupted run can't pass as complete. Design Claude, then **[agy]** implementation (oracle: tampered-model and interrupted-run fixtures must fail).
4. [ ] OpenMC model of the JSI core: cores 242 and 246 from the database core maps (element positions and serials in `242.pdf`/`246.pdf`), fresh fuel first. Main caveat: burnup (decades-old elements) biases absolute k-eff; report the offset, and look for published per-element burnup in open JSI papers.
5. [ ] First outputs, each with an existing check:
   - transient-rod integral worth vs the measured rod tables (`s242.pdf`, and `s246.pdf` which was measured on core 244);
   - Λ and β_eff: Λ settles run 3's joint γ/Λ caveat (40 µs assumed);
   - fuel α(T) vs svajger2024 Table 2;
   - k-eff ≈ 1 at the measured critical rod positions in the rod-table headers (core 242: K = 499, R = 500, T and V up, 400 W).
   Then rebuild the per-core libraries with OpenMC values replacing `assumed` rod shapes, and re-run run 3's Part B as a regression.

**Track 2: the browser (parallel)**
6. [ ] C6: Web Worker runtime, clock and command bus (ARCHITECTURE runtime loop). Claude designs the scheduling semantics; parts can then be delegated.
7. [ ] M3 renderer decision (TD-07: primitives now, CSG reuse later), then a three.js scaffold (the dispatcher adds the dependency and lockfile). Then **[agy]** the primitive viewer from the library's `geometry` (A10).
8. [ ] **[agy]** Browser end-to-end check on the synthetic fixture: malformed library, a trip, pause/resume, replay (once C6 exists).

**Housekeeping**
9. [ ] **[agy]** Pre-merge check (TD-03, A9): one script that runs the Python fast tests plus `npm test`/`typecheck`/`build`.
10. [ ] **[codex]** When quota allows: the engine line (pending since 2026-09-26), then the TS port (A6-1) and the per-core library changes; together these close M1's review.
11. [ ] Find the JSI Research Reactor Simulator's source and license (independent comparison, reference only).

**Standalone kinetics engine (decided 2026-09-27: yes, but not before the API settles)**
12. [ ] Rule from now on: keep `physics_ref/` and `web/src/sim/` separable. No imports from views, `pipeline/` or `validation/` except through one small library-loader module.
13. [ ] After C6: define a plain parameter API for the engine (parameters in, state out) and make our library format an adapter over it.
14. [ ] At M9 (open release): split the engine into its own MIT repo (Python and npm packages, the same golden vectors), and make this project depend on it.
    Why it's worth it: an MIT, dependency-free, browser-capable point-kinetics engine with deterministic replay and pulse validation fills a gap
    (PyRK has no license; openpointkinetics is GPL and dormant). Why not yet: the API will change with C6 and M2.

## Now

- [x] 2026-09-26: Downloaded and parsed JSI pulse database (757 pulses from [trigapulse.ijs.si](http://trigapulse.ijs.si/), 1991–2023) into `validation/data/jsi-pulses/` (CSV and JSON summary) with citations, fetch script, loader API (`validation/pulse_loader.py`), unit tests, and TRIGA benchmark parameters (`validation/data/triga-jsi/parameters.json`)
- [x] 2026-09-27: ICSBEP `IEU-COMP-THERM-003` access dropped: licensed to named users, kept out of this work (user). Open-data route instead (Next #1)
- [ ] Create the `openmc-vr` conda env in WSL (clone of `openmc-mcnp` + pytest + jsonschema), then try OpenMC 0.16 there; leave the shared env alone ([TOOLING §2](docs/TOOLING.md)). *(2026-09-27: exists in the agent sandbox (Python 3.11.16, OpenMC 0.15.3); not yet in WSL Ubuntu; see Next #2)*
- [ ] Find the JSI Research Reactor Simulator's source repo, confirm its license, and decide how to use it as an independent comparison
- [x] 2026-09-26: Private GitHub repo [bluetyde/virtual-reactor](https://github.com/bluetyde/virtual-reactor), MIT license detected, first commit `55da9c2`

## Contracts (before M1 code) · from the [architecture review](docs/ARCHITECTURE-REVIEW.md) and [tech-debt register](docs/TECH-DEBT-REVIEW.md)

Review findings are tracked here, one task each. Status of a finding: proposed → accepted → documented → implemented → verified.
Close a task only with evidence (a passing test or a recorded decision); a plan edit alone means "documented", not "verified".
All ten architecture findings and TD-01..09 are **accepted and documented** (2026-09-25); none is implemented yet.

- [x] 2026-09-27 (verified in Python and TS: `physics_ref/tests/test_engine.py`, `pipeline/tests/test_library.py`, `web/src/sim/`): Initialization rules: S = 0 for critical equilibrium, reject ρ ≥ 0 source equilibria, explicit initial precursors, poisons and temperatures ([01](docs/plans/01-physics-core.md))
- [x] 2026-09-27 (verified in Python and TS: `physics_ref/tests/test_engine.py`, `pipeline/tests/test_library.py`, `web/src/sim/`): Reference-state contract: stored reference state and reactivity, tables as deltas, labelled calibration ([03](docs/plans/03-library-format.md))
- [ ] Power, shape and density definitions; tally basis; bin volumes; deposition assumption ([03](docs/plans/03-library-format.md))
- [x] 2026-09-27 (verified in Python and TS: `physics_ref/tests/test_engine.py`, `pipeline/tests/test_library.py`, `web/src/sim/`): Model capabilities (`point-kinetics/lumped-thermal-v1`) and validity statuses with reason codes
- [ ] Command scheduling and acknowledgements, event ordering, trip channel declarations, typed predicate format ([ARCHITECTURE](docs/ARCHITECTURE.md), [05](docs/plans/05-operator-ui.md))
- [x] 2026-09-27 (verified in Python and TS: `physics_ref/tests/test_engine.py`, `pipeline/tests/test_library.py`, `web/src/sim/`): Checkpoint contents, session pins and solver restart boundaries ([06](docs/plans/06-instructor.md))
- [x] 2026-09-27 (verified in Python and TS: `physics_ref/tests/test_engine.py`, `pipeline/tests/test_library.py`, `web/src/sim/`): Binary array descriptors, base vs delta shapes, per-table interpolation and range behavior ([03](docs/plans/03-library-format.md))
- [x] 2026-09-25: Normative [`docs/library-format.md`](docs/library-format.md) v0.1.0 + `schema/library.schema.json` with 28 stable error codes (TD-02: implemented + verified in Python; TypeScript side pending)
- [x] 2026-09-25: Synthetic fixture `schema/vectors/synthetic-core` (generated, deterministic) + 30 invalid fixtures covering every error code; stdlib validator `pipeline/library/validate.py`; 10 tests pass on Windows Python 3.14 and WSL Python 3.11
- [x] 2026-09-26: Initial-state definition in the engine: power `source-equilibrium` / `critical-equilibrium` / `given`, precursors equilibrium or supplied, poisons zero/equilibrium/given; impossible equilibria rejected
- [x] 2026-09-25: Scaffold part 1: `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md`, `.gitattributes` (LF), `.gitignore`, `pyproject.toml` (fast checks need no packages), `pipeline/environment.yml` (`openmc-vr`, pinned)
- [ ] Scaffold part 2: create the `openmc-vr` env from the file; `web/` with a committed `package-lock.json`; CI (or the local pre-merge check) runs the fast tests + web build (TD-03). *(2026-09-27: `web/` + lockfile done (A5-0); env and pre-merge check open: Next #2, #9)*
- [x] 2026-09-26: Headless slice in Python (`physics_ref/`): load → initialize (explicit rules, `E_INIT_*`) → commands with seq/status → advance → snapshot → checkpoint → replay, all bit-identical (TD-05 implemented + verified in Python)
- [ ] Then a minimal panel and primitive viewer (needs the TypeScript port).
      Checkpoint restore must match uninterrupted execution including noise and trips; built with the first stateful runtime, not deferred to M6 (TD-05)
- [x] 2026-09-27: Independent checks (TD-04): perturbed-coefficient tests (`test_wrong_coefficient_breaks_order`, `..._catches_wrong_gamma`), vector self-test (`test_comparison_catches_real_differences`, ported to TS), and targeted breaks during each verification (logged). Golden vectors reproduced by the TS port (A6-1).
- [ ] **[agy]** Basic resource bounds in the first worker and recorder (after C6); an accelerated synthetic session stays within a measured memory budget (TD-08)
- [ ] **[agy]** Browser end-to-end check on the same fixture (Next #8): malformed library, a trip, pause/resume, replay. Only then expand the transport grid
- [ ] Performance budgets on a named reference laptop (Claude sets the budgets; **[agy]** writes the benchmark harness): library memory, load time, command latency, replay latency, solver throughput

## Milestone 1: Physics prototype (Python, no UI) · [plan](docs/plans/01-physics-core.md)

Done 2026-09-26 in `physics_ref/` (25 tests): six-group kinetics with source, lumped fuel/coolant thermal model, table feedback, I/Xe, rods/scram/fire, instruments with lag/noise/faults,
trips (located or sampled) and interlocks. Analytic checks pass: source multiplication, prompt jump, inhour period, Nordheim–Fuchs (0.1%), xenon peak time (1%), energy balance (1e-4).
ROS3P and golden vectors done since; M1 GO on 2026-09-27.

- [x] 2026-09-26: Point-kinetics solver, six delayed groups (ROS2; inhour period and prompt jump checks pass)
- [x] 2026-09-26: Lumped fuel and coolant temperature model with heat removal (adiabatic limit checked by Nordheim–Fuchs)
- [x] 2026-09-26: Fuel temperature feedback from a table (temperature-dependent coefficient)
- [x] 2026-09-26: Built experimental TRIGA-like library (`libraries/triga-jsi/`) via `pipeline/library/build_triga.py`; passes `pipeline.library.validate`. Values relabelled `assumed` after review (unverified; task C2)
- [x] 2026-09-26: First pulse sweep $1.10–2.20 vs pooled JSI bins (`validation/pulse_comparison.py`): sim/exp ratios 0.51–5.92, inconclusive (unscreened, unmatched)
- [x] 2026-09-26: Pulse data screening (A3, `agy/pulse-screening`, verified: 757 = 667 kept + 90 excluded)
- [x] 2026-09-26: C1 condition-matched comparison (`validation/c1_comparison.py`, `docs/validation/m1-c1-results.md`): proposal **NO-GO**; H1 0.614 > 0.405, H2 0.880 > 0.693, s = 2.63 outside [0.5, 2]; slope 3.1–3.8 measured vs 2.0 model
- [x] 2026-09-27: C2: cp(T), α(T), kinetics cited (Vavtar & Snoj 2021, Švajger et al. 2024); fuel mass 2.363 kg/element, cores 242/246 = 59/65 elements; C1 run 2 still NO-GO
- [x] 2026-09-27: C7: the $ labels overstate the prompt excess ($0.27 core 242, $0.42 core 246) per trace rise rates; the steep law was a label artifact (`validation/trace_period.py`)
- [x] 2026-09-27: Run 3 (per-core libraries, trace-derived $, user's criterion): B passes both cores (×1.05 / ×1.03, no calibration); A1 failed by 0.6%, judged mis-specified by the user
- [x] 2026-09-26: Xenon/iodine: equilibrium derivative zero, post-shutdown peak time within 1%
- [x] 2026-09-26: Unit tests for all of the above (`physics_ref/tests/test_engine.py`, `validation/tests/`)
- [x] 2026-09-26: ROS3P (order 3) solver option, ROS2 unchanged (merged). 2026-09-27: `method` kept in pins, vectors regenerated (C5)
- [x] 2026-09-26: Golden vectors (`python -m physics_ref.vectors`), merged; regenerate on Linux Python 3.11 (Windows libm adds last-bit noise)
- [x] 2026-09-27: Go/no-go: **NO-GO** accepted by the user (C1 proposal); an earlier automatic GO was withdrawn (`docs/reviews/2026-09-26-m1-go-review.md`)
- [x] 2026-09-27: **M1 GO** (user decision on run 3, option 2: A1's bound mis-specified, failure kept on record). [Results](docs/validation/m1-c1-results.md)
- [ ] **[codex]** Codex review of M1 (pending, quota): see Next #10

## Milestone 2: OpenMC library · [plan](docs/plans/02-openmc-pipeline.md)

- [ ] **Gate before any large sweep (TD-06):** changing model content invalidates a run; changing only extraction rebuilds derived data; an interrupted run can't be read as complete

- [ ] Build the JSI TRIGA OpenMC model from open data; check k-eff at the measured critical rod positions (Next #1, #4)
- [ ] Integral and differential rod-worth curves for each control rod
- [ ] β_eff and Λ
- [ ] Fuel and coolant temperature coefficients
- [ ] 3D power mesh tallies over the state grid; estimate compute cost first
- [ ] **[agy]** Export script: OpenMC outputs → browser data files (once the library fields are fixed; oracle: `pipeline.library.validate` plus the TS validator)
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 3: Static 3D viewer · [plan](docs/plans/04-3d-explorer.md)

- [ ] Renderer decision recorded (primitives now; CSG reuse later as shared module or vendored snapshot with an update policy), with a focused check of picking, cutaways, moving rods and overlays (TD-07)

- [ ] Vite + three.js scaffold (dispatcher: dependency + lockfile)
- [ ] **[agy]** Load core geometry (fuel elements, rods, reflector, tank) (A10)
- [ ] **[agy]** Colour elements by one power tally
- [ ] **[agy]** Noclip camera, cutaway plane, click-to-inspect (after the renderer decision fixes the picking contract)
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 4: Link simulation and view

- [x] 2026-09-27: Port the simulation core to TypeScript and match the Python results (A6-1: all 6 golden vectors within tolerance, 71 web tests)
- [ ] State snapshot and command interface (C6)
- [ ] **[agy]** Interpolate power shapes by rod height and temperature (port of `Engine.shape()`; oracle: Python shapes on the synthetic core within tolerance)
- [ ] **[agy]** Live 3D updates while rods move
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 5: Operator panel and scenarios · [plan](docs/plans/05-operator-ui.md)

- [ ] **[agy]** Instrument panel (rod positions, linear and log power, period, temperatures, alarms), once the snapshot-to-panel mapping is designed
- [ ] Scram logic and trip setpoints
- [ ] Scenarios: startup, steady power, pulse, scram, xenon transient (format design Claude (A7, on hold); then **[agy]** the schema, validator and fixtures)
- [ ] **[agy]** Split-screen layout and realism toggle
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 6: Instructor view · [plan](docs/plans/06-instructor.md)

- [ ] History buffer, rewind, time speed-up (design Claude: builds on checkpoint/replay; then **[agy]**)
- [ ] **[agy]** Fault injection UI: stuck rod, pump trip, failed instrument (the engine commands exist)
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 7: Validation (stretch) · [plan](docs/plans/07-validation.md)

- [ ] Compare against measured data from a real TRIGA
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 8: Second reactor

- [ ] Choose a second reactor of a different type (open)
- [ ] Build its library with no changes to simulation or view code; record anything that forced a code change
- [ ] **[codex]** Codex review of the milestone's merged diff before closing it (`codex-review` skill; pick the auditor that fits; log it as pending if the quota is out)

## Milestone 9: Open release · [plan](docs/plans/09-open-release.md)

- [ ] Confirm the license (MIT, provisional since 2026-09-25) and check that every reused file is permissive with its notice kept
- [ ] Public repo, README, docs for the library format, library-authoring guide
- [ ] Ship example libraries (TRIGA plus the second reactor)
- [ ] Split the kinetics engine into its own repo (Next #14)
- [ ] **[codex]** Codex review of the whole repo before it goes public (license notices, secrets, data provenance)

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
