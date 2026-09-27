# M4: the live explorer

Status: **first slice done, 2026-09-27** (cloud session, branch `claude/m4-live`). TODO M4: "Link them. Move rods, power responds, the 3D view updates live."

## Data flow

```
 controls (app/controls.ts) ── commands ──▶ RuntimeClient ──▶ worker: Runtime ▶ Engine
                                                                   │
 explorer ◀── rod positions, live element power ◀── snapshots (30 Hz, shape only when it changed)
 controls ◀── read-out (truth), clock, acknowledgements
```

- **Commands only.** Every control sends a command through the runtime's command bus (`rod.move`, `rod.fire`, `scram`, `trip.reset`, `mode.set`) or a clock request (run, pause, rate).
  A rejection shows with the engine's or the runtime's reason, for example `REJ_TRIPPED`.
- **Rods:** each snapshot's `truth.rods` positions move the rod instances (`live.ts` `rodPositionsFrom`). The explorer's rod sliders become read-outs in live mode.
- **Live power overlay:** when a snapshot carries the shape ([E, A], element-major), each element's power is its axial sum × total power (`elementPowers`).
  The colours scale to the hottest element (viridis), so the pattern shows at any power level. The read-out gives the absolute power.
- **Truth, not indicated.** The explorer and this control strip show `truth` (ARCHITECTURE allows it for the explorer). The operator panel (M5) will show only `indicated`.

## Checks

- Vitest: `web/src/views/explorer/live.test.ts` (element powers from the engine's live shape add up to the total power; colours; display formats).
- Playwright (`web/src/app/e2e/app.spec.ts`, real clicks on the production build):
  - withdrawing a rod moves it in the 3D view, raises the power, and colours the fuel by live power;
  - SCRAM trips the reactor and drops a withdrawn rod, and a later withdrawal is rejected with `REJ_TRIPPED`;
  - pause stops sim time, and the clock shows the achieved rate while it runs.
- A deliberate break (the app ignores snapshot rod positions) fails both rod tests. The first version of the SCRAM test could not catch it:
  the synthetic core starts with every rod in, so "the rods fall" was already true. The test now withdraws a rod first.

## Known limits

- The main thread loads the library for the geometry, and the worker loads it again to run it (two reads of the same files; small for these libraries).
- Cut faces keep the material colour (see the M3 decision), so the live overlay shows on the element surfaces, not on the cut.
- The overlay is per element, not per axial bin; the per-bin data texture is still TODO M3.
- No rod target positions: the engine has `rod.move` in/out/stop only (ARCHITECTURE lists `rod.setTarget`, which the engine does not implement).
- One runtime per page. Switching library terminates the worker and starts a new one.
