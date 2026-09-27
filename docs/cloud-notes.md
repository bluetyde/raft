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

None open.

## Log

### 2026-09-27: baseline check

- Branch: `claude/kind-bohr-p73819` at `main` `03e6cb4`, no changes.
- `python3 scripts/premerge.py` with `VR_PYTHON=python3`, Python 3.11.15, Node 22.22.2 (the container has no Node 24 yet): all four stages pass.
  Python 108 tests (156 s), web 77 tests in 9 files.
- TODO Next #9 (A9, pre-merge script) is already done. The other session updates TODO and the board on `claude/todo-a9-done`, so this session leaves those files alone.

### 2026-09-27: CI workflow

- What: `.github/workflows/premerge.yml` runs `python3 scripts/premerge.py` on every push and every pull request.
  It uses Ubuntu, Python 3.11, Node 24, `npm ci --ignore-scripts` in `web/`, and `VR_PYTHON=python3`.
  A newer run on the same ref cancels an older one.
- Branch: `claude/kind-bohr-p73819`.
- Checks: `python3 scripts/premerge.py` in the container (Node 22.22.2): see the PR for the summary table. CI on Node 24 is the reference.
