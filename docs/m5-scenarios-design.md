# M5 scenarios (design)

Status: **approved by the user on 2026-09-28: D1–D5 and D7 as recommended (option a), D6 = (b), with five amendments** (§9). Slice SC1 is built on the same branch (§10).
The decisions are marked **D1–D7**, each with options and a recommendation. The table at the end lists them.

This is the last M5 item in TODO: "Scenarios: startup, steady power, pulse, scram, xenon transient". Plan 05 sketches the format.
The format design is A7 in `docs/AGENT-TASKS.md`. A7 was on hold, and the user asked for this item on 2026-09-28.
The design builds on the C6 runtime, the M5 operator panel and the M6 instructor view ([m6-instructor-design.md](m6-instructor-design.md)).

## 1. What a scenario is

A scenario is a teaching unit. It names:
- a library;
- a start state and an outer step;
- the controls the operator may use;
- scripted events (for example, a fault at a given time);
- goals, each with a check;
- a brief and hints.

The instructor starts a scenario. That starts a new session. The operator window shows the brief, the goals and the hints.
Scoring is gentle (plan 05): goals met, trips caused and time taken.

## 2. What already exists

- **Start states:** the engine's `init` takes rod positions, the mode, pumps, fuel and coolant temperatures, and precursors. It also takes three power modes (`source-equilibrium`, `given`, `critical-equilibrium`) and three poison modes (`zero`, `given`, `equilibrium`).
  So a scenario's start state can be passed through as `init`, with no engine change.
- **Checks:** the library format already has typed predicates: `all`, `any`, `not`, and the operators `eq`, `ne`, `between`, `gt`, `ge`, `lt`, `le` and `absGt`.
  `evalPredicate` in `web/src/sim/engine.ts` evaluates them. The signals are `indicated.<instrument>` and `truth.power`, `truth.fuelTemp`, `truth.coolantTemp`, `truth.xenon`, `truth.mode`, `truth.period` and `truth.rod.<id>`.
  ARCHITECTURE-REVIEW asked for scenario checks in this typed form, not free text.
- **Commands** that a script can use: `rod.move`, `rod.fire`, `mode.set`, `pump.set`, `scram`, `trip.reset`, `fault.instrument` and `fault.reactivity`.
- **Sessions:** the command log makes replay, rewind, branches and CSV exact. Session files are version 2.
- **Roles:** the worker enforces what an operator window may send (M6 amendment 3).
- **Outer step:** fine (10 ms) or coarse (1 s). A coarse session rejects pulse mode and rod firing (M6 amendment 1).

## 3. The format (proposed)

```jsonc
{
  "format": "virtual-reactor-scenario",
  "version": 1,
  "id": "triga-scram-and-restart",
  "library": "triga-jsi-242",          // a library id; the session pins the digest it ran with
  "title": "Scram and restart",
  "brief": "Hold the reactor at low power, scram it, watch the period, then restart.",
  "outerDt": 0.01,                      // 0.01 (fine) or 1 (coarse); a pulse scenario needs 0.01
  "seed": 1,
  "init": { "rods": { "safety": 1, "shim": 1, "regulating": 0.55, "transient": 0 }, "power": { "mode": "given", "value": 100 } },
  "controls": { "allow": ["rod.move", "scram", "trip.reset", "mode.set"] },
  "faultsVisible": false,               // M6 D4: the operator sees faults only through the instruments
  "events": [
    { "at": 120, "cmd": { "type": "fault.instrument", "instrument": "fuel-t2", "kind": "stuck" }, "note": "a stuck thermocouple" }
  ],
  "goals": [
    { "id": "scram", "text": "Scram the reactor", "check": { "signal": "truth.rod.safety", "op": "lt", "value": 0.01 } },
    { "id": "negative-period", "text": "See the negative period settle",
      "check": { "signal": "truth.period", "op": "between", "value": [-90, -70] }, "for": 5,
      "source": "the stable negative period after a scram is set by the longest-lived precursor group (about -80 s; Keepin 1965)" },
    { "id": "restart", "text": "Restart to the same power", "after": "scram", "within": 900,
      "check": { "signal": "indicated.linear", "op": "gt", "fromTrip": "power-high", "times": 0.0004 } }
  ],
  "hints": ["The negative period after a scram does not depend on how much rod worth went in."]
}
```

Rules (a validator checks each one, with an error code):

| Rule | Code |
|---|---|
| `format`, `version`, `id`, `library`, `title` are present, and `id` is `[a-z0-9-]+` | `E_SCN_FIELD` |
| `outerDt` is 0.01 or 1. A coarse scenario has no `rod.fire` and no pulse mode, in `init`, `events` and `controls` (M6 amendment 1) | `E_SCN_COARSE` |
| `init` is accepted by the engine for the named library (the validator tries `new Engine`) | `E_SCN_INIT` |
| Each `controls.allow` entry is a command type the engine has | `E_SCN_CONTROL` |
| Each event has `at` ≥ 0 (sim seconds) and a `cmd` that passes the command schema | `E_SCN_EVENT` |
| Each check uses the library's predicate format, with known operators and signals that the library has | `E_SCN_CHECK` |
| Goal ids are unique. `after` names an earlier goal. `within` and `for` are > 0 | `E_SCN_GOAL` |
| Every number that is a threshold or a level has a `source`, or it comes from the library (`fromTrip`) | `E_SCN_SOURCE` |

`fromTrip` takes a trip's setpoint from the library, and `times` scales it. This follows WORKFLOWS §4: "every threshold must come from the library or a cited source. No invented setpoints."

## 4. How a scenario runs

- **Start:** the instructor picks a scenario. The runtime loads its library with `init`, `seed` and `outerDt`. Loading is instructor-only (M6 amendment 3).
  The runtime holds the scenario while the session lasts, and the session file (version 3) adds `scenario: {id, digest}`.
- **Scripted events (D2):** at the first step boundary at or after `at`, the runtime submits the event's `cmd` with `clientId: "scenario"`.
  It does this before any other command of that boundary, so the event gets the lower sequence number.
  The command log holds it, so replay, rewind, branches and CSV traces reproduce it exactly.
  After a rewind, the runtime submits again the events that come after the rewind step.
- **Allowed controls (D4):** the worker rejects an operator's command whose type is not in `controls.allow`, with `REJ_SCENARIO`.
  "An operator's command" means any command from an operator window, or with a `clientId` other than `instructor` or `scenario`.
- **Goals (D3):** after each engine step, the runtime evaluates each open goal's check on that step's state.
  - A goal is met the first time its check holds for `for` seconds without a break (default: one step).
  - A goal with `after` opens only when that goal is met.
  - A goal with `within` fails if it is not met within that many seconds after it opens.
  - The results are a list of `{goal, status, t}`. Like the timeline marks, they belong to a branch, and a rewind drops the ones after the rewind point.
  - The runtime sends a new `scenario` message when a goal changes: the scenario's id, each goal's status, and the trips so far.
- **Fault visibility:** with `faultsVisible: false` (the default), the operator panel shows only what the instruments show (M6 D4).
  With `true`, it adds a tile "instructor fault active".
- **Score:** goals met out of all goals, the number of trips, and the time at the last goal. It is shown to both windows at the end: when all goals are met or failed, or when the instructor ends the scenario.

## 5. Decisions

### D1: where the format, the files and the validator live

- **(a) The format is defined in this doc (recommended).** Scenario files go in `web/src/app/scenarios/<id>.json`, bundled like the library catalog.
  A TypeScript validator in `web/src/runtime/scenario.ts` checks them, with the codes in §3. A test runs it on every shipped scenario.
  A7 (the JSON schema `schema/scenario.schema.json`, a Python validator in `pipeline/scenario/` and invalid fixtures) comes later from the other session, from this doc.
  Then the files can move to `web/public/scenarios/`, where plan 05 puts them.
- (b) The other session writes the schema and fixtures first (A7), and the runtime work waits for them.

`schema/`, `pipeline/` and `web/public/` are outside my scope, so (a) keeps the work moving. The schema must then match the TypeScript validator. A shared set of invalid fixtures would keep them in step.

### D2: how scripted events enter the engine

- **(a) The runtime submits them as commands (recommended).** They use `clientId: "scenario"`, at their step, before other commands of that boundary.
  This needs no engine change. Replay is exact, because the log holds them.
  The limit: a script can only do what a command can do, so no rod drop or drift until D3a (M6) adds them.
- (b) Scenario events in the engine, in both engines. ARCHITECTURE §2 says "scripted scenario events will slot in before commands when scenarios exist". This needs the other session, and golden vectors.

With (a), a scripted command at a boundary still comes after the trips at that boundary, like every command. This matches ARCHITECTURE's order (trips, then commands in sequence order).

### D3: where goals are checked

- **(a) In the worker, after each engine step (recommended).** This is exact: a goal on a short event (a pulse peak) is not missed, and all windows agree.
- (b) In the view, from snapshots. Snapshots come at about 30 Hz, so a check can miss an event between two snapshots.

### D4: allowed controls

- **(a) The worker enforces `controls.allow` for operator commands (recommended),** with `REJ_SCENARIO`. The instructor and the script are not limited.
- (b) The view only disables the buttons.

### D5: thresholds and their sources

- **(a) Each threshold has a `source`, or comes from the library with `fromTrip` (recommended).** The validator refuses a bare number (`E_SCN_SOURCE`).
- (b) Plain numbers, and a reviewer checks them.

### D6: the first scenarios

- **(a) All five from TODO, for `triga-jsi-242` (recommended):**
  1. **approach to critical**, from shutdown with the source;
  2. **power ascension and steady hold**;
  3. **pulse**, fine step;
  4. **scram and restart**;
  5. **xenon after shutdown**, coarse step.

  Each scenario also gets a copy for `synthetic-core`, which the tests use.
  The library is "experimental", and its rod worths are "assumed". So the goals use the library's own trips, or physics with a published source (for example, the negative period after a scram).
  They do not use plant numbers that the library does not have. Xenon at TRIGA power is small, and the scenario says so (plan 05: "shown honestly").
- (b) Start with two (scram and restart, and power ascension) to prove the format. Add the other three after M2's real data.

### D7: the operator's view of a scenario

- **(a) A scenario strip on the operator panel (recommended):** the brief, a goal checklist (open, met or failed, with the time), hints behind a button, and the elapsed time.
  The instructor panel gets a scenario picker ("start"), the goals with their status, and the scripted events as timeline marks.
  The 1/M plot helper for the approach to critical is part of this too: 1/M from the log channel against the rod position, drawn after each rod stop.
- (b) Goals only in the instructor panel. The operator sees nothing of the scenario but the brief.

## 6. Slices

1. **SC1, the engine side:** the format, the validator, the runtime (events, controls, goals and score), session files version 3, and the scram-and-restart and power-ascension scenarios. It has only a small UI: the picker and the goals list.
2. **SC2, the rest:** the other three scenarios, the operator's scenario strip, the 1/M plot, and the end-of-scenario score.

Each slice is its own PR, with its own Vitest and Playwright tests.

## 7. Tests (first cut)

- **Validator:** one test per error code, and every shipped scenario passes.
- **Events:** a scripted event is in the log with `clientId: "scenario"`, at its step, with a lower seq than an operator command at the same boundary.
  After a rewind before the event, it is submitted again, and the end state equals a run without the rewind (deep equality).
- **Controls:** a command outside `allow` from the operator is rejected with `REJ_SCENARIO`. The same command from the instructor is accepted.
- **Goals:** `for`, `after` and `within` each have a test. A goal on a short pulse peak is met, although no snapshot saw the peak. A rewind drops the later results.
- **Headless run of each scenario (WORKFLOWS §4):** a scripted operator plays each scenario on `synthetic-core`. All goals are met, and the trips fire when expected.
- **Session file version 3:** export and import with the scenario. A file with an unknown scenario, or a changed scenario digest, is refused.
- **Playwright:** the instructor starts a scenario. The operator window shows the goals. A rejected control shows `REJ_SCENARIO`. A goal is met.

## 8. Findings and requests (only if the user picks these options)

- **Plan 05's example** uses `indicated.period` (no library has a period instrument) and `instrument.drift` (not in the engines). The format above uses `truth.period` for checks, and leaves drift to D3a.
- **For the other session:** A7 from this doc (D1a): the JSON schema, the Python validator and invalid fixtures. If (b) is chosen for D2, scenario events go into both engines.
- **Real numbers:** after M2, the scenario thresholds for `triga-jsi-242` should move from "assumed" library values to measured ones where a source exists.

## 9. User decision and amendments (2026-09-28)

- D1–D5 and D7: option (a). **D6 = (b):** scram-and-restart and power ascension now. Approach to critical, pulse and xenon wait for the M2 OpenMC libraries.
- **Amendment 1:** `init.rods` also accepts `"reference"` (the library's `reference.rods`) and `"shutdown"` (every rod at 0), as well as per-rod values. The validator refuses unknown rod ids (`E_SCN_ROD`).
- **Amendment 2:** the resolved `fromTrip` thresholds are recorded in the version 3 session file.
- **Amendment 3:** a scripted event gets its sequence number when its boundary is reached, before operator commands queued for that boundary. A test covers the case where the operator's command was queued first.
- **Amendment 4:** until the period trip is lagged, scenarios avoid `fault.reactivity` step events, or they expect the `period-short` trip (M6 finding: any step trips it at once).
  The validator refuses a `fault.reactivity` event unless `expectTrips` names every trip on `truth.period` (`E_SCN_REACTIVITY_STEP`).
- **Amendment 5:** operator-facing goals use `indicated.*` where an instrument exists. The validator refuses a `truth.*` signal that an instrument measures (`E_SCN_TRUTH_GOAL`).
  `truth.period`, `truth.rod.<id>`, `truth.xenon` and `truth.mode` stay allowed, because no instrument measures them.
- The other session will do A7 (the schema, a Python validator and shared invalid fixtures) after SC1. It will also propose a lagged period instrument, which would also give `indicated.period`.

## 10. Slice SC1: what is built

- **Format changes from §3, found while building:**
  - `fromTrip` takes the trip's setpoint. For a trip like `period-short` (`all` of `gt 0` and `lt 3`), the setpoint is the one bound that is not 0. `times` scales it. For `between`, `times` is a pair.
  - `init.source` is needed when `init` has a level (`power.value`, `Tfuel`, `Tcoolant`, or given poisons). Rod positions are controls, not levels.
  - `expectTrips` lists the trips a scenario expects (amendment 4). The score does not count them, and it never counts `manual`.
- **Code:**
  - `web/src/runtime/scenario.ts`: the format, the validator (the codes in §3 plus `E_SCN_ROD`, `E_SCN_REACTIVITY_STEP` and `E_SCN_TRUTH_GOAL`), the preparation (rod presets, `fromTrip`, event steps, the digest) and the goal tracker;
  - `web/src/runtime/runtime.ts`: a `load` with a scenario, the scripted events (submitted when their boundary is reached, and before an operator command at that boundary), the allowed controls (`REJ_SCENARIO`; `clientId: "scenario"` is reserved), the goals after each step, and a `scenario` message.
    The goal tracker's state is kept at each checkpoint, so a rewind, a branch switch and an import give the same goals as a run without them;
  - session files version 3 with `scenario: {id, digest, thresholds}`. An import needs the same scenario (its digest must match);
  - `web/src/app/scenarios/`: the two approved scenarios for `triga-jsi-242`, and copies for `synthetic-core` (the scram copy has one scripted event, a stuck pool thermometer at 60 s);
  - the instructor panel: a scenario picker, the goals with their status and time, the score, and "scripted" marks on the timeline. The operator's scenario strip (D7) is SC2.
- **Findings from runs on `triga-jsi-242` and `synthetic-core`:**
  - After a scram from a *rising* power, the period stays far from −80 s: it creeps from −11 s to −49 s in 150 s, because the precursors are not in equilibrium.
    After 20 minutes at steady power, the period enters −90 to −70 s about 225 s after the scram and stays there.
    So the scram-and-restart scenario first asks for 10 minutes of steady power, and the negative-period goal has 400 s. The §3 example was wrong about this.
  - A "positive period" goal is met a few seconds after the rods start out, while the core is still subcritical (subcritical multiplication). So power ascension uses power goals only.
  - With every rod out, fuel-temperature feedback holds `triga-jsi-242` near 100 kW, below the 275 kW power-high trip.

## Decisions (approved by the user, 2026-09-28)

| # | Decision | Recommended |
|---|---|---|
| D1 | Where the format, files and validator live | **(a)** the format in this doc, files in `web/src/app/scenarios/`, a TypeScript validator now, and the A7 schema later |
| D2 | How scripted events enter the engine | **(a)** the runtime submits them as commands (`clientId: "scenario"`) |
| D3 | Where goals are checked | **(a)** in the worker, after each step |
| D4 | Allowed controls | **(a)** the worker enforces them for operator commands (`REJ_SCENARIO`) |
| D5 | Thresholds and sources | **(a)** each has a `source`, or `fromTrip` from the library |
| D6 | First scenarios | **(b), chosen:** scram-and-restart and power ascension now; the other three after the M2 OpenMC libraries |
| D7 | The operator's view of a scenario | **(a)** a scenario strip with the goals checklist, hints and the 1/M plot |
