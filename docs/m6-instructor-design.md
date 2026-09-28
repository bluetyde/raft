# M6: Instructor view (design)

Status: **approved by the user on 2026-09-27: D1–D6 as recommended (all option a), with four amendments** (§9). Slice S1 is built on the same branch (§10).
The decisions are marked **D1–D6**, each with options and a recommendation. The table at the end lists them.

The plan is [plan 06](plans/06-instructor.md). This design builds on the C6 runtime ([c6-runtime-design.md](c6-runtime-design.md)) and the M5 operator panel ([m5-operator-design.md](m5-operator-design.md)).

## 1. What already exists

- **Time:** the runtime has pause, rates, single steps and the achieved rate with its limit (`clock` message).
  `outerDt` is fixed per session (C6 D1, option T2). At the default 10 ms step, the runtime reaches about 30–150× real time (C6 §2).
- **History:** checkpoints every 10 s of sim time (at most 128, thinned when full). The command log is always complete.
  `rewind(step)` truncates the future (C6 D3a) and returns the old timeline as a session file (`rewound.previous`).
- **Session files:** `{format, version: 1, endStep, session}`. `session` is `engine.session()`, which pins the engine version, library digest, solver configuration, initial state and seed, and holds the command log.
- **Faults in the engine** (both engines, `_apply`):
  - `fault.instrument` with `kind` = `stuck`, `dead` or `clear`;
  - `fault.reactivity` with `deltaRho`, which adds to a running total (`extraRho`). There is no clear and no fault id;
  - `pump.set` with `on: false` is a pump trip.
- **Truth in the snapshot:** power, precursors, reactivity by source (`reference`, `calibration`, `fault`, `rods`, `fuel`, `coolant`, `xenon`, `total`), period, temperatures, iodine and xenon, energy, rods, mode and pumps.
  The snapshot does **not** list the active instrument faults. The engine keeps them in its public field `faults`.
- **Operator side:** the operator panel reads snapshots only through `operatorView` and sends commands as `clientId: "operator"`.

## 2. What plan 06 asks for, against what exists

| Plan 06 feature | Status | Gap |
|---|---|---|
| Pause, 1×, 10× | exists | UI only |
| 60×, 600×, 3600× | not at 10 ms steps | needs a longer `outerDt` (D5) |
| Rewind on a timeline | runtime exists | UI: scrub bar, markers |
| Branches, kept and compared | truncate only | D1 |
| Stuck instrument, dead instrument | engine has them | UI only |
| Instrument drift | not in the engine | engine request (D3) |
| Stuck rod, rod drop | not in the engine | engine request (D3) |
| Pump trip | `pump.set` | UI only |
| Reactivity insertion | `fault.reactivity` | UI only. "Clear" inserts the opposite amount |
| Truth panel | truth is in the snapshot | active faults are not (§4) |
| Annotations | none | D6 |
| Session and CSV export | session export exists | annotations, branches, CSV (D6) |
| Two windows (operator and instructor) | none | D2 |
| Fault visibility to the operator | open question in plan 06 | D4 |

## 3. Layout

The instructor view is a new view, `web/src/views/instructor/`. It is a fourth layout in `web/src/app/main.ts`, next to split, realism and explorer.
In one window, it shows the operator panel (small) and the instructor panel side by side. With two windows (D2), each window shows one of them.

The instructor panel has four parts:

1. **Time bar:** play and pause, rate, single step, achieved rate and its limit, and the session's outer step.
2. **Timeline:** a scrub bar from step 0 to the current step. It has markers for trips, rejected commands, faults, annotations and branch points.
   A click on the bar asks for a rewind to that step, after a confirm. The runtime pauses after a rewind (C6).
3. **Faults:** one row per fault the library supports, with its parameters, "inject" and "clear", and a list of active faults.
4. **Truth panel:** the truth values next to the operator's readings, and the reactivity by source as a bar per source.

## 4. Runtime additions (in my scope, no engine change)

- The snapshot message gets `faults: {instruments: Record<string, "stuck" | "dead">, extraRho: number}`, read from the engine's public fields after each step.
  This is the same pattern as `extremes` in M5.
- Annotations and branches live in the worker (D1, D6), so that two windows see the same list. New messages: `annotate`, `branch.list`, `branch.switch`.
- **Faster branch switch:** when a session file's command log equals the current log up to a stored checkpoint, the import starts from that checkpoint, not from step 0.
  Replay is deterministic, so this gives the same state. A test compares both paths with deep equality.

## 5. Decisions

### D1: rewind and branches

- **(a) Branch list in the worker (recommended).** A rewind keeps the old timeline as a branch: `{id, parent, forkStep, endStep, session, annotations}`.
  A branch is only its command log, so it is small. To switch to a branch, the runtime replays it (from a shared checkpoint when it can, §4).
  The current branch keeps its checkpoints. The other branches keep none, so memory stays bounded. Branches are limited to 32, and the oldest unnamed branch goes first.
- (b) Keep the C6 behaviour (truncate), and hold the old timelines only in the instructor window. This needs no runtime change, but a second window cannot see them.
- (c) Keep checkpoints for every branch. Switching is faster, but memory grows with each branch.

**Compare:** in the first slice, "compare" shows two branches' final values side by side, and their fork point.
Overlay charts of two branches need traces of the other branch. The CSV replay (D6) gives those, so overlays come in a later slice.

### D2: two windows

- **(a) A `SharedWorker` (recommended).** Both windows connect to the same worker, so no window is the owner.
  The worker lives while any window is open, so "owner lost" cannot happen. The runtime sends snapshots to each port, with one `frameAck` per port.
  `RuntimeClient` already accepts a `MessagePort`-like object (`WorkerLike`).
  Where a browser has no `SharedWorker` (some mobile browsers), the app falls back to one dedicated worker in one window.
- (b) The plan-06 design: one window owns a dedicated worker, and the other window mirrors it through `BroadcastChannel`.
  This needs a mirror protocol, owner-loss detection, and "disconnected" handling.
- (c) One window only in M6. Two windows come later.

With (a), ARCHITECTURE's "one owner" rule (mirror detects owner loss) changes to "one shared worker". That file is outside my scope, so the other session would change it (a request in `cloud-notes.md`).

### D3: faults that the engine does not have

- **(a) Build the UI for the faults that exist now, and request the others from the other session (recommended).**
  The request asks for, in both engines: `fault.rod` with `kind` = `stuck` (will not move), `noScram` (will not drop on a trip), `drop` (falls now) and `clear`,
  and `fault.instrument` with `kind` = `drift` and a rate. The UI adds a row for each one when the engine supports it.
- (b) Emulate a stuck rod in the view: the instructor view drops the operator's rod commands. This is not real: a SCRAM still moves the rod, and a replay does not show the fault. I do not recommend it.

### D4: can the operator see that a fault exists?

- **(a) No (recommended).** The operator sees only what the instruments show: a stuck reading freezes, and a dead reading goes blank, so M5 shows "failed" for it.
  This is what a real console does. The instructor panel lists all active faults.
- (b) A switch on the instructor panel that also lights an "instructor fault active" tile on the operator panel.

Plan 06 wants this as a per-scenario setting. Scenarios (A7) are on hold, so (a) is the default now, and the setting can come with scenarios.

### D5: rates above about 150×

`outerDt` is fixed per session (C6 D1 = T2). The request R3 (change `outerDt` during a session) is open and needs both engines.

- **(a) Choose the outer step when the session starts (recommended).** The instructor picks "fine" (10 ms) or "coarse" (1 s) at load.
  C6 measured (§2, one core): fine reaches about 150× at steady state and 31× during a transient. Coarse reaches 11 000–15 000× at steady state and about 2000× during a transient.
  So 3600× works in a coarse session while the state changes slowly (a xenon wait). During a fast transient the achieved rate is lower, and the time bar says so.
  The rate menu shows only rates that the step can reach.
  In the C6 test, a 1 s step changed xenon by at most 4e-8 relative. Commands apply on 1 s boundaries, and trips on instrument readings are checked once per second.
  A pulse needs the fine step.
- (b) Wait for R3, so one session can run a pulse and then a xenon wait.

### D6: annotations and export

- **Annotations:** `{id, step, text}`, held in the worker with their branch. A rewind moves annotations after the rewind step to the old branch.
- **Session file version 2:** version 1 plus `annotations` and `branch: {id, parent, forkStep}`. Import accepts versions 1 and 2. Replay ignores annotations.
- **CSV of traces:**
  - **(a) Replay the session in a separate short-lived worker (recommended).** It samples every N s of sim time (default 0.1 s) and writes time, the indicated readings, truth power, temperatures and reactivity by source.
    The result is exact and does not depend on chart thinning. The main worker does not stop while it runs. This is also the source of branch overlays later (D1).
  - (b) Write the chart buffers. This is fast but thinned (min and max per 0.2 s), and only covers the charted instruments.

## 6. Slices

1. **S1, one window:** the instructor layout, time bar with the outer-step choice (D5), timeline with markers and rewind, faults that exist now (D3), truth panel, active-fault list (§4).
2. **S2, history:** branches (D1), annotations, session file version 2, CSV export (D6).
3. **S3, two windows:** `SharedWorker` (D2), per-port snapshots, fallback, and e2e tests with two pages.

Each slice is its own PR on its own branch, based on the one before. Each has its own Vitest and Playwright tests.

## 7. Tests (first cut)

- **Truth guard:** the operator panel still reads no truth when the instructor view is open. The M5 truth-guard test stays as it is.
- **Faults:** inject and clear each fault from the panel. The active-fault list and the snapshot `faults` agree. A stuck instrument freezes and a dead one reads null on the operator panel.
- **Reactivity clear:** inserting +x and then "clear" returns `truth.reactivity.fault` to 0.
- **Timeline:** markers appear at the steps of trips, rejections, faults and annotations. A rewind from the bar ends at the chosen step, paused.
- **Branches:** rewind, change a command, then switch back. The old branch's end state deep-equals the state before the rewind (the main oracle). The shared-checkpoint path and the step-0 path give the same state.
- **Session v2:** export, import and compare with deep equality. Version 1 files still import.
- **CSV:** the replay's values at sampled times equal a step-by-step run's snapshots.
- **Two windows (S3):** Playwright with two pages on one shared worker: a command in one page shows in the other. Closing one page does not stop the sim.
- **Coarse step:** a 1 s session runs at 3600× in the fake-clock host, and a trip on an instrument reading comes within one outer step of the fine session's trip time.

## 8. Requests for the other session (only if the user picks these options)

- D3a: `fault.rod` (`stuck`, `noScram`, `drop`, `clear`) and instrument `drift`, in both engines, with golden vectors.
- D2a: ARCHITECTURE §"one owner" says one shared worker.
- Optional, from D5: R3 (change `outerDt` during a session) stays open.

## 9. Amendments (user, 2026-09-27)

1. **Coarse sessions and pulses.** A coarse session (outer step longer than 10 ms) rejects `mode.set` to `pulse` and `rod.fire`, with the reason `REJ_COARSE_STEP` and a text that says why.
   The time bar shows the session's outer step. A test covers it.
   The runtime does the check before the engine sees the command, so the rejected command is not in the command log.
   For the same reason, a coarse session cannot load in pulse mode, and a coarse session file with a pulse command does not import.
2. **Reactivity clear comes from the engine.** The panel does not insert the opposite amount. The other session adds a clear to the D3a request.
   Until then, the panel has no clear button for reactivity.
   Note for that request: today the engine accepts any `fault.reactivity` and adds `deltaRho ?? 0`. So a new `{kind: "clear"}` field would be accepted as a no-op by an older engine.
   The panel must know that the engine supports clear (for example, from the engine version in the pins) before it offers it.
3. **Roles with two windows.** The worker enforces which commands each window's role may send. The operator window cannot send time, rewind or fault commands. A test covers it. This comes with S3.
4. **Compare.** Compare shows each branch's fork step and command count next to its final values. This comes with S2.

The other session will do D3a (rod stuck, no-scram, drop and clear; instrument drift; reactivity clear) after its M2 runs, and the ARCHITECTURE change to one shared worker.

## 10. Slice S1: what is built

- **Runtime** (`web/src/runtime/`):
  - each snapshot message has `faults` (instrument faults and the inserted reactivity), read from the engine's public fields;
  - a coarse session (outer step longer than 10 ms, `isCoarse` in `protocol.ts`) rejects `rod.fire` and `mode.set` to `pulse` with `REJ_COARSE_STEP`.
    It also refuses to load in pulse mode (`E_COARSE_PULSE`), and it refuses to import a coarse session file that holds pulse mode or a rod firing;
  - `RUNTIME_REJECTIONS` gives the text for `REJ_COARSE_STEP`. The operator panel shows it next to the code.
- **Operator panel:** its rate menu now follows the clock, because the instructor can also set the rate.
- **Instructor view** (`web/src/views/instructor/`):
  - `time.ts`: the two outer steps (fine 10 ms, coarse 1 s), the rates for each, and the step as the time bar shows it;
  - `timeline.ts`: markers for trips, rejected commands and the instructor's faults, and the mapping from the bar to a step;
  - `faults.ts`: the fault commands that the engine has (instrument stuck, dead and clear, reactivity insertion, pump trip and restart). The panel lists the others as "not in the engine yet";
  - `truth.ts`: the reactivity by source in pcm, each instrument's reading next to its true value, and the active-fault lines;
  - `panel.ts`: the DOM panel. A click on the timeline asks first, then rewinds. "New session" restarts the library with the chosen outer step.
- **Layout:** `instructor` in `web/src/app/main.ts`: the operator panel next to the instructor panel. The 3D view is hidden in this layout.
- **Not in S1:** markers from before an import (the runtime does not send the events of a replay), branches, annotations and export (S2), and two windows (S3).

### Findings while building S1

- **A reactivity step trips `period-short` at once.** The trip reads `truth.period`, which has no lag. Right after a step, the prompt jump gives a very short period.
  On the synthetic core, 5, 10, 20 and 40 pcm all trip after one step. `triga-jsi-242` has the same trip.
  A real period channel has a lag, so it would not trip on a small step. This is a question for the library and the engine, not for the view. The panel has a note about it.
- **`fault.reactivity` accepts unknown fields.** A `{kind: "clear"}` sent to today's engine is accepted and adds 0. So the view must know that the engine supports clear before it sends one (amendment 2).

## Decisions (approved by the user, 2026-09-27)

| # | Decision | Recommended |
|---|---|---|
| D1 | Rewind and branches | **(a)** branch list in the worker, command logs only, 32 at most |
| D2 | Two windows | **(a)** `SharedWorker`, with a one-window fallback |
| D3 | Faults the engine lacks | **(a)** UI for existing faults now, request the rest |
| D4 | Operator sees faults | **(a)** no, only through the instruments |
| D5 | Rates above about 150× | **(a)** outer step chosen at session start (10 ms or 1 s) |
| D6 | CSV export | **(a)** replay in a separate worker, sample every 0.1 s |
