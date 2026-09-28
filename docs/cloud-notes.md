# Cloud notes

A log for the browser-track session that runs in the cloud. The OpenMC session reads it to see what changed and what this session needs.
Add a dated entry for each piece of work: what changed, the branch, and the checks with their results.
Put requests for the other session under "Requests". Mark a request "done" when it is done, and do not delete it.

## Scope of the cloud session

- Owns: `web/src/runtime/`, `web/src/views/`, `web/src/app/`, `web/index.html`, `web/vite.config.ts` (user OK, 2026-09-27), `web/package.json` and its lockfile (dependencies only), `.github/`, this file, and its own design docs under `docs/`.
- Does not edit: `physics_ref/`, `web/src/sim/`, `web/src/library/`, `web/src/contracts/`, `schema/`, `pipeline/`, `validation/`, `libraries/`.
  Engine or schema changes come here as requests, because the Python and TypeScript engines must stay in step.
- Works on branches with pull requests only. It never pushes to `main`. It merges a pull request only when the user asks for that pull request.

## Requests for the OpenMC session

### R1 (done 2026-09-27 by the cloud session, user OK): give the slow web tests more time than Vitest's 5 s default

- Problem: on the GitHub runner, `src/sim/engine.test.ts > TestKineticsAnalytic > nordheim-fuchs pulse` takes 3.0–5+ s.
  Locally it takes 1.9 s. On commit `d7e4ba8` it passed in one CI run (3011 ms) and timed out at 5000 ms in the other.
  The assertions pass. Only the time limit fails.
- Why here: the fix is in `web/vite.config.ts` or `web/src/sim/engine.test.ts`, outside the cloud session's files.
- Proposed patch (no assertion changes), in `web/vite.config.ts`:
  ```ts
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    // CPU-heavy analytic checks take 3-6 s on the GitHub runner.
    testTimeout: 30_000,
  },
  ```
  A per-test timeout on the slow tests in `engine.test.ts` also works, but then every new heavy test needs one too.
- Done: the user let the cloud session make this one edit to `web/vite.config.ts` (`testTimeout: 30_000`, no other change), on `claude/kind-bohr-p73819`.

### R3 (future, not blocking, 2026-09-27): change `outerDt` during a session

- The runtime can reach high speeds only with a long outer step, and `outerDt` is fixed per session (D1 option T2, chosen by the user).
  A pulse needs 10 ms steps, and a xenon wait can use 1–2 s steps. One session cannot do both today.
- Request, for when M6 needs it: let a session change `outerDt` at a logged boundary, with replay and checkpoints still deterministic.
  This means time is no longer `stepIndex × outerDt`, in both engines. Measurements: `docs/c6-runtime-design.md` §2.

### R4 (future, not blocking, 2026-09-27): engine step cost

- Measured on `triga-jsi-242` (Node 22, one core): 54 µs per steady 10 ms step, and about 320 µs per step during a rod-scram-xenon transient (31× real time at 10 ms).
  For a 13-value state this is slow, so profiling (allocations per step, for example) could give a few times more speed.
- The cost is per outer step and almost independent of `outerDt`. A 1 s outer step gave the same results to 4e-8 relative and 1993× real time.
- Only if the other session has time. The golden vectors must still pass.

### R5 (open, 2026-09-27): third-party notices for three.js and viridis

- The app build now bundles **three.js 0.186.1** (MIT, copyright three.js authors) and uses the **viridis** colour-map stops from matplotlib (CC0),
  in `web/src/views/explorer/styles.ts`. `THIRD_PARTY_NOTICES.md` still says "No third-party code is included yet".
- Request: add both to `THIRD_PARTY_NOTICES.md` (the file is outside the cloud session's scope). `@types/three` and its type dependencies are build-time only.

### R6 (open, 2026-09-27): `web/src/main.ts` is no longer used

- `web/index.html` now loads `web/src/app/main.ts` (the explorer). The old placeholder `web/src/main.ts` is outside the cloud session's files, so it stays, unused.
- Request: delete it, or say the cloud session may.

### R7 (open, 2026-09-27): TODO Next #8 is done

- The browser end-to-end check on the synthetic fixture exists (malformed library, a trip, pause/resume, replay): `web/src/app/e2e/`, CI job `e2e`.
  Request: tick TODO Next #8 and the matching item under "Contracts", and update the agent board. Those files are outside the cloud session's scope.

### R2 (information, 2026-09-27): CI has no scipy, so one Python test skips there

- `physics_ref/tests/test_engine.py:353` (`skipUnless(HAVE_SCIPY)`) skips on CI and runs where scipy is installed.
  This is by design ("fast checks need no packages"). The user decided CI does not need scipy for now (maybe later).

## Log

### 2026-09-27: baseline check

- Branch: `claude/kind-bohr-p73819` at `main` `03e6cb4`, no changes.
- `python3 scripts/premerge.py` with `VR_PYTHON=python3`, Python 3.11.15, Node 22.22.2 (the container has no Node 24 yet): all four stages pass.
  Python 108 tests (156 s), web 77 tests in 9 files.
- TODO Next #9 (A9, pre-merge script) is already done. The other session updates TODO and the board on `claude/todo-a9-done`, so this session leaves those files alone.

### 2026-09-27: CI workflow

- What: `.github/workflows/premerge.yml` runs `python3 scripts/premerge.py` on every pull request and on pushes to `main`.
  Push runs are limited to `main`, because a push to a PR branch already starts a `pull_request` run (the user left this choice to this session).
  It uses Ubuntu, Python 3.11, Node 24, `npm ci --ignore-scripts` in `web/`, and `VR_PYTHON=python3`.
  A newer run on the same ref cancels an older one.
- Branch: `claude/kind-bohr-p73819`.
- Checks: `python3 scripts/premerge.py` in the container (Node 22.22.2): all four stages pass (summary table in the PR).
- First CI runs on `d7e4ba8` (Python 3.11.16, Node 24.21.0, npm 11.19.0): the `pull_request` run passed.
  The `push` run failed in web-test on a 5 s timeout (request R1). The Python stage took 198–227 s and skipped 1 test (R2).
- Fix: `testTimeout: 30_000` in `web/vite.config.ts` (R1, user OK), and `push` limited to `main`.

### 2026-09-27: C6 runtime design (proposal, waiting for the user)

- What: `docs/c6-runtime-design.md`, the design for the Web Worker runtime (clock, command bus, snapshot and event stream, history). No code yet.
  It uses only the engine's public API and the command and snapshot schemas. No engine or schema change is needed for the recommended options.
- Findings from the engine code that the other session may want to know:
  - `time.set` and `time.rewindTo` from ARCHITECTURE §2 are not engine commands (the engine rejects them). The design keeps time control in the runtime.
  - `engine.checkpoint()` copies the whole command log, so the runtime stores checkpoints without it and rebuilds it from its own log.
  - `engine.session()` has no end step, so the runtime's session file adds one.
- Measured step cost (Node 22, one core): about 55–90 µs per 10 ms outer step, so at most about 150× real time. The cost is per step, so 3600× needs a longer `outerDt`.
  One pulse step on the synthetic core takes about 60 ms.
- User decisions (2026-09-27): D1 = T2 (`outerDt` fixed per session), D2 = queue commands while paused, D3 = truncate after a rewind, D4 = no role check.
- The user asked for the speed findings to be noted: a 4-hour transient at `outerDt` 10 ms / 0.1 s / 1 s gave 31× / 238× / 1993× real time with the same results (to 4e-8).
  Future requests R3 (change `outerDt` during a session) and R4 (engine step cost) are above.
- Branch: `claude/c6-runtime-design` (based on `claude/kind-bohr-p73819`, because this file is not on `main` yet).

### 2026-09-27: C6 runtime implemented

- What: `web/src/runtime/` (`protocol.ts`, `runtime.ts`, `history.ts`, `readers.ts`, `worker.ts`, `client.ts`), built on the engine's public API only.
  No change to `web/src/sim/`, `web/src/library/`, `web/src/contracts/` or `schema/`. Design and decisions: `docs/c6-runtime-design.md`.
- Tests: 39 new Vitest tests in `web/src/runtime/*.test.ts` (fake clock; the main oracle compares a runtime session with `Engine.replay` and a plain loop).
  Five targeted breaks, each caught. A manual Chromium smoke run of the real worker passed. Automated browser e2e is still TODO Next #8.
- Behaviour to know: a rewind to a step keeps the commands logged at that step queued, the same as `Engine.replay`.
- Branch: `claude/c6-runtime-design`. Checks: see the PR.

### 2026-09-27: M3 renderer decision and three.js viewer

- What: `docs/m3-renderer-decision.md` (TD-07: three.js meshes from the primitives now, behind the `ViewerModel` adapter; CSG reuse at a later gate) and the viewer in
  `web/src/views/explorer/` (noclip and orbit cameras, one cutaway plane with stencil caps, click-to-inspect with exact analytic picking, view-only rod sliders,
  per-element reference power overlay). App in `web/src/app/`, which bundles the synthetic core and `triga-jsi-242`. `web/index.html` loads the app.
- Dependencies (user OK): `three` 0.186.1 and `@types/three` 0.186.0, pinned exactly. The lockfile was regenerated with npm 11.19.0 (the CI npm), and its diff only adds packages.
  (npm 10 in this container drops the `libc` fields of the native bindings, so it was not used.)
- Tests: 34 new Vitest tests (picking on both libraries, scene bounds, rods, cutaway, overlay, noclip math, catalog). A Chromium run of the production build checked a real click pick,
  cutaway caps (with and without), a withdrawn rod, and both libraries.
- Requests R5 (notices) and R6 (unused `web/src/main.ts`) are above.
- Branch: `claude/m3-viewer` (based on `claude/c6-runtime-design`). Checks: see the PR.

### 2026-09-27: merges (user request)

- The user asked the cloud session to merge the CI and C6 pull requests, but not M3:
  `claude/kind-bohr-p73819` (CI) was merged into `main` as `0002c02`, and `claude/c6-runtime-design` (C6) as `6a4be94`, both with merge commits.
- The M3 pull request (`claude/m3-viewer`, bluetyde/virtual-reactor#3) stays open for the user's review. It also carries this file's M3 entry and requests R5 and R6,
  so those reach `main` only when M3 merges.

### 2026-09-27: browser end-to-end check (TODO Next #8)

- What: `web/src/app/e2e/` (harness page, `runtime.spec.ts`, `playwright.config.ts`) and the CI job `e2e`. Five tests run the real runtime worker in Chromium on the production build:
  two malformed libraries (`E_JSON`, `E_DIGEST_MISMATCH`); the period trip, which fires at the golden vector's time (`period-trip.json`, within 1e-9 s) with the vector's peak power and time;
  pause and resume; and replay (export from one worker, import into another, and a rewind, each giving the same snapshot).
- Two deliberate breaks were each caught (replay re-submitting checkpointed commands; pause doing nothing).
- Fix found by this work: the C6 client's `WorkerLike` type did not accept a real DOM `Worker` (its tests used an in-memory fake). Fixed, with a compile-time check in `client.test.ts`.
- `web/vite.config.ts`: `VR_E2E=1` adds the harness page to the build. Normal builds are unchanged.
- Dependency: `@playwright/test` 1.63.0 (Apache-2.0), pinned exactly; lockfile regenerated with npm 11.19.0, additions only (`@playwright/test`, `playwright`, `playwright-core`).
  In a container whose Playwright browsers are older, set `VR_CHROMIUM` to a Chromium executable (here `/opt/pw-browsers/chromium`, Chromium 141).
- `scripts/premerge.py` does not run the e2e tests (the script is outside this session's files). Locally: `cd web && npx playwright test -c src/app/e2e/playwright.config.ts`.
- Branch: `claude/e2e-browser` (from `main` at `6a4be94`). Checks: see the PR.

### 2026-09-27: M4 live explorer (first slice)

- What: the app now runs the chosen library in the runtime worker. The explorer's rods and a live per-element power overlay follow the snapshots,
  and a control strip (`web/src/app/controls.ts`) sends rod, scram, trip-reset, mode and clock commands through the command bus. Notes: `docs/m4-live-view.md`.
- New code: `web/src/views/explorer/live.ts` (snapshot to view), explorer live mode and overlay, `web/src/app/controls.ts`, `catalogFiles` in the catalog, app wiring.
- Tests: 11 new Vitest tests (`live.test.ts`) and 3 new Playwright tests (`app.spec.ts`); a deliberate break (rods not applied) fails both rod tests.
- Finding: ARCHITECTURE §2 lists `rod.setTarget`, which the engine does not implement (only `rod.move` in/out/stop). Not a request yet; tell the cloud session if M5 should have it.
- Branch: `claude/m4-live`, based on `claude/m3-viewer` with `claude/e2e-browser` merged in (it needs the `WorkerLike` fix). Merge order: M3, e2e, then M4.

### 2026-09-27: M5 operator panel design (proposal, waiting for the user)

- What: `docs/m5-operator-design.md`. No panel code yet. Decisions D1–D6 are open for the user.
- Findings the other session may want to know (plan 05 and ARCHITECTURE §3 assume things the engine and format do not have):
  - no `alarms` in the snapshot (only `trips` and `tripped`);
  - no derived instruments, so no indicated period;
  - rod positions only in `truth.rods` (no rod-position instruments);
  - no rated power, so no percent power.
  The recommended options need none of these. Possible later requests, only if the user picks those options: engine alarms (D1b), rod-position instruments (D2b), an indicated period (D3b), `plant.ratedPower` (D4b).
- Branch: `claude/m5-operator-design`, based on `claude/m4-live`.
- User decision (2026-09-27): approved with D1–D6 = option a, and three amendments: min/max chart thinning (with a 10 ms spike test),
  a careful derived period (skips null, pegged and pre-rewind points; "—" when too few points or in pulse mode; tested with lag and noise),
  and no edit to ARCHITECTURE.md from the cloud session.
- **For the local session:** the user said the local session will change ARCHITECTURE §3 to say that alarms are derived in the view (not `snapshot.alarms`).

### 2026-09-27: M5 operator panel implemented

- What: `web/src/views/operator/` (`console.ts` the operator-view rule, `meters.ts`, `period.ts`, `strip.ts`, `annunciator.ts`, `chart.ts`, `panel.ts`),
  the split / realism / explorer layouts in `web/src/app/main.ts`, and per-step instrument extremes in the runtime snapshot message (`extremes`).
  The operator panel reads snapshots only through `operatorView` and sends commands with `clientId: "operator"`.
- Findings while building it (recorded in `docs/m5-operator-design.md` §7):
  - the derived period needs at least 8 readings in its 2 s window, so it reads only up to about 7× real time (30 Hz snapshots); above that it shows "—";
  - with 1–2 % log-channel noise, the slope must exceed 3 standard errors to show a period (2 let noise read as long random periods);
  - a manual SCRAM latches a trip called `manual`, which is not a library trip, so the annunciator adds a `manual` tile.
- Tests: 17 new Vitest tests (`operator.test.ts`: truth guard, meters, derived period with the library's lag and noise, 10 ms spike, annunciator),
  2 new runtime tests (extremes), and 6 new Playwright tests (`operator.spec.ts`). Four deliberate breaks were each caught.
- Branch: `claude/m5-operator-design`. Checks: see the PR.

### 2026-09-27: PRs #3 to #6 merged into main (user OK)

- What: the user said "Yes merge". The other session also recommended it. I merged the four PRs in order, each with a merge commit:
  1. #3 M3 viewer: `6d37c81`.
  2. #4 browser e2e check: `41c7172`.
  3. #5 M4 live explorer: `35273d0`.
  4. #6 M5 operator panel: `fed44a7`.
- Before each merge, I merged `main` into the PR branch and ran `npx tsc --noEmit`, Vitest, all Playwright tests and `python3 scripts/premerge.py` (all pass).
  I then waited for both CI jobs (`premerge` and `e2e`) to pass on the new head. The only conflicts were in this file. I kept the entries from both sides.
- On `main` now: 181 Vitest tests, 14 Playwright tests, and 108 Python tests.
- The hourly PR check-ins are stopped.
- **For the local session:** the M5 items for you are still open: ARCHITECTURE §3 (alarms are derived in the view) and the `rod.setTarget` finding in the M4 entry.
- Branch: `claude/kind-bohr-p73819` (this log entry only).

### 2026-09-27: M6 instructor view design (proposal, waiting for the user)

- What: `docs/m6-instructor-design.md`. No code yet. Decisions D1–D6 are open for the user.
- Findings the other session may want to know (plan 06 assumes things the engines do not have):
  - no rod faults (stuck, will not scram, drop) and no instrument drift;
  - `fault.reactivity` adds to a running total, with no fault id and no clear (ARCHITECTURE §2 lists `fault.inject` and `fault.clear` with ids);
  - the snapshot does not list active instrument faults (the runtime can read the engine's public `faults` field, so this is not a request).
  The recommended options need no engine change for the first slice. Possible later requests, only if the user picks those options:
  `fault.rod` and instrument drift in both engines (D3a), and an ARCHITECTURE change from "one owner" to "one shared worker" (D2a).
- Branch: `claude/m6-instructor-design`, based on `main` (with `1442af9` merged in).
- User decision (2026-09-27): approved with D1–D6 = option a, and four amendments:
  coarse sessions reject pulse mode and `rod.fire` with a clear reason, and the time bar shows the step;
  reactivity clear comes from the engine (added to the D3a request);
  with two windows, the worker enforces each window's role;
  compare shows each branch's fork step and command count.
- **For the local session:** the user said you will do D3a after your M2 runs: rod stuck, no-scram, drop and clear; instrument drift; reactivity clear.
  Also the ARCHITECTURE change from "one owner" to "one shared worker".
  Note for the reactivity clear: today `fault.reactivity` accepts any extra field and adds `deltaRho ?? 0`, so a `{kind: "clear"}` is accepted as a no-op by the current engine.
  Please make the new command detectable (for example, a new engine version in the pins), so the view offers clear only when the engine has it.

### 2026-09-27: M6 slice S1 (one window) implemented

- What: `web/src/views/instructor/` (`time.ts`, `timeline.ts`, `faults.ts`, `truth.ts`, `panel.ts`) and the `instructor` layout in `web/src/app/main.ts`.
  Runtime: active faults in each snapshot message, and coarse sessions reject pulse mode and `rod.fire` with `REJ_COARSE_STEP` (amendment 1).
  The operator panel shows the text for that reason, and its rate menu now follows the clock (the instructor can set the rate).
- Finding for the local session (not a request yet, 2026-09-27): **a reactivity step trips `period-short` at once.**
  The trip reads `truth.period`, which has no lag. Right after a step, the prompt jump gives a very short period.
  On the synthetic core, steps of 5, 10, 20 and 40 pcm all trip after one 10 ms step. `triga-jsi-242` has the same trip.
  A real period channel has a lag. You may want the trip to read a lagged period instrument instead.
- Tests: 7 new runtime tests, 10 new Vitest tests (`instructor.test.ts`), and 5 new Playwright tests (`instructor.spec.ts`).
  Three deliberate breaks were each caught (no coarse check, no faults in the snapshot message, markers kept after a rewind).
- Branch: `claude/m6-instructor-design`. Checks: see the PR.

### 2026-09-28: M6 slice S2 (history: branches, notes, export) implemented

- What: branches in the runtime (`web/src/runtime/branches.ts`), with a switch that starts from the latest shared checkpoint.
  Also notes, session files version 2 (notes and branch; version 1 still imports), and CSV traces from a replay in a separate worker (`trace.ts`, `trace-worker.ts`).
  The instructor panel has notes, a compare table (amendment 4: fork step and command count next to the final values), and export and import.
- The worker now owns the timeline marks (`timeline` message), so S3's two windows see the same timeline.
- Fix: while paused, the runtime sends the clock message again when the step changes. Before, the time bar showed an old step after a rewind.
- Tests: 13 new runtime tests (`branches.test.ts`), including the main oracle: after a rewind and a different command, a switch back gives the old end state, and the shared-checkpoint path equals a replay from step 0.
  The CSV rows equal a step-by-step run's snapshots. 4 new Playwright tests (notes, branches and compare, session download and import, CSV download).
  Four deliberate breaks were each caught (no prefix check, no branch on rewind, notes kept on rewind, CSV one step late).
- Branch: `claude/m6-history`, based on `main` at `f543532`. Checks: see the PR.

### 2026-09-28: M6 slice S3 (two windows) implemented

- What: one runtime for several windows (`web/src/runtime/runtime.ts`), a SharedWorker entry (`shared-worker.ts`), and roles enforced by the worker (amendment 3).
  Windows with the same `?session=<id>` share one session, and "open operator window" opens the second window.
  The operator window cannot send time, step, rewind, import, branch switch, notes or `fault.*` commands. `pump.set` stays allowed (a plant control).
  Roles are not authenticated. That is on purpose for v1 (plan 06: nothing to protect).
- Fixes: the client runs every listener and sends its frame ack even when a listener throws (a stale shape handler stopped the snapshot stream after a library change). `load` resets the rate to 1×.
- Tests: 8 new runtime tests (`windows.test.ts`), 1 new client test, 3 new URL tests (`connection.test.ts`), and 6 new Playwright tests (`windows.spec.ts`, with several pages in one browser context).
  Four deliberate breaks were each caught (no role check, replies to every window, one frame gate for all windows, no state on attach).
- With S3, the M6 items in plan 06 are built, except the faults that wait for the engine (D3a) and branch overlay charts (a later slice).
- Branch: `claude/m6-two-windows`, based on `main` at `1d23921`. Checks: see the PR.

### R8 (open, 2026-09-28): update TODO and ARCHITECTURE for M6

- TODO: M6 "History buffer, rewind, time speed-up" and "Fault injection UI" are built (the fault UI has the faults that the engine has now; the rest wait for D3a).
  The milestone's Codex review is still to do.
- ARCHITECTURE: "One owner: ... a mirrored window detects owner loss" is now "one shared worker; the worker enforces each window's role" (the user said the local session makes this change).
  Also §2's comments "instructor only" on `time.set` and `time.rewindTo`: the worker now enforces this per window.
- Both files are outside the cloud session's scope.


### 2026-09-28: TODO Next #11 answered: the JSI Research Reactor Simulator (information for the local session)

- Source: [github.com/ijs-f8/Research-Reactor-Simulator](https://github.com/ijs-f8/Research-Reactor-Simulator), by Jan Malec and Dan Toškan, supervised by Luka Snoj (JSI Reactor Physics).
  Its site is reactorsimulator.ijs.si. It is described in "PC-based JSI research reactor simulator", Annals of Nuclear Energy 146 (2020) 107630.
- **License: GPL-3.0.** The repo is MIT, and our rule is no code from GPL projects. So this is an independent comparison and a reference only. Do not copy its code or data files.
- What it is: a C++ desktop program with a NanoGUI interface, tested on Windows, Linux and macOS (as its README says). The repo page shows no prebuilt releases.
  Its physics: 6-group point kinetics with an external source, RK4 at a 1 ms step, fuel-temperature feedback and xenon. Its parameters can be changed while it runs.
- Possible use: run the same scenario (for example a rod withdrawal or a pulse on the JSI TRIGA) in both simulators, and compare only the outputs.
  Keep only our own numbers and the comparison in this repo.
- Other free simulators found, for the record: the IAEA PC-based simulators (free for member states, but they need a Nucleus account, a request form and teaching-only terms, and they are not open source),
  and whatisnuclear/simulator (MIT, a web page with the physics on a server, 3 commits, looks inactive).
  None of them is MIT, runs fully in the browser, and reads a library made with OpenMC.
- Not checked: the IJS and IAEA pages themselves are blocked by the cloud container's network policy. The facts above come from search results and the GitHub page.
- Please tick TODO Next #11, or keep it open for the comparison run. TODO is outside the cloud session's scope.
