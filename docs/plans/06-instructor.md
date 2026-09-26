# Plan 06: Instructor view

Controls for running a session: time, history and faults. Built for a lecture or lab where one person runs the scenario and others operate or watch.
Milestone: M6.

## Features

- **Time control:** pause, 1×, and speed-ups (10×, 60×, 600×, 3600×) for xenon and heat-up scenarios.
  The sim caps speed when the worker can't keep up (e.g. during a pulse), and the UI shows the actual rate.
- **Rewind and branch:** scrub back on a timeline, then continue from there with different actions.
  The old branch is kept, so you can compare "what if I had scrammed here".
- **Fault injection:** from a list the library supports, with parameters:
  - stuck rod (won't move / won't scram)
  - rod drops unexpectedly
  - instrument stuck, drift or dead
  - pump trip / loss of heat removal
  - reactivity insertion (generic, for "what if")
- **Truth panel:** the full `snapshot.truth` next to what the operator sees, including the reactivity broken down by source.
- **Annotations:** drop a marker on the timeline with a note. It shows up in exports.
- **Export:** session file and CSV of traces. The session file **pins** the library content digest, engine build, solver configuration, scenario digest,
  initial-state definition, seed, command log and annotations. Anyone with the same pinned engine can replay it exactly;
  a different engine version replays within tolerance and says so.

## How rewind works

```
 checkpoints:  ●───────●───────●───────●        (full state every N s of sim time)
 command log:  ─c──c────────c──────c─c──        (all commands, time-stamped)

 rewind to t:  restore last checkpoint ≤ t, replay commands up to t
 branch:       truncate command log at t on a new branch; keep the old one
```

**A checkpoint contains:** power and precursors, iodine and xenon, fuel and coolant temperatures, rod positions and motion, controller and trip latches,
instrument filter states, the random-generator state, scenario progress and event cursor, and solver history if the method needs it
(or checkpoints sit only at canonical solver restart boundaries; see [01](01-physics-core.md)).
**A branch** records its parent branch and fork time.

**Limits:** retained checkpoints and old branches have a memory budget, measured on a named test machine. At the limit, the oldest checkpoints are thinned
(the command log is always kept, so replay from the start stays possible), and the UI says so. Exported sessions always include the full command log.

This depends on the **determinism** guarantee in [01](01-physics-core.md).
One test replays a long random session twice and requires identical results.

## Multi-window and classroom use

- **v1, same machine:** operator and instructor in separate browser windows, linked by `BroadcastChannel`.
  One worker owns the sim, and the other window mirrors its snapshots and sends commands.
  If the owner window closes, the mirror detects it, disables its controls and says it's disconnected. Automatic takeover can wait.
  With a projector plus a laptop, that's enough for NE403.
- **Later, networked:** a small WebSocket relay so students on their own laptops watch or operate a shared session.
  Out of scope until v1 works.

## Access control

In v1, "instructor mode" is just a toggle. There's nothing to protect.
If networked sessions arrive, instructor actions need a session key, so a watching student can't inject faults.

## Open questions

- Should faults be visible to the operator as "something is wrong", or completely hidden? Make it a per-scenario setting.
- Should the timeline also show alarms and trips as markers? Probably yes, since it's cheap and useful for debriefs.
