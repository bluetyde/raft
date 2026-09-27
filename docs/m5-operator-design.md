# M5: operator panel (design)

Status: **approved by the user on 2026-09-27: D1–D6 as recommended (all option a), with three amendments (section 7).** Implemented on the same branch: `web/src/views/operator/`, the layouts in `web/src/app/main.ts`, and per-step instrument extremes in the runtime.
Scope: the operator view of [plan 05](plans/05-operator-ui.md) (TODO M5 "Instrument panel", "once the snapshot-to-panel mapping is designed") and the split layout.
Out of scope: scenarios, because the scenario format (A7) is on hold by the user's decision; the instructor view (M6).

The operator view is built on the C6 runtime (`web/src/runtime/`) and the M4 app (`web/src/app/`). It sends commands through the same command bus, with `clientId: "operator"`.
The decisions are marked **D1–D6**, each with options and a recommendation. The table at the end lists them.

## 1. What the engine and library give today

Plan 05 and ARCHITECTURE §3 assume some things that do not exist yet:

| Plan 05 / ARCHITECTURE | What exists | Consequence |
|---|---|---|
| `snapshot.alarms: Alarm[]` | Not in the engine or `schema/snapshot.schema.json`. The snapshot has `trips: { latched, active }` and `tripped`. | The annunciator must come from somewhere else (D1). |
| A period meter computed from the indicated power | No derived instruments. `indicated` holds only the library's instruments. The `period-short` trip watches `truth.period`. | D3. |
| Rod position indicators, limit lights | Rod positions exist only in `truth.rods`. | D2. |
| Percent power | The library has no rated power. | D4. |
| Instrument labels, units and roles (power channel, temperature) | An instrument has `id`, `signal`, `scale`, `range`, `lag`, `noise`. | The role comes from `signal` (`truth.power` → power channel, `truth.fuelTemp` → fuel temperature, `truth.coolantTemp` → pool temperature). The label is the `id`. The unit follows from the signal. |

What the two shipped libraries define (both have the same structure):
- **Instruments:** `linear` (linear power, 0–300 kW), `log` (log power, 1e-4 W to 1e9 or 3e9 W), one or two fuel thermocouples, and `pool-temp`.
- **Trips:** `power-high` (on `indicated.linear`), `fuel-temp-high` (on a fuel thermocouple), and `period-short` (on `truth.period`). All three latch.
- **Interlocks:** `fire-needs-pulse-mode` and `pulse-mode-low-power`.
- **Modes:** `steady` and `pulse`.

## 2. The rule, made precise

The operator view never reads the physics state from `truth`. It reads:
- **`indicated`:** every meter and chart. A `null` reading means a dead instrument.
- **Console state:** the state of the controls themselves, which a real console shows from its own switches and relays.
  These are `truth.rods[*].position` and `.moving` (only if D2 = a), `truth.mode`, `truth.pumps`, `trips`, `tripped`, `validity`, and the time `t`.
  The panel code gets these through one function, `consoleState(snapshot)`. A test checks that no other `truth` field reaches the view.
- **Never:** `truth.power`, `truth.period`, the temperatures, reactivity, precursors, xenon, iodine, energy, peak values, or the shape.

## 3. Panel parts

All parts are built from the library's lists. There is no reactor-specific layout in the code.

| Part | Built from | Shows |
|---|---|---|
| **Power channels** | instruments with `signal: truth.power` | For each: a bar meter on its own scale (`linear` or `log` decades) and range, the digital reading with an SI prefix, and "OVER" or "UNDER" when the reading is outside the range (the meter pegs). |
| **Period meter** | derived from a log power channel (D3) | Period in s, with "∞" when steady, and a bar on a signed log scale. |
| **Temperatures** | instruments with `signal: truth.fuelTemp` or `truth.coolantTemp` | A bar meter and a reading in °C (converted in one place, as ARCHITECTURE's conventions say). |
| **Rod column** | the library's rods (`reactivity.rods`) | Position (D2), moving arrow, IN / STOP / OUT, a "rod down" light at 0 and an "up limit" light at 1. FIRE for a pulse-capable rod, shown enabled only in pulse mode (the engine's interlock still decides). |
| **Mode switch** | `plant.modes` | `mode.set`. A rejection shows the interlock's `reason`. |
| **Annunciator** | D1 | Tiles that flash until acknowledged. |
| **SCRAM** | — | A two-step control: first "lift cover", then "SCRAM". Esc or a timeout closes the cover. |
| **Strip charts** | the power channels, the period meter and the fuel temperature | The last 10 minutes of sim time. |
| **Clock** | the runtime | Run, pause and rate, as in M4, with the achieved rate. In the operator view these are marked "instructor", because plan 06 puts time control there. |

## 4. Layout

- **Split (default):** the operator panel on the left, and the M4 explorer as a smaller live 3D inset on the right. A key (`Tab`) swaps which one is large.
  As built, the inset is 3D only: the explorer's own panel and the M4 truth read-out are hidden, so nothing on screen in split shows truth values.
- **Realism:** hides the 3D inset and the M4 truth read-out. Only instruments show.
- **Explorer:** the M4 view (3D with the truth read-out and controls).

A toggle in the header chooses the mode. The choice is kept in `localStorage` as a convenience only.

## 5. Chart and alarm limits (TD-08)

- **Charts:** one ring buffer per charted channel, 3,000 points, stored as (sim time, reading).
  A new point is kept only if at least 10 minutes / 3,000 = 0.2 s of sim time has passed since the last one. So at high time rates the buffer thins and stays bounded.
  A null reading is stored as a gap. A rewind clears the charts after the rewind point.
- **Annunciator:** one tile per source. The tile count is fixed by the library, so it is bounded.

## 6. Tests

- **Vitest (pure functions):**
  - the mapping from library instruments to meters;
  - log and linear scales and pegging;
  - the °C conversion;
  - the derived period from a synthetic exponential series (a known period within 1 %);
  - the ring buffer thinning and bound;
  - the annunciator state machine (lit, flashing, acknowledged, cleared);
  - `consoleState` returning only the whitelisted fields.
- **Playwright** (like `app.spec.ts`):
  - withdraw a rod in the operator view: the log meter and the period meter respond;
  - SCRAM with the cover: the trip tile flashes, acknowledging stops the flashing, the rod-down lights come on, and a withdrawal is rejected with `REJ_TRIPPED`;
  - realism mode hides the 3D inset and the truth read-out.
- **Truth guard:** the operator view is built with a snapshot whose `truth` physics fields are removed. It must still render every meter.

## 7. Amendments from the user (2026-09-27)

1. **Charts keep the extremes.** The thinning keeps the minimum and the maximum of each 0.2 s bucket, not a single sample, so pulse peaks survive.
   A test checks that a 10 ms spike survives at full height.
   Because snapshots come at about 30 Hz, a 10 ms spike could fall between two snapshots before the chart sees it.
   So the runtime also sends, with each snapshot, each instrument's minimum and maximum over every engine step since the last snapshot (`extremes`).
   The chart stores those as points. This is a runtime change only; it reads `engine.indicated` after each step.
2. **The derived period is careful about its input.** It skips null readings, pegged readings (outside the instrument's range) and points from before a rewind.
   It shows "—" when too few points remain in the window, and in pulse mode. A test runs it with the library's lag and noise on.
   Consequences found while building it:
   - The meter reads only up to about 7× real time. Snapshots come at about 30 Hz of wall time, so at 10× they are 0.33 s of sim time apart,
     and a 2 s window then holds fewer than the 8 readings it needs. Above that rate it shows "—".
   - With the libraries' log-channel noise (1–2 % per reading), a 2 s window measures periods from a few seconds to tens of seconds.
     A slope smaller than three times its standard error reads as steady (∞), so noise never shows a short, alarming period (tested).
     A first version used two times; a screenshot showed it reading −103 s on noise while the true period was thousands of seconds.
3. **ARCHITECTURE.md is not edited here.** The local session will change §3 to say that alarms are derived in the view.

Notes:
- **Interlock-rejection tiles are not in replays.** They come from the acknowledgements of this view's own commands, which a session file does not record.
  A replay or a rewind shows the trip, instrument and over-range tiles again, but not the interlock rejections from before.
- **The truth-guard test keeps the `consoleState` fields.** It removes only the physics fields of `truth`
  (power, period, temperatures, reactivity, precursors, iodine, xenon, energy, heat removed, peak values, shape). Rods, mode and pumps stay, because the panel may read them.

## Decisions (approved 2026-09-27)

| # | Question | Options | Recommendation (chosen) |
|---|---|---|---|
| D1 | Where do alarms come from, when the engine has none? | (a) The view derives annunciator tiles: one per library trip (lit while active, flashing when it latches until acknowledged), plus "instrument failed" (reading `null`), "over range", and "command rejected by interlock". (b) Ask the other session for engine alarms in the snapshot (engine, schema and Python change). | **(a)** now. The tiles come from data the snapshot already has. Ask for (b) only if the instructor view needs alarms in the replay record. |
| D2 | Rod positions: the plan wants position indicators, but positions are only in `truth.rods`. | (a) Treat rod position, motion, mode and pumps as console state (section 2), labelled "position indicator (ideal)". (b) Ask for rod-position instruments in the library format (a new truth signal per rod, with lag and faults). | **(a)**. Rod positions come from drive encoders on a real console, and an ideal indicator is honest if it is labelled. (b) becomes useful when M6 needs a "rod position indicator failed" fault. |
| D3 | The period meter, "computed from the indicated power". | (a) Derive it in the view from the log power channel: a least-squares slope of ln(reading) over a sliding window of 2 s of sim time. The window is a view setting, shown in the tooltip. (b) Ask for a derived `indicated.period` instrument in the engine, which trips could then watch. | **(a)** for the display. The `period-short` trip stays on `truth.period`, as the library defines it. Note in the UI that the meter is derived. |
| D4 | Percent power. | (a) Leave it out. (b) Ask for `plant.ratedPower` in the library format. | **(a)**. The linear channel in W shows the same information, and adding a rated power is a format change for no new physics. |
| D5 | Strip charts. | (a) Own small canvas charts (about 150 lines, no dependency). (b) A charting library, for example uPlot (MIT, about 50 KB). | **(a)**. Three or four line charts with a time axis do not need a dependency, and they are easy to test. |
| D6 | Default layout. | (a) Split, operator panel large. (b) Operator only. (c) Explorer, as now. | **(a)**, as plan 05 says, with realism mode one click away. |

After approval, the plan is:
1. Build `web/src/views/operator/` and the layout switch in `web/src/app/`.
2. Add the tests from section 6.
3. Keep each piece library-driven, and check it on both shipped libraries.
