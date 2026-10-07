# M8 step 2: the format fit check for a BEAVRS PWR library (2026-10-07)

Plan: `m8-second-reactor-plan.md`, step 2. For each quantity a BEAVRS hot-zero-power library must carry, this says whether the library format v0.1 and the engine (0.3.0) can hold it, and if not, which of the plan's three answers applies: **fits**, **fold in** (an existing field carries it and the notes say how), **refuse** (leave it out and show a validity warning) or **extend** (a named change). Checked against `docs/library-format.md`, `schema/library.schema.json`, `physics_ref/engine.py` (the state vector, `reactivity`, `rhs`, `_apply`) and the BEAVRS results of step 1. Nothing was built.

## The table

| # | Quantity | Where it goes | Verdict | Reason |
|---|---|---|---|---|
| 1 | Nine control banks (A, B, C, D, SA to SE), 228 steps | `reactivity.rods[]` (id, `travelCm`, `speed`, `worth` table, `scram`) | **fits** | Rods are ids with their own tables. The 228 steps are 360.68 cm of travel (step height 1.58193 cm, specification rev 3.0.2); speed is fraction per second (the benchmark gives no drive speed; to be assumed and labelled). |
| 2 | Bank worth interaction (the worth of a bank depends on the banks already in) | `domain.jointChecked`, `R_JOINT_UNCHECKED` | **fits, with a warning** | The format adds rod worths as if independent and says so. Step 1's sequence (eight states) gives joint checks for the insertion order D, C, B, A, SE, SD, SC; any other combination is flagged. |
| 3 | Fuel temperature (Doppler) | `reactivity.fuelTemp`, `thermal.fuel` | **fits** | One table over fuel temperature. At HZP the fuel is at the coolant temperature. |
| 4 | Moderator temperature and density | `reactivity.coolantTemp`, `thermal.coolant` | **fits, validity note** | One table. Step 1 found the transport model's isothermal coefficient 1.6 to 2.0 pcm/°F too negative, so the library is marked *temperature feedback not validated at HZP* (protocol decision 4). |
| 5 | Coupling of the moderator coefficient to the boron concentration (it becomes less negative as boron rises) | none | **fold in** | The coolant table is built at one boron (975 ppm) and the notes say so. The reactivity is a sum of separable terms; there is no cross-term. A warning when the boron differs from the table's by more than a stated amount. A 2D table is an extension to consider only if a lesson needs the dilution transient with temperature change (it does not). |
| 6 | **Soluble boron**: concentration state, reactivity, a command, a rate | none | **extend** | See the next section. This is the one forced change. |
| 7 | Boron worth (12.6 pcm/ppm at 975 ppm, 12.8 at 508) | the new `reactivity.boron` table | extend (part of 6) | Step 1's K series gave the two slopes; the table needs about six points (step 3). |
| 8 | Delayed neutrons: six groups, β_eff, Λ | `kinetics` | **fits** | Needs one IFP case (the TRIGA pipeline has `--kinetics`); not yet run for BEAVRS. |
| 9 | Source for shutdown multiplication | `kinetics.extSource` | **fits** | A scalar. |
| 10 | Xenon and iodine | `poisons`, `reactivity.xenon`, reference `xenon` | **fold in** | The schema requires `poisons` and the xenon table. HZP is xenon-free: the reference xenon is 0, the table is flat or short, the `poisons` values are assumed and labelled so, and the lesson's envelope caps power and time so xenon does not matter. A long-run PWR lesson would need real values (a later milestone). |
| 11 | Decay heat after a trip | none | **refuse** | The format has no decay-heat inventory (stated in section 8). The HZP lesson does not need it; any trip lesson at power would. The library carries the validity reason *no decay heat* and the supported envelope is zero power physics. |
| 12 | Primary heat removal, steam generators, RCPs | `thermal.heatExchanger` (one UA, one sink temperature, one pump), `plant.pumps` | **fold in** | One lumped heat exchanger and one pump id (the four RCPs as one). Adequate for isothermal HZP; no loop, no flow dynamics (refused, out of scope for M8). |
| 13 | Pressure, pressurizer, boiling, void | none | **refuse** | Not in the format. At HZP (566 K, 15.5 MPa) there is no boiling; the library states it. |
| 14 | Power channels: source range, intermediate, power range | `plant.instruments` (linear and log scales, range, lag, noise) | **fits** | Instruments read a truth signal; counts per second are a scaled power. |
| 15 | Trips (high flux, high startup rate, others) and interlocks | `plant.trips`, `plant.interlocks` | **fits** | Trips read `truth.power` / `truth.period` / indicated channels. Setpoints would be *assumed* and labelled so (the provenance note added for the TRIGA libraries on 2026-10-07 applies). |
| 16 | Operating modes | `plant.modes` | **fits** | One mode, `steady`. The TRIGA pulse mode is optional per library. |
| 17 | Fission power shapes by assembly and axial bin | `shapes` (193 elements, A axial bins; rod deltas per bank; fuel-temperature delta) | **fits, cost** | `base + Σ rodDelta + tempDelta(T_f)` has no boron term and no moderator term; shapes at HZP vary little with boron, and the notes say so. Size is small (nine banks × grid × 193 × A bins of float32, well under 1 MB). Cost is a mesh tally in each rod case. |
| 18 | Render geometry: vessel, 193 assemblies, banks moving with the rods | `geometry.primitives` with `element` and `rod` | **fits** | Cylinders, annuli and boxes; each RCCA primitive carries its bank's rod id. A few hundred primitives; the viewer has not been tested at that size. |
| 19 | Domain (where the tables have data) | `domain` | **fits, extended** | Needs the boron range to be added to `domain` (part of 6). |
| 20 | Reference state | `reference` (rods, Tfuel, Tcoolant, xenon, rho, calibration) | **fits, extended** | Needs `reference.boron` (part of 6). Step 1 found no calibration offset (+70 pcm mean, within 1σ), so `calibration` is null. |

## The one extension: soluble boron

**Design.** Make boron behave like a rod. It is not an ODE state: the engine already keeps a `motions` record for each rod and evaluates `rod_position(id, t)` analytically from the last command (a linear ramp at the rod's speed). Boron would be one more such actuator, `boron(t)`, ramping from its current value toward a commanded value at a rate limit from the library (dilution and boration are slow). Reactivity gains one term, `lib.boron(boron(t))`, in `reactivity()` and `rhs()` beside `fuel_temp` and `xenon`. No new entry in the state vector (`IP … IEH`), so checkpoints keep their shape and only `motions` carries the new actuator.

**Format (capability `point-kinetics/boron-v1`, so older libraries are unaffected, as `lumped-thermal-v2` was for the hA law):**

- `reference.boron` (ppm) and `domain.boron` `[lo, hi]`;
- `reactivity.boron`: a table with axis `C` (ppm), zero at the reference like every table;
- `plant.boron`: `{ maxRatePpmPerS, range }`, and `truth.boron` as a new truth signal, so trips, instruments and scenario goals can read it.

**Command.** `boron.set { ppm }`, rate-limited, rejected outside the range; a fault command is not needed.

**What it touches** (the list for step 4's estimate): both engines (`physics_ref/engine.py`, `web/src/sim/engine.ts`) and `library.py` / `library.ts`; both validators and `schema/library.schema.json`; the signal list; `validateCommand` and the scenario `controls.allow` names; the operator panel (one control, one reading) and the instructor panel (one line); the session file and CSV trace (the command is in the log and replays on its own); golden vectors (a planted boron-step case with Python and TypeScript agreeing to 1e-9, as for the hA law); the supported-envelope text. TRIGA libraries and their vectors must pass unchanged (the step 4 gate). Rough effort: one working day for a careful build and the Codex review.

**Why not fold it in.** Boron is the operator's lever in the PWR lesson, and the format has nowhere for an operator-set quantity except a rod. Calling it a rod would put a 0 to 2000 ppm "position" into `reactivity.rods` with a travel in cm: it would validate and render as a moving control rod. That is a lie in the library; the extension is smaller than the confusion.

## What step 3 (the sweep) will cost

Cases beyond the 20 already run: nine banks × about six positions for the rod curves and shapes (54), fuel-only temperature (about 5), moderator temperature and density (about 5), boron at the reference rods (about 4 more points; the K series gives two), kinetics by IFP (2), joint checks (about 6). Roughly 75 to 80 cases. At the standard 12 million active histories a case took 6 to 9 minutes of wall time at the load seen during step 1 (9 to 27); about 10 to 12 hours. The W, B and K series already give the joint-check states and the two boron slopes.

## Decisions needed

1. **Extend for boron (step 4) as designed above, or stop?** Recommended: go, with the actuator design, behind the gate (TRIGA libraries and vectors unchanged).
2. **Refuse decay heat and pressure for M8** (zero power physics only), as in items 11 and 13. Recommended: yes.
3. **Fold in** the boron–moderator coupling (item 5) with a warning, not a 2D table. Recommended: yes.
4. **Step 3 scope:** approve about 80 further OpenMC cases and 10 to 12 hours of wall time, or cut the rod grid to four positions per bank (about 45 cases)?

## Not checked

The number of RCCA assemblies per bank (item 18) and the rod drive speed (item 1) are not read yet and need a look before step 3. The viewer's handling of several hundred primitives is untested. `physics_ref/library.py` and `library.ts` were not read in full for where a new table and a new truth signal would plug in; the estimate assumes it follows the pattern of the xenon table and the hA law.
