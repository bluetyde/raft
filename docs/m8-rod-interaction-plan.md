# M8 follow-up: combined rod worth and the bank-withdrawal lesson: plan (2026-10-10)

The user wants a lesson with banks moving (a bank-withdrawal startup) on the BEAVRS PWR library. The library cannot support it today: it adds single-bank worths, and the twelfth protocol measured the cost (`docs/validation/m8-beavrs-library-results.md`: critical boron +50, +92 and +157 ppm too high with C and D, A to D and seven banks in; the real combined worth is 1.27 to 1.48 times the sum). This plan fixes that with one new table, checks the fix on cases the table was not fitted to, and then builds the lesson. Status: plan only; nothing built.

## 1. The change: a correction table on the summed rod reactivity

Capability `point-kinetics/rod-interaction-v1` (the same pattern as `boron-v1`: a capability string, required fields, both engines, both validators, a fixture set and a golden vector; libraries without it are untouched).

- **Library field:** `reactivity.rodInteraction = { S: [...], rho: [...], unc?: [...], interp, outOfRange, source }`. The axis S is the **sum of the single-rod reactivities** Σ wᵢ(xᵢ) (each rod's table value at its position, relative to the reference, the number the engine already computes); the value is a correction **added** to the rod sum. The table must be zero at S = 0 (every rod at its reference position; `E_REF_NONZERO` as for the other tables), the axis strictly increasing.
- **Engine:** `rho_total = reference + calibration + Σ wᵢ(xᵢ) + rodInteraction(Σ wᵢ(xᵢ)) + fuel + coolant + xenon (+ boron)`; the breakdown in the snapshot gains one field `rodInteraction`. Python reference engine first, then TypeScript, then a golden vector.
- **Gate (as for boron):** the TRIGA libraries and every existing golden vector pass unchanged (only the engine-version pin may move, 0.5.0); both engines agree on the new vector; the SEED oracle entries still reproduce.
- **Not in this change:** a rod dependence of the temperature tables (the temperature coefficient at C and D in stays wrong, protocol 12; the lesson runs at constant temperature, so it does not need it); the separable power shape (it stays a sum; see risk 3).

## 2. The fit, and what it is fitted to

**To the transport cases only, never to the measurements**, so that the comparison with the measurements stays a test (the fourteenth protocol of section 4). The points, from the sweep and the exporter's self-check (`pipeline/openmc/results/beavrs_export_report.json`), in pcm relative to the reference:

| State | S (sum of single-bank worths) | Correction = transport minus summed | Source |
|---|---|---|---|
| all at reference | 0 | 0 | by definition |
| one bank, the deepest single worth | −827 (bank B) | 0 | one bank has nothing to interact with |
| C and D in (S2) | −1576 | −420 | case J-W2 |
| A to D in (S4) | −2632 | −1107 | case J-W4 |
| seven banks in (S7) | −4075 | −1953 | case J-W7 |
| above the reference | +100 | 0 | assumed (bank D from its bite position to out is +61 pcm) |

The fit is the weighted isotonic regression of the exporter (`isotonic`), the points weighted by the statistical errors of their cases; the correction is monotone in S. Between the points the table interpolates linearly; beyond −4075 it clamps and flags (`clamp-and-flag`), which is where the two banks that are not in the benchmark sequence (SA, SB) would go.

**The assumption** (and the thing to test): the correction depends only on S, the total rod strength, not on which banks make it up. Along the benchmark insertion order (D, C, B, A, SE, SD, SC) that holds by construction at the three combined points; elsewhere it is a claim. The library says so in its notes and the lesson stays on the benchmark order.

## 3. New transport cases, held out from the fit

To test the assumption between the fitted points, nine new OpenMC cases along the benchmark path, run once, at 975 ppm and 566.483 K, the same settings as the sweep (60 000 × 300, inactive 100; about 8 to 10 minutes each on a quiet machine, so 1.5 hours; **needs the user's go and an idle machine, best overnight**):

- the cumulative states S3 (D, C, B in), S5 (D, C, B, A, SE in) and S6 (D, C, B, A, SE, SD in);
- one bank part-way with the earlier banks of the order fully in, for C, B, A, SE, SD and SC: that bank at 76 steps withdrawn (x = 1/3, two thirds inserted), the earlier banks at 0 steps, the later ones at their reference positions.

They are added to `pipeline/openmc/beavrs_cases.py` as a second family (`P-S3`, `P-S5`, `P-S6`, `P-<bank>-76`), kept apart from the fit. The exporter reads them as held-out checks and reports, for each, the library's error with and without the table; they enter `domain.jointChecked` only where the error is within 100 pcm (the limit of the exporter and of protocol 12).

## 4. The protocol (written before any new run or code, the fourteenth)

`docs/validation/m8-rod-interaction-protocol.md`, two parts, each run once:

- **P: the held-out path cases.** The library's error at each of the nine cases against the transport result, with the statistical error; labelled good if within 100 pcm or 3σ, plausible within 200 pcm, fails above. **Predictions (written in the protocol before the run):** S3, S5 and S6 within 200 pcm; the part-way cases within 300 pcm; the largest error at the part-way cases of the last banks, where one bank moves while six others are in and the table is steepest.
- **M: the library against the measurements again**, the same metrics, bands and decision rules as the twelfth protocol (critical boron at five states, seven sequential worths and the total, the two temperature coefficients, the six differences from transport). **Predictions:** the critical boron errors fall to the transport model's own (+8, +22, about +16, about +6 and about +8 ppm at S0, S1, S2, S4 and S7: the boron×bank interaction of 100 and 290 pcm at S4 and S7 stays), the total of the seven worths comes within 1 % of the measured 6042 pcm, the worth of C is within 5 %, other sequential worths between plausible and fails (the interpolation at S3, S5 and S6 decides), and the temperature coefficient still fails at both states.

## 5. The lesson (draft; the final shape waits for the results of P and M)

**Bank-withdrawal startup at hot zero power.** The shutdown banks and the control banks are in (state S7: banks D, C, B, A, SE, SD and SC at 0 steps), boron fixed near the concentration at which the **fewest** banks would be critical in the library (to be set from the results: about 860 ppm, the library's critical value with C and D in), the source in the core. The operator withdraws the banks in reverse benchmark order (SC, SD, SE, A, B) and brings the reactor critical with C and D still in; goals on the log channel as in the dilution lesson, with a hold and a startup-rate trip; controls `rod.move` and `scram` only (boron fixed: the dilution lesson is the boron one). The rods move at the library's assumed speed (72 steps a minute, 190 s for a full bank), so the lesson is about 15 to 20 minutes at 1×. Envelope: every state on the benchmark insertion path (the other rod combinations are not supported and the banner says so), boron as set, power as in the dilution lesson.

The lesson claims only what P and M show: the critical state with C and D in, and the approach to it along the path; no claim about other bank orders or about temperature feedback. Tests: scripted operators (careful, too fast, wrong order, idle) with their outcomes written before they run, as for the dilution lesson.

## 6. Work, in order

1. **This plan**, then the protocol (section 4), committed before any code.
2. **Format:** `docs/library-format.md` section 16, schema (`tableS`), both validators, fixtures (valid with the capability; invalid: capability missing, field missing, not zero at S = 0, axis not increasing), tests. About half a day.
3. **Engines:** Python, TypeScript, one golden vector with a planted answer, the gate of section 1; Codex review of the capability (as boron). About half a day.
4. **Exporter:** the fit of section 2, a planted-model test (a nonseparable planted sweep along a path: the exporter must recover the planted table), deliberate breaks, the library rebuilt (`pwr-beavrs-hzp-openmc` gains the capability; its digest changes, which is fine: the twelfth protocol is fixed to the old digest). A quarter of a day.
5. **The nine cases** (needs the go, idle machine), the exporter's held-out report, and the analysis script of the protocol (P and M; the twelfth script is reused for M). Then the results note.
6. **The lesson** (section 5), its tests, a browser check, notes, a Codex review of the whole.

About two working days, of which about two hours are machine time.

## 7. Risks

1. **S alone may not carry the interaction.** A bank worth depends on where the other banks are, not only on how much they are worth in total. P is the test. If P fails badly, the next step is pair terms (a bank's correction as a function of the other banks' reactivity), which costs more cases; the lesson would wait.
2. **The boron × bank interaction** (about 100 pcm at S4, 290 at S7) stays; it is small against the correction but it moves the lesson's critical concentration by up to 23 ppm. The notes say so; a boron-dependent table is not in this change.
3. **The power shape** with several banks in goes negative in some bins (6 bins at S4, 19 at S7, summed shapes). The engine's shape output must floor and renormalise those bins, or the lesson's 3D view will show negative power; check how the explorer handles them before the lesson, and fix in the engine if needed (it changes no vector unless a bin is negative).
4. **Validity.** `domain.jointChecked` will list only the states that P confirms; between them the banner says "not checked against transport", which is true. The library stays `experimental`.
5. **The sum-of-worths axis at the far end:** beyond S = −4075 (SA, SB in) the correction is clamped and flagged; the lesson never goes there.

## 8. Decisions I need from you

1. **The change:** the correction table on the summed worth (recommended: one table, no new cases to fit), or pair terms now (more general, about 40 new cases, much longer).
2. **The nine held-out cases:** run them (recommended, about 1.5 hours overnight; without them the table is validated at its three fitted points only and the lesson would stand on an untested interpolation), or skip them.
3. **The lesson:** the bank-withdrawal startup of section 5 (shutdown banks out, control banks C and D in, boron fixed), or a different one (say what you want to teach).
