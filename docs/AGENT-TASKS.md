# Agent task board

How work is split under the delegation workflow:
**Claude plans and verifies; Antigravity (agy, via the `antigravity-task` skill) implements delegated tasks in the isolated
`agent-sandbox`; Codex (`codex-review` skill) gives a read-only second opinion on non-trivial diffs.**
Nothing merges to `main` until Claude has re-run the checks itself and the user agrees.

## Whether to delegate

Decide with **step 0 ("Is it worth delegating?") of the antigravity-task skill**, `~/.claude/skills/antigravity-task/SKILL.md`.
It's the single source for the rule; this board only applies it to this project's tasks.
How to brief, preflight, run and verify is in the same file (steps 1–6).

### Evidence from this project (2026-09-26)

First three tasks (~1,200 lines): break-even at best in Claude usage; brief + preflight + verification + fixes cost about as much as writing the code. The clear wins were the ones step 0 favours: large, mechanical, contract already fixed, strong oracle:

| Task | Result | Cost beyond the brief |
|---|---|---|
| Golden vectors (`agy/golden-vectors`) | ~320 lines, correct as specified | Rewrote its main test: byte identity (my brief's error) → tolerance comparison; found and fixed the Python 3.12 `sum()` issue in the engine |
| Pulse screening (`agy/pulse-screening`) | ~600 lines, correct first time | Verification only. **The clear win** |
| Command/snapshot schemas, A8 (`claude/agy-contracts`) | ~600 lines (2 schemas, validator, 17 invalid fixtures, 11 tests), correct first time, no reruns | One brief (contract already fixed by the engine's code), preflight, verification: 4 targeted source breaks all caught. **A textbook step-0 win** |
| ROS3P (`claude/agy-ros3p`) | ~250 lines, correct on the 4th run | 3 failed runs (background stall, blocked web fetch, stopped by the user); coefficients from the paper; a feasibility prototype that already was ROS3P; an added test for the γᵢ coefficients. **A net loss: this kind of task is Claude-only now** |

## Board

Status: `ready` (brief can be written now) · `blocked` (needs something first) · `pending` · `done` · `ongoing`.

### agy candidates (large, mechanical, strong oracle)

| ID | Task | Files | Oracle / proof of done | Status |
|---|---|---|---|---|
| A5-1 | TS port of `pipeline/library/minischema.py` + every semantic check of `validate.py` (28 codes) + Vitest tests | `web/src/library/` | The **30 broken fixtures** in `schema/vectors/invalid/` give exactly their `expected.json` codes; synthetic core and `triga-jsi` validate | ready after A5-0 (`--node 24 --setup "npm ci --ignore-scripts"`) |
| A6-1 | TS port of `physics_ref` (numerics, library, engine incl. ROS3P) + its Python tests ported + a Vitest runner over every golden vector | `web/src/sim/` | Every vector in `schema/engine-vectors/` within its declared tolerances; ported analytic tests; snapshots valid against `schema/snapshot.schema.json` | blocked on A5-1 and C5. Split at numerics/library vs engine if the brief gets too large |
| A7 | Scenario schema + validator + fixtures | `schema/scenario.schema.json`, `pipeline/scenario/` | Every invalid fixture gives its expected code | **on hold (user)**. Step 0 failed (spec still moving); the format design is Claude's when resumed |

New dispatches use branches `claude/agy-<task>` (INSTRUCTIONS.md rule 5).

Sandbox Node setup landed (2026-09-26): `--node 24` (24.18.0, matches Windows) and `--setup "npm ci --ignore-scripts"` (runs with network before agy starts; a committed lockfile is required).

### Claude-only (judgment, data, precision-critical numerics, small changes)

| ID | Task | Why not agy | Status |
|---|---|---|---|
| C1 | M1 condition-matched comparison | physics judgment | done: proposal **NO-GO** ([results](validation/m1-c1-results.md)); awaiting the user's decision |
| C2 | Verify every parameter in `validation/data/triga-jsi/parameters.json` and the library against real sources (esp. UZrH cp(T), α(T)); then correct citations in `pipeline/library/build_triga.py` (the former A4) and re-run C1 unchanged | judgment on sources | ready |
| C3 | OpenMC JSI TRIGA model (M2) | OpenMC transport, nuclear data | blocked on C2 |
| C4 | Verify each agy result (skill step 4), log, propose merges | dispatcher's job | ongoing |
| A5-0 | `web/` scaffold: `package.json` with pinned deps (TypeScript, Vite, Vitest), lockfile generated on Windows (Node 24), `tsconfig`/Vitest config; design decisions for A5-1 (TS port of `minischema` instead of a JSON Schema library, injected file reader, WebCrypto SHA-256) | dependencies and lockfile are the dispatcher's by skill rule; small | ready |
| C5 | Keep `"method"` in `pins()` (undo agy's omission) and regenerate `schema/engine-vectors/` | small, touches pinned contracts | ready; must land before A6-1 (the vectors are A6's oracle) |
| A6-0 | A6 design in the brief: module layout, API parity with Python, SplitMix64 on BigInt, explicit left-to-right sums, library loading via A5-1, snapshot validation via the TS minischema; Web Worker out of scope | design decisions | with the A6-1 brief |
| C6 | Web Worker runtime, clock and command bus (ARCHITECTURE runtime loop) | scheduling semantics still open | later |
| — | Anything like ROS3P: solvers, new numerical methods, coefficient work, precision-critical code | small and precision-critical (skill step 0) | — |

### Done

| ID | Task | Where |
|---|---|---|
| A1 | ROS3P solver option, ROS2 unchanged (would be Claude-only under step 0) | `main` via `claude/agy-ros3p` |
| A2 | Golden engine vectors | `main` via `agy/golden-vectors` + `claude/golden-vectors-fix` |
| A3 | Pulse data screening | `main` via `agy/pulse-screening` |
| A4 | Relabel unverified library values `assumed` (done by Claude in the M1 review) | `main` via `claude/m1-review` |
| A8 | Command and snapshot schemas + validator + fixtures | `main` via `claude/agy-contracts` |

### Codex review points

- **Pending: ROS3P/engine line.** Run when Codex's quota resets (not the Claude-subagent fallback, by the user's choice):
  `--base d2af1ad --head 4559323 --auditor specification-gap-auditor` (the diff of the engine-line merge into `main`).
- After A6 (the port) and any change to `docs/library-format.md` or the schemas.
