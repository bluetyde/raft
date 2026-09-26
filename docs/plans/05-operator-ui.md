# Plan 05: Operator view, instruments and scenarios

The control-room view. You run the reactor using only what real instruments would tell you.
Milestone: M5.

## Principle: the operator sees instruments, not truth

The operator view reads only `snapshot.indicated` and `snapshot.alarms`, never `snapshot.truth`.
The **instrument layer** between them is part of the simulation, not the UI.

For each instrument (all specs come from the library's `plant.instruments`):
- A **signal** from the truth state (power, fuel temperature, rod position, pool temperature).
- A **range** and **scale** (linear, log, percent). Readings beyond the range peg the meter.
- A **time lag** (first order). A log power channel shouldn't show a pulse's millisecond peak the way the truth does.
- **Noise**, seeded, for determinism.
- **Failure modes:** stuck, drift, dead (null), set only through faults from the instructor.
- Derived signals, e.g. a **period meter** computed from the indicated power, not the true period.

Checks, interlocks and trips use the same **typed predicate format** (validated signal names, a fixed operator list: `gt`, `lt`, `absGt`, `between`, `all`, `any`, `not`).
Free-text expressions aren't allowed, and unknown operators or signals fail validation.

## Panel layout (generic, driven by the library)

The panel is built from the library's instrument and rod lists. Nothing is laid out specifically for TRIGA in code.

- **Power channels:** linear power (with range switching), log/wide-range power, percent power.
- **Period meter.**
- **Temperatures:** fuel (instrumented element), pool.
- **Rod column** for each rod: position readout, UP/DOWN buttons, up-limit / down-limit / rod-down lights.
  A pulse-capable rod gets a FIRE button that's enabled only in pulse mode and when the interlocks allow it.
- **Mode switch:** from the library's `plant.modes`. For TRIGA that's steady, pulse and square wave.
- **Annunciator panel:** alarm tiles that flash until acknowledged.
- **SCRAM** button (with a cover, so it isn't clicked by accident).
- **Strip charts:** power (log), period and fuel temperature over the last N minutes.

Style: flat and readable, not a skeuomorphic replica of a real console.
We don't copy any specific facility's panel, and a clean design is easier to learn.

## Scenarios

JSON files in `web/public/scenarios/`, validated against `schema/scenario.schema.json`:

```jsonc
{
  "id": "triga-first-startup",
  "library": "triga-jsi",
  "title": "Approach to critical",
  "brief": "Withdraw rods to reach criticality from shutdown using a 1/M plot.",
  "initialState": { "power": "source", "rods": { "*": 0 }, "Tfuel": "ambient" },
  "controls": { "allow": ["rod.move", "scram", "mode.set"] },
  "events": [ { "at": 600, "fault": { "type": "instrument.drift", "instrument": "linear", "rate": ... } } ],
  "goals":  [ { "id": "critical", "check": { "all": [ { "signal": "indicated.period", "op": "absGt", "value": 300 },
                                                  { "signal": "indicated.linear", "op": "gt", "value": ... } ] }, "within": 1800 } ],
  "hints": [ "..." ]
}
```

Starting set for the TRIGA (each also a teaching unit):

| Scenario | Teaches |
|---|---|
| Approach to critical | Subcritical multiplication, 1/M plot, why you withdraw in steps |
| Power ascension | Period, feedback, the prompt jump |
| Steady-state hold | Feedback against rod adjustments; the pool slowly heating |
| Pulse | Prompt critical, Nordheim–Fuchs behavior, why the fuel's feedback makes TRIGA pulsing safe |
| Square wave | Pulse, then hold, using the TRIGA square-wave mode |
| Scram and restart | Rod-drop reactivity, negative period, precursor decay tail |
| Xenon after shutdown | Build-up, the peak, and why restart can be limited (small at TRIGA power; shown honestly) |

The **1/M plot** is built into the view as an optional helper during the approach-to-critical scenario.

**Scoring** is gentle: goals met, trips caused and time taken. This is a teaching tool, not a competitive game.

## Layout modes (from PLAN.md)

- **Split (default):** operator panel plus a live 3D inset. A key swaps which one is large.
- **Realism:** hides the 3D inset during a scenario. Instruments only.
- **Full explorer:** 3D only, with the HUD.

## Disclaimer

Shown on first launch and in the About box:
this is an educational model built from published data. It isn't an operator training tool for any real facility, and it isn't for safety analysis.

## Open questions

- Which instruments do published JSI sources describe? The panel should list only channels that we can source, plus clearly labelled generic ones.
- Should the pulse-mode interlock rules come from JSI documents or from the generic TRIGA license limits in the literature?
