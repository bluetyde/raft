# M7 core 134 feedback: the effective fuel temperature in transport: results (2026-10-07)

Protocol: `m7-core134-transport-protocol.md` (tenth protocol; not blind, see its disclosure). Runs: `pipeline/openmc/results/core134_transport.jsonl` (core 134, reference rods, default fresh fuel, 600 000 particles × 150 batches, 50 inactive, ENDF/B-VIII.0; 34, 35 and 41 minutes). The per-element temperatures are in `pipeline/openmc/results/core134_element_tfuel.json`. Script: `validation/m7_core134_transport.py`, run once (`python -m validation.m7_core134_transport`). Full output: `validation/m7_core134_transport_report.json`. Every metric is reported. Nothing was changed after seeing the results, and no library was changed.

## Result in one paragraph

**In transport the per-element fuel temperature changes the reactivity loss by a factor κ_T = 1.033 ± 0.038 over the uniform fuel temperature: label "none" (below 1.05), and compatible with the radial proxy of part C (1.080, a difference of −0.047, "agrees").** The radial distribution of the fuel temperature is at most a small effect: the result excludes 1.16 (the proxy's full value including the axial part) for the radial part, and cannot tell 1.00 from 1.08. With κ_T the what-if of the reactivity loss at step 7 is 440 pcm against 666 measured, which removes 7 % of the shortfall (the weak feedback stays "fails"). The protocol's decision (case 2): the proxy overstates the effect in transport, to the extent that the radial distribution is not an explanation; it is not an explanation of the weak feedback.

## The runs and T1, T2

| Run | Fuel temperature | k | ρ (pcm) |
|---|---|---|---|
| R294 | uniform 294 K | 1.00400 ± 0.00012 | +398 ± 12 |
| U372 | uniform 372 K | 0.99865 ± 0.00015 | −135 ± 15 |
| NU372 | 48 element temperatures, 336.9–396.5 K, volume mean 372.00 K | 0.99848 ± 0.00013 | −153 ± 13 |

- **T1:** the reactivity change from 294 K is **−533 ± 19 pcm** for the uniform fuel and **−551 ± 18 pcm** for the per-element fuel; **κ_T = 1.033 ± 0.038**, label **none** (the band edge is 1.05).
- **T2:** the radial proxy of part C is 1.080; the difference is −0.047, within 2σ: **agrees**.
- **T4:** the element temperatures (the hottest are B4 at 396.5 K, B5 at 394.2 K and B3 at 392.3 K; the coolest are E1 at 336.9 K, E2 at 340.7 K and E24 at 343.6 K) average 372.00 K by volume, as defined.

## T3: the what-if with κ_T (the protocol's primary) and the interval of κ_T

| κ | Step 7 loss (pcm) | Fraction of the shortfall removed | Primary label |
|---|---|---|---|
| 1.000 (the library as it is) | 424 | 0 % | fails |
| **1.033 (transport, primary)** | **440** | **7 %** | **fails** (steps 1 good, 2–4 plausible, 5–7 fail) |
| 1.109 (κ_T + 2σ; not in the protocol) | 476 | 22 % | fails |

The last row is an addition made after the analysis to show what the statistical interval allows; it is not a protocol quantity. Even at the upper edge the radial effect leaves most of the shortfall.

## Reading (interpretation, separate from the protocol's labels)

1. **The radial distribution of the fuel temperature is a small effect on the reactivity.** The transport change is 3 % (± 4 %) against the 8 % of the proxy, so the proxy overstated the radial effect, if only by about one standard deviation: the two are compatible, and the transport value is the one to use.
2. **The axial part (proxy 1.07) is untested.** It would need fuel cells split axially into bins with their own temperatures; the radial result suggests its transport value is also smaller than the proxy's, but that is not tested. Taking the proxy at face value for the product of the two (1.16) would remove 31 % of the shortfall; with the radial part at the transport value (1.03) and the axial at the proxy (1.07), about 1.10 and about 20 %.
3. **What this closes.** With the ninth protocol's pin cell, the ten protocols leave the weak fresh-fuel feedback of core 134 (the library table is 36 % short at step 7 and 26–34 % short at steps 3–6) mostly unexplained inside the model: not the reference treatment, the table interval, the hydrogen content, OpenMC's temperature treatment, the thermal scattering evaluation (VII.1), the fuel temperature distribution (radial), nor the thermocouple conversion (supported independently). Left: the code and cell differences against the Serpent reference (the pin cell is 15–18 % weaker with either evaluation), the axial distribution, the temperatures of the Zr rod and the cladding (the model keeps them at 294 K), and the measurement's own uncertainty (the mean fuel temperature carries ±20 % at 100 °C, which is of the order of the step 7 shortfall; at steps 3–6, where it is ±5–10 %, the shortfall of 26–34 % is well outside it).

## Decision (protocol)

1. **κ_T none, agrees with the radial proxy:** the protocol's case 2 applies (the proxy overstates the effect in transport; the radial distribution is not an explanation). With the interval 1.033 ± 0.038 the statement is not sharp: the radial effect is at most about 11 % (upper 2σ) and removes at most 22 % of the shortfall.
2. **The transport value (1.033) is the one to use**, and the axial part remains untested.
3. **Nothing in any library changes**; all stay `experimental`.
4. **Not tried after seeing the results (per the protocol):** other ΔT̄, exponents, particle counts or distributions, an axial distribution, a fit of anything.

## Limits, repeated

κ_T carries ±0.038, so 1.00 and 1.08 cannot be told apart; the axial distribution is not modelled; the temperatures follow the model's own power shapes (which carry their tally uncertainty); one temperature per element, none inside the pellet; the model's Zr rod, cladding and water stay at 294 K.
