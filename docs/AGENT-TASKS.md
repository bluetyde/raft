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

About 1,200 lines written by agy across three tasks; break-even at best in Claude usage. Brief + preflight + verification + fixes cost about as much as writing the code:

| Task | Result | Cost beyond the brief |
|---|---|---|
| Golden vectors (`agy/golden-vectors`) | ~320 lines, correct as specified | Rewrote its main test: byte identity (my brief's error) → tolerance comparison; found and fixed the Python 3.12 `sum()` issue in the engine |
| Pulse screening (`agy/pulse-screening`) | ~600 lines, correct first time | Verification only. **The clear win** |
| ROS3P (`claude/agy-ros3p`) | ~250 lines, correct on the 4th run | 3 failed runs (background stall, blocked web fetch, stopped by the user); coefficients from the paper; a feasibility prototype that already was ROS3P; an added test for the γᵢ coefficients. **A net loss: this kind of task is Claude-only now** |

## Board

Status: `ready` (brief can be written now) · `blocked` (needs something first) · `pending` · `done` · `ongoing`.

### agy candidates (large, mechanical, strong oracle)

| ID | Task | Files | Oracle / proof of done | Status |
|---|---|---|---|---|
| A5 | `web/` scaffold (Vite + TS + Vitest) and a TypeScript library validator | `web/` | The **30 broken fixtures** in `schema/vectors/invalid/` each give exactly their `expected.json` codes; the synthetic core validates | ready; first confirm `npm install` works in the sandbox (agy's commands have no network) |
| A6 | TypeScript port of the engine (`physics_ref`: engine, library, numerics) | `web/src/sim/` | Vitest runs every vector in `schema/engine-vectors/` within its declared tolerances | blocked on A5 (and C5, which regenerates the vectors) |
| A7 | Scenario schema + validator + valid/invalid fixtures (typed predicates, plan 05) | `schema/scenario.schema.json`, `pipeline/scenario/`, fixtures | Every invalid fixture gives its expected code | ready |
| A8 | Command and snapshot schemas + fixtures (ARCHITECTURE interfaces) | `schema/command.schema.json`, `schema/snapshot.schema.json` | Snapshots from the golden-vector scenarios validate; invalid fixtures fail with expected codes | ready |

New dispatches use branches `claude/agy-<task>` (INSTRUCTIONS.md rule 5).

### Claude-only (judgment, data, precision-critical numerics, small changes)

| ID | Task | Why not agy | Status |
|---|---|---|---|
| C1 | M1 condition-matched comparison | physics judgment | done: proposal **NO-GO** ([results](validation/m1-c1-results.md)); awaiting the user's decision |
| C2 | Verify every parameter in `validation/data/triga-jsi/parameters.json` and the library against real sources (esp. UZrH cp(T), α(T)); then correct citations in `pipeline/library/build_triga.py` (the former A4) and re-run C1 unchanged | judgment on sources | ready |
| C3 | OpenMC JSI TRIGA model (M2) | OpenMC transport, nuclear data | blocked on C2 |
| C4 | Verify each agy result (skill step 4), log, propose merges | dispatcher's job | ongoing |
| C5 | Keep `"method"` in `pins()` (undo agy's omission) and regenerate `schema/engine-vectors/` | small, touches pinned contracts | ready |
| — | Anything like ROS3P: solvers, new numerical methods, coefficient work, precision-critical code | small and precision-critical (skill step 0) | — |

### Done

| ID | Task | Where |
|---|---|---|
| A1 | ROS3P solver option, ROS2 unchanged (would be Claude-only under step 0) | `main` via `claude/agy-ros3p` |
| A2 | Golden engine vectors | `main` via `agy/golden-vectors` + `claude/golden-vectors-fix` |
| A3 | Pulse data screening | `main` via `agy/pulse-screening` |
| A4 | Relabel unverified library values `assumed` (done by Claude in the M1 review) | `main` via `claude/m1-review` |

### Codex review points

- **Pending: ROS3P/engine line.** Run when Codex's quota resets (not the Claude-subagent fallback, by the user's choice):
  `--base d2af1ad --head 4559323 --auditor specification-gap-auditor` (the diff of the engine-line merge into `main`).
- After A6 (the port) and any change to `docs/library-format.md` or the schemas.
