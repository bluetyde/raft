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
- Possible request R3 (only if the user picks D1 option T3): let a session change `outerDt` at a logged boundary. Not requested yet.
- Branch: `claude/c6-runtime-design` (based on `claude/kind-bohr-p73819`, because this file is not on `main` yet).

