# Workflows

Step-by-step procedures for the recurring kinds of work. The structure behind them is in [ARCHITECTURE.md](ARCHITECTURE.md).

**This file is the canonical place for setup, environments, ports and process ownership.** Other documents link here instead of repeating it.
[TOOLING.md](TOOLING.md) is a dated survey (history and options), not setup instructions.

## 0. Setup (canonical)

- **Pipeline env:** WSL2 conda env `openmc-vr`, created from the project's own `pipeline/environment.yml` (written with the first scaffold),
  never by modifying the shared `openmc-mcnp`. Nuclear data location comes from `OPENMC_CROSS_SECTIONS`; data **identity** (digest) is recorded separately from its path.
- **Web:** Node on Windows (WSL has no Node). `web/package-lock.json` is committed; `npm ci` reproduces it.
- **Dev port:** `VR_PORT` (default **5187**). Each checkout or agent picks its own free port and records it in its log entry, so concurrent sessions don't collide.
- **Processes:** stop only processes your session started, then confirm your port is free.
- **Fast checks (run before every handoff):** from the repo root, `python -m unittest` (standard library only; Python ≥ 3.11; about 40 s, mostly the pulse and xenon physics tests).
  In an env with scipy (e.g. WSL `openmc-mcnp`/`openmc-vr`) it also runs the independent-integrator check.
  Validate any library with `python -m pipeline.library.validate <folder>`. Regenerate fixtures with `python -m pipeline.library.synthetic` and review the diff.
- **Fast checks need no OpenMC:** the synthetic fixture lets the headless tests and web build run on a clean checkout (and in CI) without nuclear data.

## 1. Build a reactor library (offline)

Runs in WSL2, `conda activate openmc-vr` (a clone of `openmc-mcnp`; never modify the shared env for this project). Check `OPENMC_CROSS_SECTIONS` is set in the new env.

1. **Model:** write or update `pipeline/models/<reactor>.py`. It takes a parameter dict and returns an `openmc.Model`.
2. **Verify:** `python -m pipeline verify <reactor>` runs the reference case and compares k-eff with the benchmark.
   Don't continue if it fails. Log the result.
3. **Plan:** `python -m pipeline plan configs/<reactor>.yaml` expands the cases and prints the estimated core-hours.
   Check the budget before continuing (tell the user if it's many hours).
4. **Run:** `python -m pipeline run configs/<reactor>.yaml`. It's resumable and cached by case hash, so run it in the background and rerun it after interruptions.
5. **Extract:** `python -m pipeline extract <reactor>` produces tables, shapes and uncertainties.
6. **Build:** `python -m pipeline build <reactor>` writes `libraries/<reactor>/` and validates it against the schema.
7. **Validate:** `python validation/run_all.py <reactor>` writes the validation report into the library.
8. **Log:** add the OpenMC version, case counts, run time and key results to `messages/virtual-reactor.md`.

(These commands are the planned interface. They're written as the pipeline is built.)

## 2. Change the physics

The Python reference is the source of truth. TypeScript follows it.

1. Change `physics_ref/` and its tests. All tests must pass.
2. Regenerate the golden vectors: `python -m physics_ref.vectors` → `schema/vectors/`.
   Vectors carry provenance (generator commit, solver settings, tolerances). **Changed expected results need a stated reason and a readable before/after summary**
   in the commit or log. Never refresh expectations just to make a test pass. The independent checks (analytic tests, scipy path) must still pass unchanged.
3. Update `web/src/sim/` until `npm test` passes against the new vectors.
4. If the change needs new library data, bump `schemaVersion` (see [plans/03](plans/03-library-format.md)) and update the builder and both validators.
5. Commit Python, vectors and TypeScript **together**, so the repo never has them out of step.

## 3. Work on the web app

1. `cd web && npm run dev` (port `VR_PORT`, default 5187; see section 0). Or use the preview tools with a `.claude/launch.json` entry.
2. With no real library yet, the app loads `schema/vectors/synthetic-core/`.
3. Check changes in the browser: console clean, 3D renders, commands change state.
4. `npm test` (sim core + vectors) and `npm run build` before handing off.
5. **Stop the dev server you started** when done, then confirm your port is free. Never stop another session's or another agent's process.

## 4. Add a scenario

1. Write `web/public/scenarios/<id>.json` against `schema/scenario.schema.json`.
2. Every threshold in it must come from the library or a cited source. No invented setpoints.
3. Add a headless test: run the scenario's scripted events with a scripted "operator" and check the goals can be met and trips fire when expected.

## 5. Add a new reactor

1. Collect the sources (benchmark, design reports) into `validation/data/<reactor>/`, with citations.
2. Workflow 1 with a new model file and config.
3. Render geometry: primitives if the reactor is simple, otherwise the sampled-mesh converter (plan 03).
4. Scenarios for it (workflow 4).
5. **Within an existing model capability, a needed code change is a bug.** Log it and fix it generally.
   If the reactor needs physics the capability doesn't have, that's a **new capability**: propose it in the log, version it, and make old libraries keep working.

## 6. Release

1. All CI green; validation reports current for every shipped library.
2. Bump versions (app, schema if changed, libraries).
3. Changelog entry.
4. Tag, build static files, attach large library arrays as release assets.
5. Check the pre-release items in [plans/09](plans/09-open-release.md).

## 7. Multi-agent rules for this project

Follows [`messages/INSTRUCTIONS.md`](../../messages/INSTRUCTIONS.md). Specific to this project:

- **Log:** `messages/virtual-reactor.md`. Read it at the start of every session and append at the end.
- **Claims** by area, matching the plans: `CLAIM: physics-core`, `CLAIM: openmc-pipeline`, `CLAIM: library-format`, `CLAIM: explorer`, `CLAIM: operator`, `CLAIM: instructor`, `CLAIM: validation`.
  Two agents can work in parallel on different claims (see the dependency graph in ARCHITECTURE.md).
- **Library format changes affect everyone.** Post the proposed change in the log before editing the schema, and don't change it under someone's open claim.
- **Once it's a git repo:** separate clones per agent, per the shared rules. No worktrees.
- **OpenMC runs share one machine:** say in the log when a long run starts and how many threads it uses. Don't start a second big run on top of someone else's.
- **Keep TODO.md current:** check off finished items with the date, and add discovered work under the right milestone.
