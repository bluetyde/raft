# C6: Web Worker runtime (design)

Status: **approved by the user on 2026-09-27, with the recommended option for D1–D4** (see the table at the end). Implemented in `web/src/runtime/` on the same branch (39 Vitest tests, plus a manual smoke run in Chromium, section 11).
Scope: TODO Next #6 and the "Runtime loop" in [ARCHITECTURE.md](ARCHITECTURE.md). The runtime runs `web/src/sim`'s `Engine` in a Web Worker.
It has a clock, a command bus, a snapshot and event stream, and history (checkpoint, rewind, replay).
Out of scope: views, the scalar plot buffer, multi-window mirroring (`BroadcastChannel`), scenarios, and the memory-budget benchmark (TD-08, after C6).

The engine does not change. The runtime uses only its public API: `new Engine`, `submit`, `step`, `snapshot`, `checkpoint`, `session`,
`Engine.restore` and `Engine.replay`, plus the read-only fields `t`, `stepIndex`, `halted`, `events` and `lib`.
The messages carry commands and snapshots in the forms of `schema/command.schema.json` and `schema/snapshot.schema.json`.

The decisions are marked **D1–D4**, each with its options. The table at the end gives the choices.

## 1. What the engine already fixes

These facts come from `web/src/sim/engine.ts` and set most of the runtime's behaviour:

- Sim time is `stepIndex × outerDt`. `outerDt` is part of the engine config, and the session and checkpoint pins include it. It cannot change during a session.
- `submit(cmd, clientId)` appends the command to the log with the current `stepIndex` and returns its sequence number. It does not apply the command.
- The next `step()` applies the pending commands in sequence order, integrates one outer step, then evaluates the boundary (instruments, then trips).
  So a command takes effect at the boundary where it was submitted, after the trips already found at that boundary.
- The accept or reject result is not returned by `submit`. It appears after the step as an event `{type: "command", seq, status, reason}` in `engine.events`.
- `time.set` and `time.rewindTo` (ARCHITECTURE §2) are not engine commands. The engine rejects unknown types with `REJ_UNKNOWN_COMMAND`.
  Time control is therefore runtime state, and it is not in the command log. Replay does not need it, because each logged command carries its step index.
- When `halted` is set (a `reject` table went out of range), `step()` does nothing.

## 2. Measured cost (this container, Node 22, one core)

| Operation | Synthetic core | `triga-jsi-242` |
|---|---|---|
| `step()`, steady, `outerDt` 10 ms | 62 µs | 54 µs |
| `step()`, one rod moving | 87 µs | 53 µs |
| `step()`, first 20 steps of a pulse | **58–63 ms** | 2–8 ms |
| `snapshot()` / with shape | 9 µs / 48 µs (150 bins) | 5 µs / 62 µs (560 bins) |
| `checkpoint()` / `Engine.restore()` | 14 µs / 0.33 ms | 8 µs / 0.27 ms |
| 60 s of steady sim at `outerDt` 0.01 / 0.1 / 1 s | 179× / 1992× / 11157× real time | 187× / 1872× / 15130× real time |

A second test used a 4-hour transient on `triga-jsi-242`: a rod withdrawal, a scram at 600 s, then xenon build-up (at about 1 mW, so not a full-power case).
It changed only `outerDt`:

| `outerDt` | Speed reached | Largest relative difference from the 10 ms run (t = 300 s, 600 s, 1 h, 4 h) |
|---|---|---|
| 10 ms | 31× | — |
| 0.1 s | 238× | power 2e-11, xenon 4e-10 |
| 1 s | 1993× | power 2e-11, xenon 4e-8, fuel temperature 9e-9 K (absolute) |

The step cost is higher while the state changes (31× here, against about 150× at steady state).
The results do not change with `outerDt`, because inside each outer step the adaptive solver chooses its own steps to meet `rtol`.

Three results drive the design:
1. The cost is per outer step, and almost independent of the step length. At 10 ms outer steps, one core gives about **150× real time** at most.
   The 600× and 3600× presets in [plan 06](plans/06-instructor.md) need a longer outer step (D1).
2. One step of a pulse can take about 60 ms. A step cannot be split, so this is the worst-case delay before the worker reads the next message.
3. A longer `outerDt` changes only what happens at boundaries: commands apply up to one outer step later in sim time, instruments and noise are sampled once per outer step,
   and trips on instrument readings are checked once per outer step. Trips on truth signals are still located inside the step (to 0.1 µs).
   So a slow scenario (a xenon wait) can use 1–2 s outer steps and reach 3600×, but a pulse scenario needs 10 ms.

## 3. Parts

All files are in `web/src/runtime/`. Only `worker.ts` and `client.ts` touch Worker APIs, so everything else runs under Vitest in Node.

| File | Role |
|---|---|
| `protocol.ts` | Message types and `PROTOCOL_VERSION`. No logic. |
| `runtime.ts` | The `Runtime` class: clock, command bus, snapshot and event stream, history. It gets `now()`, `schedule(fn)` and `post(msg, transfer)` from its host, so tests drive it with a fake clock. |
| `history.ts` | Checkpoint store, rewind and session import/export. |
| `readers.ts` | `LibraryReader` implementations: fetch from a base URL, and a map of transferred files (File API folder drop). |
| `worker.ts` | Worker entry point. Connects `onmessage` and `postMessage` to one `Runtime`. Yields through a `MessageChannel`, which has no minimum delay. |
| `test-helpers.ts` | Test only: a fake host with a controllable wall clock, and library folders read into the `files` form. |
| `client.ts` | Main-thread `RuntimeClient`: typed calls, a promise per command acknowledgement, snapshot and event subscriptions, worker error detection. |

## 4. Messages

Every message has `kind` and the first one has `protocol`. The worker is the only authority for state.

| Direction | `kind` | Content |
|---|---|---|
| main → worker | `load` | `source` (`{url}` or `{files}`, files transferred), `init`, `seed`, `config` |
| | `command` | `clientSeq`, `clientId`, `cmd` (command schema) |
| | `time` | `rate` (sim s per wall s), `paused` |
| | `step` | `n` outer steps, only while paused |
| | `rewind` | `step` (target step index) |
| | `session.export` / `session.import` | — / session file |
| | `frameAck` | — (the main thread has drawn the last snapshot) |
| worker → main | `loaded` / `loadFailed` | library id, digest, pins, `outerDt` / issues `{code, path}` or an `E_INIT_*` code |
| | `queued` | `clientSeq`, `seq`, `step`, `t` |
| | `ack` | `clientSeq`, `seq`, `status`, `reason`, `t` |
| | `snapshot` | the engine snapshot; `shape` as a transferred `Float32Array` when sent |
| | `events` | every new engine event, in order |
| | `clock` | requested rate, achieved rate, `paused`, `limited` with a cause (`cpu`, `halted`, `solver`) |
| | `history` | checkpoint steps, first and last step, whether thinning happened |
| | `rewound` | the step reached after a rewind or a session import, and the previous timeline as a session file |
| | `error` | a request that could not be done: the request kind, a code (`E_BAD_ARGUMENT`, `E_RUNNING`, `E_FAULTED`, ...) and a message |
| | `fault` | an unexpected error, with its message; the clock is paused |

## 5. Clock

- **Pacing.** On resume or a rate change, the runtime records an anchor (wall time, sim time).
  The target sim time is `anchorSim + rate × (now − anchorWall)`. The runtime calls `step()` while `engine.t` is below the target.
- **Slices.** Steps run in slices of at most 4 ms wall time, and each slice has at least one step. Between slices the worker yields, so it reads messages.
- **Falling behind.** The runtime never skips physics. If the sim is more than 0.25 s of wall time behind its target, the runtime moves the anchor to now.
  The sim then runs slower than requested, and it does not race to catch up later. The `clock` message reports the achieved rate over the last wall second, with `limited: "cpu"`.
- **Pause** stops stepping. **Resume** sets a new anchor. **Step n** while paused runs exactly `n` steps, for the instructor and for tests.
- **Halt.** If `engine.halted` is set after a step, the runtime pauses with `limited: "halted"` and the halt reason.
- **Solver error.** If `step()` throws, the runtime pauses and sends `fault`. The engine state after a throw is not trusted, so the only way on is a rewind to a checkpoint.

**D1: time rates above about 150×.**

| Option | What it means | Cost |
|---|---|---|
| T1 | Keep one `outerDt` (10 ms) for all sessions. The rate caps at about 150×, and the UI shows the achieved rate. | Nothing. Xenon scenarios (hours) take minutes of wall time. |
| **T2 (chosen)** | `outerDt` is a session setting, fixed for the session (the engine already supports this, and pins it). A xenon scenario uses, for example, 0.5 s. The UI offers only the rates the session can reach. | Instruments are sampled and boundary trips are checked once per outer step, so a coarse session reacts later to fast events. It suits slow scenarios, not pulses. |
| T3 (later, needs the engine) | Let a session change `outerDt` at a logged boundary, so one session can be fine during a pulse and coarse during a xenon wait. | An engine change in Python and TypeScript: time is no longer `stepIndex × outerDt`. Request R3 in `docs/cloud-notes.md`, only if you choose it. |

## 6. Command bus

1. The view calls `client.command(cmd)`. The client adds `clientSeq` and its `clientId` (the view name: `operator`, `instructor`, `explorer`).
2. The worker reads the message between slices, so the command lands at the first boundary after it arrives.
   The wall-time delay is at most one slice plus one step: normally under 5 ms, and up to about 60 ms during a pulse. In sim time the delay is about `rate ×` that.
3. The worker checks the structure with `validateCommand` (`src/contracts`). A structural error gives an immediate `ack` with `REJ_SCHEMA`. The command is not submitted or logged.
4. Otherwise the worker calls `engine.submit(cmd, clientId)` and sends `queued` with the sequence number, step and sim time.
5. After the next step, the engine's `command` event gives the result. The worker sends `ack` with the engine's status and reason unchanged.

Runtime-only reasons: `REJ_SCHEMA`, `REJ_NO_LIBRARY` (nothing loaded), `REJ_HALTED` (the engine is halted, so the command would never apply),
`REJ_FAULTED` (a solver error stopped the clock; only a rewind continues), `REJ_REWOUND` (a queued command was after the rewind point and was discarded)
and `REJ_SESSION_REPLACED` (a queued command was discarded by a new load or a session import).

**D2: commands while paused.**
- **(a) Queue them (chosen).** They are submitted at the paused boundary and apply on the next step, at resume or at a single step. The `ack` comes then. This is what the engine does anyway, and it is deterministic. The instructor can pause, set up a fault, and resume.
- (b) Reject them with `REJ_PAUSED`. Simpler to explain to an operator, but an instructor cannot prepare actions during a pause.

**D4: who may send which command.** ARCHITECTURE marks faults as instructor-only.
- **(a) No check in C6 (chosen).** Plan 06 says instructor mode is only a toggle in v1. The views decide which controls they show.
- (b) The runtime checks a role table by `clientId` and rejects `fault.*` from other views with `REJ_ROLE`. Cheap, and useful later for a scenario's allowed controls.

## 7. Snapshots and events

- **Snapshots** are coalesced. After a slice, the worker sends `engine.snapshot()` only if at least 1/30 s of wall time has passed (a setting, 30–60 Hz), and only if the main thread acknowledged the previous one (`frameAck`).
  A slow main thread gets fewer frames and never a queue. On pause, one last snapshot is sent.
- **Shape** is included on the first frame, after a rewind, and when a rod moved more than 0.001 or the fuel temperature changed more than 0.5 K since the last shape sent.
  It goes as a new `Float32Array` that is transferred, so the worker gives up that buffer and does not copy it. (TRIGA 242: 560 values, 2.2 KB.)
- **Events** are authoritative. The engine's `events` list is append-only. The runtime keeps a cursor and sends every new event, in order, after each slice.
  Events are never coalesced or dropped, and they do not wait for `frameAck`. After a restore, the engine's list restarts with a `restored` event, and the cursor resets.
- **Pulse extremes** come from the engine (`truth.peakPower`, `truth.peakTime`), so a 30 Hz display cannot miss a millisecond peak.

## 8. History: checkpoints, rewind, session files

- **Checkpoints** are taken at load and then every 10 s of sim time (a setting). The store keeps at most 128.
  At the limit, it drops every second checkpoint in the older half, and the `history` message says that thinning happened.
  The command log is always complete, so a replay from step 0 is always possible.
- **Memory.** `engine.checkpoint()` includes a copy of the whole command log, so stored checkpoints would grow with the square of the session length.
  The store removes `commandLog` and keeps its length. On restore, it rebuilds the log from the runtime's one log (it is append-only, so the prefix is identical).
  A test checks that a rebuilt checkpoint deep-equals the original. (A quick check on the synthetic core already gives an identical log.)
- **Rewind to a step.** Take the latest checkpoint at or before the target, `Engine.restore` it, then run the same loop as `Engine.replay`, starting from that checkpoint:
  submit each logged command at its step (skipping commands with `seq < cp.nextSeq`, which the checkpoint already holds) and step until the target. Then the clock is paused.
  The re-submitted commands get their original sequence numbers, because the checkpoint restores `nextSeq`.
  As in `Engine.replay`, commands logged at the target step itself stay queued: they were sent at that boundary, so they apply on the next step.
- **D3: commands after the rewind point.**
  - **(a) Truncate (chosen).** The future is discarded. Before that, the runtime keeps the old timeline as one in-memory session file, so the user can export it.
  - (b) Keep the future as a redo list, replayed on request.
  - (c) The full branch tree of plan 06. This is M6 work, and it builds on (a).
- **Session export** wraps `engine.session()` as `{format: "virtual-reactor-session", version: 1, endStep, session}`.
  `engine.session()` has no end step, so the wrapper adds one.
  **Import** calls `Engine.replay(lib, session, endStep)`. Its pin check (engine version and library digest) gives a clear error on a mismatch.

## 9. Library loading

- `load` builds a `LibraryReader` from the source, runs `validateLibrary`, and stops with `loadFailed` and the issues if there are any.
  Then it calls `loadLibrary` and `new Engine(lib, init, seed, config)`. An `InitError` gives `loadFailed` with its `E_INIT_*` code.
- A worker holds one library and one engine. A new `load` replaces both and clears the history.

## Later ways to more speed (not in C6)

- **T3:** change `outerDt` at a logged boundary, so one session can be fine during a pulse and coarse during a wait. Engine work in Python and TypeScript (request R3).
- **A faster engine step.** 55–320 µs per step is slow for a 13-value state, so profiling will probably find a few times more speed.
  The golden vectors must still pass, and this is the other session's work (request R4).
- More workers do not help: one timeline is computed one step after another.

## 10. Limits and Resource Bounds (TD-08)

| Item | Limit | At the limit |
|---|---|---|
| Unacknowledged snapshots | 1 per window | Newer snapshots coalesce and replace older ones before sending; extremes accumulate across all intervening steps (M5 amendment 1). |
| Binary array transfer | 1 buffer per shape update | Buffer ownership transferred via `Transferable` (`[own.buffer]`) to eliminate worker-to-window copy overhead. |
| Stored checkpoints | 128 default (`maxCheckpoints`) | Bounded in `CheckpointStore`; thin the older half while preserving step 0 and the latest checkpoint. Stored without command log to prevent quadratic growth. |
| Retained branches | 32 (`MAX_BRANCHES`) | Oldest timeline dropped when creating the 33rd branch. |
| Strip charts | 3,000 buckets over 600 s window | Hard bound of 6,000 items (including gaps); evicts older points and keeps bucket min/max. |
| Events to send | none | Never dropped. Commands, trips, halts, and restores dispatch immediately regardless of frame backpressure. |
| Engine `commandLog` and `events` | Append-only | About 120 B per command and 95 B per event as JSON. Exportable session files pin the exact command sequence and initial state so replaying from step 0 is 100% deterministic even when intermediate checkpoints have been thinned. |

### TD-08 Measured Verification (`web/src/runtime/bounds.test.ts`)
- **Backpressure & Coalescing**: 50 unacknowledged simulation steps emit at most 1 snapshot; authoritative trip and command acks dispatch without blocking; acknowledged frames immediately receive the latest snapshot and extremes.
- **Buffer Ownership**: Shape updates transfer the underlying `ArrayBuffer` without cloning.
- **Checkpoint Thinning & Replay**: Checkpoint store caps at quota, drops older intermediate checkpoints, and rewinding to both preserved and thinned steps succeeds.
- **Exportability**: Exported session files after checkpoint thinning successfully import and reconstruct the exact engine state and trajectory.
- **Memory & Latency Benchmark**:
  - Environment: Windows 11 x64, 16 CPUs, Node.js v24.18.0.
  - 4,000 fine simulation steps under continuous operator commands (`rod.move`) and frame backpressure ran in ~300 ms.
  - Heap growth: **< 3.5 MB** (well under the 35 MB budget).
  - Command acknowledgment latency: 0 steps delay.
  - Post-run rewind and forward replay: bit-identical.

## 11. Tests (Vitest, Node, fake clock)

- **Clock:** at rates 1, 10 and 100 with a fake clock, the sim time follows `rate × wall time`. With a slow fake step, the achieved rate drops, no step is skipped, and `limited` is `cpu`.
- **Pause and step:** no steps while paused, and `step n` runs exactly `n`.
- **Commands:** each gets `queued`, then `ack` with the engine's result. A structural error gives `REJ_SCHEMA` with no engine call.
  A command sent while paused applies at the paused boundary (D2a).
- **Determinism (the main oracle):** a scripted session through the `Runtime` (mixed rates, pauses, one rewind) ends with the same `checkpoint()`
  as a plain loop of `submit` and `step` with the same commands at the same steps.
- **History:** a rebuilt checkpoint deep-equals the original. Rewind then run gives the same state as an uninterrupted run. Thinning keeps the first and latest checkpoints.
- **Session:** export, then import, gives the same checkpoint. A wrong library digest gives a clear error.
- **Stream:** events arrive in order and complete when snapshots are coalesced. The shape is sent only when the rule in §7 says so.
- **Library errors:** a malformed library gives `loadFailed` with the validator's codes.
- **Client:** `client.test.ts` joins a `RuntimeClient` to a `Runtime` in memory (messages cloned and delivered asynchronously): load, command promises, automatic `frameAck`,
  error routing (an error for one request never answers another), session round trip, and worker loss.
- **Targeted breaks (2026-09-27):** five deliberate faults, each caught by at least one test: replay re-submitting commands already in a checkpoint (3 tests fail),
  the clock running one step ahead (4), a rebuilt checkpoint log with one extra command (4), snapshots ignoring `frameAck` (1), and no structural command check (1).
- **Real Worker:** `worker.ts` does not run under Vitest. A manual smoke run in Chromium (Playwright 1.56, Vite dev server) loaded the synthetic core over `fetch`,
  ran 1.5 s of wall time at 10× (15.08 s of sim time, 44 snapshots), and did a command, a session export, a rewind and a failed load (`E_JSON`).
  The automated browser test (TODO Next #8) now exists: `web/src/app/e2e/`, run in CI as the `e2e` job.

## Decisions (approved by the user, 2026-09-27)

| # | Question | Choice |
|---|---|---|
| D1 | Time rates above about 150× | **T2**: `outerDt` as a fixed per-session setting now; T3 (engine change) only if needed later |
| D2 | Commands while paused | **(a)** queue them; they apply when time moves |
| D3 | Commands after a rewind point | **(a)** truncate, keeping the old timeline as an exportable session |
| D4 | Role check for instructor-only commands | **(a)** no check in C6; the views decide |
