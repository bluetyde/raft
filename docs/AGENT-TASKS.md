# Agent task board

How work is split under the delegation workflow (2026-09-26):
**Claude plans and verifies; Antigravity (agy, via the `antigravity-task` skill) implements well-specified tasks in the isolated
`agent-sandbox`; Codex (`codex-review` skill) gives a read-only second opinion on non-trivial diffs.**
Nothing merges to `main` until Claude has re-run the checks itself and the user agrees.

## What makes a task fit for agy

- The design is already decided and fits in a brief: files, functions, behavior, edge cases, tests.
- "Done" is a command whose output proves it. The best tasks have a test that fails if the idea is wrong,
  like an observed-order check for a solver or byte-identity for generated files.
- It runs in the sandbox: git, Python 3.12 (standard library only), Node 18. No conda, no OpenMC, no nuclear data.
  Network access for agy's own commands isn't guaranteed, so tasks needing `npm install` or `pip install` must be tried once first.
- It stays inside a few files, so parallel tasks don't collide.

Not for agy: judging data or sources, physics modelling choices, go/no-go calls, anything needing the WSL conda envs or OpenMC.

## Board

Status: `running` · `ready` (brief can be written now) · `blocked` (needs something first) · `claude` (not delegable) · `done`.

### Delegable to agy

| ID | Task | Files | Proof of done | Status |
|---|---|---|---|---|
| A1 | ROS3P order-3 solver option, ROS2 bit-identical | `physics_ref/engine.py`, `physics_ref/tests/test_ros3p.py` | Observed order 2.7–3.3; analytic tests pass with ROS3P; < 0.5× ROS2 steps on the post-shutdown case; ROS2 reference values unchanged | running (`agy/ros3p`) |
| A2 | Golden engine vectors for the TypeScript port | `physics_ref/vectors.py`, `physics_ref/tests/test_vectors.py`, `schema/engine-vectors/` | Byte-identical regeneration; behavior sanity checks (pulse, scram, rejections, located trip) | running (`agy/golden-vectors`) |
| A3 | Pulse data screening: missing values (`fwhm_s == 0`, blank temperatures), robust outlier flag per core config and $ value, exclusion report | `validation/pulse_loader.py`, new tests | Known bad rows (e.g. pulse 19) are flagged; counts reported; no silent drops | ready (after the user decides on the M1 review) |
| A4 | Relabel library sources to `assumed` / correct citations, from a list Claude supplies | `pipeline/library/build_triga.py`, regenerated `libraries/triga-jsi/` | Regenerated library validates; label counts match the list | blocked on Claude's list (C2) |
| A5 | `web/` scaffold (Vite + TS + Vitest) and a TypeScript library validator that passes every fixture in `schema/vectors/` with the same error codes | `web/` | `npm test` passes; every invalid fixture gives exactly its `expected.json` codes | ready; first check that `npm install` works in the sandbox |
| A6 | TypeScript port of `physics_ref` (engine, library, numerics) matching the golden vectors within their tolerances | `web/src/sim/` | Vitest runs every vector in `schema/engine-vectors/` within tolerance | blocked on A2 and A5 |
| A7 | Scenario schema + validator + fixtures (typed predicates as in plan 05) | `schema/scenario.schema.json`, `pipeline/scenario/`, fixtures | Valid and invalid fixtures give expected codes | ready |
| A8 | Command and snapshot schemas + fixtures from ARCHITECTURE's interfaces and the engine | `schema/command.schema.json`, `schema/snapshot.schema.json` | Engine snapshots from A2 validate; invalid fixtures fail | blocked on A2 |

### Claude (judgment, data, environments)

| ID | Task | Status |
|---|---|---|
| C1 | Redo the M1 comparison: pick a well-documented core configuration, calibration/held-out split, reactivity uncertainty, FWHM definition from traces; propose GO/NO-GO to the user | after the user decides on the review |
| C2 | Verify every parameter in `validation/data/triga-jsi/parameters.json` and the library against real sources; produce the relabel list for A4 | ready |
| C3 | OpenMC JSI TRIGA model (M2): needs the WSL `openmc-vr` env and nuclear data | blocked on C2 and the `openmc-vr` env |
| C4 | Verify each agy result (scope, checks, pasted commands, test-weakening), then log and propose merges | ongoing |

### Codex review points

- After A1, A2 and A6 (numerical code and the port): `codex-review --base <base> --head <branch>`.
- After C1 (the comparison code and its statistics).
- Any change to `docs/library-format.md` or the schemas.

## Rules for every delegated task

1. Post a CLAIM in `messages/virtual-reactor.md` naming the branch before running agy.
2. The brief carries the design; agy makes no design decisions.
3. Claude verifies independently (the skill's step 4). agy's pasted output is a claim, not evidence.
4. Results stay on their `agy/*` branch until the user agrees to merge.
5. The log entry says what agy did, what Claude verified and how, and what's unverified.
