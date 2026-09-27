# Cloud notes

A log for the browser-track session that runs in the cloud. The OpenMC session reads it to see what changed and what this session needs.
Add a dated entry for each piece of work: what changed, the branch, and the checks with their results.
Put requests for the other session under "Requests". Mark a request "done" when it is done, and do not delete it.

## Scope of the cloud session

- Owns: `web/src/runtime/`, `web/src/views/`, `web/src/app/`, `web/index.html`, `web/package.json` and its lockfile (dependencies only), `.github/`, this file, and its own design docs under `docs/`.
- Does not edit: `physics_ref/`, `web/src/sim/`, `web/src/library/`, `web/src/contracts/`, `schema/`, `pipeline/`, `validation/`, `libraries/`.
  Engine or schema changes come here as requests, because the Python and TypeScript engines must stay in step.
- Works on branches with pull requests only. It never pushes to `main` or merges into it.

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

