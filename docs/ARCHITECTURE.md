# Architecture

This document explains how the parts of the project fit together.
Detailed plans for each part are in [plans/](plans/). Day-to-day procedures are in [WORKFLOWS.md](WORKFLOWS.md).

## The big picture

There are two halves, joined by one file format.

```
 OFFLINE (slow, Python, WSL2)                          RUNTIME (fast, TypeScript, browser)
 ─────────────────────────────                         ──────────────────────────────────────
                                                        ┌──────────────── Web Worker ───────────┐
 Reactor model ──▶ Run planner ──▶ OpenMC runs          │  Clock ──▶ Simulation core            │
 (OpenMC Python,     (state grid,     (statepoints)      │            (kinetics, thermal,        │
  later ARMI)         budget)              │             │             xenon, rods, trips)        │
                                           ▼             │                 │                      │
                                     Extractor           │                 ▼                      │
                                   (k, β, Λ, shapes)     │        Instrument layer                │
                                           │             │     (detectors, noise, faults)         │
                                           ▼             └───────┬──────────────────▲────────────┘
                                   Library builder               │ state snapshots  │ commands
                                           │                     ▼   (30–60 Hz)     │
                                           ▼             ┌───────────────────────────┴──────────┐
                                ┌────────────────────┐   │  Main thread: views                  │
                                │  REACTOR LIBRARY   │──▶│  Operator · Explorer (3D) ·          │
                                │  (open format)     │   │  Instructor · Plots                  │
                                └────────────────────┘   └──────────────────────────────────────┘
                                           ▲
                                           │ validated against
                                 Validation suite (benchmarks, measured data, analytic tests)
```

**The library is the only connection between the halves.**
The runtime never runs OpenMC, and the offline side knows nothing about the UI.
Anyone can make a library with any tool as long as it matches the schema.

## Components

| Component | Language | Where | Role | Plan |
|---|---|---|---|---|
| Reactor model | Python (OpenMC API) | `pipeline/models/` | Geometry, materials, settings for one reactor | [02](plans/02-openmc-pipeline.md) |
| Run planner and runner | Python | `pipeline/runs/` | Builds the list of OpenMC cases from a config, runs them, resumes after interruption | [02](plans/02-openmc-pipeline.md) |
| Extractor | Python | `pipeline/extract/` | Turns statepoints into k, rod worths, β, Λ, coefficients, shapes | [02](plans/02-openmc-pipeline.md) |
| Library builder and validator | Python | `pipeline/library/` | Writes and validates the library | [03](plans/03-library-format.md) |
| Reference physics | Python | `physics_ref/` | Readable, well-tested version of the simulation; the source of truth | [01](plans/01-physics-core.md) |
| Schema and test vectors | JSON | `schema/` | Library JSON Schema, command and state types, golden results shared by Python and TS | [03](plans/03-library-format.md) |
| Simulation core | TypeScript | `web/src/sim/` | Port of the reference physics; runs in a Web Worker | [01](plans/01-physics-core.md) |
| Instrument layer | TypeScript | `web/src/instruments/` | What the operator is allowed to see: detector ranges, lag, noise, failures | [05](plans/05-operator-ui.md) |
| Explorer view | TypeScript + three.js | `web/src/views/explorer/` | Noclip 3D view with overlays | [04](plans/04-3d-explorer.md) |
| Operator view | TypeScript | `web/src/views/operator/` | Control panel and scenarios | [05](plans/05-operator-ui.md) |
| Instructor view | TypeScript | `web/src/views/instructor/` | Time control, rewind, fault injection | [06](plans/06-instructor.md) |
| Validation suite | Python | `validation/` | Tests at every level, plus reports | [07](plans/07-validation.md) |
| ARMI adapter (later) | Python | `pipeline/armi/` | ARMI blueprint → OpenMC model → library | [08](plans/08-armi-integration.md) |

## Interfaces

Everything connects through four contracts. Each gets a schema in `schema/` and versioned valid **and invalid** conformance fixtures.
Status: the **library** contract exists ([library-format.md](library-format.md), `schema/library.schema.json`, `schema/vectors/`); commands, snapshot and scenario are still planned.
Python and TypeScript must accept and reject the same fixtures with the same reason codes.

### 1. Reactor library (offline → runtime)

A folder or zip containing `manifest.json` plus binary arrays. Normative spec: [library-format.md](library-format.md) (design background in [plans/03](plans/03-library-format.md)).
It has a `schemaVersion` and a list of required **model capabilities** (v1: `point-kinetics/lumped-thermal-v1`).
During 0.x the runtime accepts only an explicit list of supported schema versions. A library needing an unknown capability fails to load with a clear reason.

### 2. Commands (views → simulation)

Views never change state directly. They send commands:

```ts
type Command =
  | { type: "rod.move";        rod: string; direction: "in" | "out" | "stop" }
  | { type: "rod.fire";        rod: string }                          // transient rod, pulse mode
  | { type: "mode.set";        mode: string }                          // e.g. "steady" | "pulse" | "squareWave"
  | { type: "scram";           reason: string }
  | { type: "pump.set";        pump: string; on: boolean }
  | { type: "fault.inject";    fault: FaultSpec }                      // instructor only
  | { type: "fault.clear";     id: string }
  | { type: "time.set";        rate: number; paused: boolean }         // instructor only
  | { type: "time.rewindTo";   simTime: number };                      // instructor only
```

`time.set` and `time.rewindTo` are runtime commands, not engine commands: the worker handles them (the engine rejects them) and
refuses them from an operator window. As built, faults are `fault.instrument` (stuck, dead, clear) and `fault.reactivity`; the
rod faults, instrument drift and an exact reactivity clear are the engine request D3a (M6 design).

`rod.setTarget` (drive a rod to a position) was in the first draft but neither engine implements it; it's dropped until a view needs
it, and then goes into both engines and the contract fixtures together. The library schema's interlock `blocks` list still accepts
the name, so no shipped library has to change when it returns.

**Scheduling (the worker is the only authority):** each command carries a client ID. The worker assigns the accepted sim time and a monotonically increasing sequence number,
and replies `accepted` or `rejected` with a reason (e.g. interlock, paused, already tripped, unknown rod).
Order at one boundary instant (implemented in `physics_ref/engine.py`): rod motions rebased and instruments sampled, then trips on instrument readings evaluated
(a new trip scrams all rods), then commands in sequence-number order, then integration continues. Protection acts on the state reached **before** any new input
at that instant. This deliberately differs from the review's proposal (commands before trips); a command can't slip in ahead of a trip that's already due.
Trips whose inputs are all truth signals are located **inside** solver steps (to 0.1 µs). Instrument channels are sampled only at boundaries, like a digital channel.
Scripted scenario events will slot in before commands when scenarios exist.
Every accepted command goes into the **command log**. See replay under Runtime loop.

### 3. State snapshot (simulation → views)

```ts
interface SimSnapshot {
  t: number;                        // sim time, s
  truth: {                          // exact physics state; only the explorer and instructor may show it
    power: number;                  // W
    precursors: number[];           // per delayed group
    reactivity: { total: number; rods: number; fuel: number; coolant: number; xenon: number }; // Δk/k
    period: number;                 // s (Infinity when steady)
    fuelTemp: number; coolantTemp: number;  // K
    iodine: number; xenon: number;  // atoms/m³ (core-average)
    rods: Record<string, { position: number; moving: "in" | "out" | null }>;
    shape?: Float32Array;           // interpolated power shape, sent only when changed
  };
  indicated: Record<string, number | null>;  // instrument readings; what the operator sees (null = failed)
  trips: { latched: string[]; active: string[] };
  tripped: boolean;
  validity: { status: "supported" | "unvalidated" | "outOfDomain"; reasons: string[] };
  diagnostics: { ... };             // solver counters; see the schema
}
```
A sketch; the normative definition is `schema/snapshot.schema.json`.

The **truth/indicated split** is what keeps operator mode realistic. The operator view reads `indicated`, plus the console's own
state (rod positions and motion, mode, pumps, trips, validity, time) through one whitelist, `consoleState()` in
`web/src/views/operator/`; a test checks that no other `truth` field reaches it. **There is no `alarms` field:** the operator view
derives its annunciator tiles from the library's trips (lit while active, flashing when latched until acknowledged) and from
failed, over-range and rejected-command states (M5 design D1, `docs/m5-operator-design.md`). Engine-side alarms would be added only
if the instructor's replay record needs them.
Pulse extrema and integrated energy are tracked inside the worker, and each snapshot message carries every instrument's minimum and
maximum over the engine steps since the previous one (`extremes`), so a 30–60 Hz snapshot never misses a millisecond peak.

### 4. Scenario (content → runtime)

JSON: library ID, initial state, allowed controls, scripted events, goals and checks. See [plans/05-operator-ui.md](plans/05-operator-ui.md).

## Runtime loop

- The **simulation runs in a Web Worker**, so a heavy 3D frame never stalls the physics, and the reverse.
- The **clock** advances sim time in fixed **outer steps** (e.g. 10 ms of sim time).
  Inside each step, a stiff adaptive solver takes as many internal steps as the physics needs.
  A pulse needs microsecond steps; a steady reactor needs one.
- **Time rate** (instructor): sim time runs at `rate × wall time`. The worker advances in **bounded work batches** that yield to command processing,
  never skips physics to catch up, and reports the achieved rate. (3600× with 10 ms outer steps would be 360,000 steps per wall second,
  so slow regimes need larger scheduling intervals that keep instrument and event semantics. Decide this in plan 01.)
- The worker **posts a snapshot** every frame (~30–60 Hz). The power shape is sent only when rods or temperatures have changed enough to alter it.
- **History:** a checkpoint of the full state at **canonical restart boundaries** (the solver restarts there in normal runs too, so replay is identical), plus the command log.
  Rewind restores the nearest earlier checkpoint and replays commands. Plots use a lighter ring buffer of scalar values.
  Checkpoint contents and session pins are defined in [plans/06](plans/06-instructor.md).
- **One shared worker:** all authoritative state lives in one worker. Windows of the same session (`?session=<id>`) connect to it as a
  SharedWorker (one dedicated worker in one window where a browser has none), so no window owns the state and closing one doesn't stop
  the simulation. The worker enforces each window's role: an operator window can't send time, step, rewind, import, branch, note or
  `fault.*` commands (M6 design D2 and amendment 3, `docs/m6-instructor-design.md`). Roles are not authenticated in v1.
- **Resource limits:** plot buffers, pending view updates and retained checkpoints are bounded, with stated eviction rules.
  Stale display updates are coalesced; authoritative events never are. What's still exportable at the limit is defined in [plans/06](plans/06-instructor.md).
  Ownership of binary arrays sent between worker and views (transfer vs copy) is defined before the first transfer.
- **Diagnostics:** library-load failures, rejected commands, solver failures, event counts, achieved rate and validity status are recorded as structured data.

## Conventions

- **Units inside the code:** SI, with temperature in K, reactivity as absolute Δk/k, power in W, number densities in atoms/m³ and cross sections in m² (microscopic) or 1/m (macroscopic).
  pcm, dollars, °C and MW are for display only and converted in one place.
  **Boundary exceptions:** geometry stays in cm (OpenMC's unit) inside the library and 3D code, and OpenMC's atoms/b-cm or atoms/cm³ are converted by the extractor.
- **Geometry:** cm and right-handed, with z up, matching OpenMC. The explorer converts to three.js's y-up at load time.
- **Rod position:** fraction withdrawn, 0 = fully inserted, 1 = fully withdrawn.
  Each library also records the physical travel in cm.
- **No reactor-specific constants outside libraries.** A code review should reject a hard-coded TRIGA number.
  Test fixtures are the one exception, and they sit under `tests/` or `schema/vectors/`.
- **Determinism:** the simulation takes a seed for instrument noise. With the same pinned library digest, engine build, solver configuration, seed and command log,
  it gives identical output. Across Python, TypeScript and engine versions, agreement is **within stated tolerances**, not bit-identical.
- **Line endings:** LF everywhere (see `AGENTS.md`).

## Repository layout (planned)

```
virtual-reactor/
  README.md  PLAN.md  TODO.md
  docs/            ARCHITECTURE.md, WORKFLOWS.md, plans/, library-format.md (spec, once written)
  schema/          library.schema.json, command/state types, vectors/ (golden test cases)
  physics_ref/     Python reference simulation + tests
  pipeline/        models/, runs/, extract/, library/, armi/ (later), configs/
  libraries/       built libraries (large arrays via release assets, not git history)
  validation/      data/ (published measurements, with sources), tests/, reports/
  web/             Vite + TypeScript app: src/sim, src/instruments, src/views/{operator,explorer,instructor}, src/app
```

## How the milestones depend on each other

```
First, per the review: settle the contracts (TODO "Contracts"), then prove a headless slice with the synthetic library:
load → initialize → move rod → advance → snapshot → checkpoint → replay. Only then attach a minimal panel and primitive viewer, then expand the transport grid.

            ┌──▶ M1 physics prototype ──────────────┐
 Library    │                                       ├──▶ M4 link ──▶ M5 operator ──▶ M6 instructor
 format v0 ─┼──▶ M3 3D viewer (fake library) ───────┘        ▲
            │                                                │
            └──▶ M2 OpenMC library (real TRIGA data) ────────┘──▶ M7 validation
                                                                        │
                                            M8 second reactor ◀─────────┘──▶ M9 open release
```

- The **library format v0** comes first, because every other part reads or writes it.
- **M1, M2 and M3 can run in parallel.** M1 uses hand-entered published parameters, M3 uses a synthetic library,
  and M2 grinds away in WSL at the same time. That suits several agents working at once.
- M4 is where the real library replaces the fake inputs.
