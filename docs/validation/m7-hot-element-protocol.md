# M7 hot-element temperature: comparison protocol (third protocol, written before any run of it, 2026-10-06)

It follows `m7-heat-transfer-protocol.md` and its results. The heat transfer law fitted the reactivity and the temperature *shape*, but needed the measured hot-element rise (201 K at 250 kW) to be only 1.15–1.25 times the model's mean fuel rise. That looks too low for an element at maximum power density. This protocol tests whether the library's own shape arrays, an in-element conduction model and independent pulse data can account for the measured thermocouple temperature, **without changing any fitted number**. Nothing here has been run.

## Disclosure: what was seen before writing

This protocol is **not blind**, and one result is expected in advance.

- All earlier data and results (first protocol, second protocol).
- **The library's shape arrays at the reference rod state** (an input, not a model output of the comparison): in the core-242 and core-246 libraries the centre-plane bin of the B-ring elements carries **1.9–2.0 times the mean element linear power** (core 242: 1.90–1.99; core 246: 1.90–1.98; all 61 and 67 element ids counted). The experiment's rod state (shim and safety fully withdrawn) has not been applied.
- **A hand calculation with those numbers**, made to check that the chain is implementable (k = 15–25 W/m·K, the geometry of the Svajger 2024 Table 1, the fitted mean rise of 172 K and n = 0.22): the predicted hot-element centre rise at 250 kW is **310–360 K, 1.5–1.8 times the measured 201 K**. So **the shape-array version of metric H1 is expected to fail high.** The protocol is built to explain that, not to hope it away.
- **Not seen:** any number from the pulse database beyond its column names (`t1_max_c`, `t2_max_c`, the energy columns, `core_config`). Stage 1 below uses them blind.

## The question

If the measured thermocouple rise is 201 K at 250 kW, what peaking does it imply, and is that the peaking the library's shape arrays give for an instrumented element? If not, which input (peaking, conduction, the library's fuel coefficient) is inconsistent?

## Stage 1: the thermocouple's peaking from independent data (the pulses)

A pulse heats the fuel almost adiabatically, so the thermocouple's rise is its local power density times the energy: `T_max − T_0 = F_tc · E / (M · c̄)`.

For each pulse of core 242 (and of core 246 separately) with a non-empty `t1_max_c` (thermocouple 1) or `t2_max_c` (thermocouple 2) and a non-empty energy:

    F_tc = (T_max − 25 °C) · M · c̄ / E       M = 137.054 kg (library fuel mass), c̄ = mean of the library's fuel cp table from 25 °C to T_max

- Energy: `energy_1000pts_mws` (primary); `energy_1pct_mws` and `energy_tangent_mws` as sensitivities. The initial temperature is taken as 25 °C (the database summary has no initial reading); 20 and 30 °C are sensitivities.
- Report, per core and per thermocouple: the number of pulses, the median F_tc and the inter-quartile range. **Fewer than 5 pulses for a core and thermocouple: "not computed".** No pulse is dropped except for an empty field or a zero energy.
- The primary F_tc is the **median over both thermocouples and the usable pulses of that core**; the two thermocouples are also reported separately (they sit in two different elements).
- Limits, stated now: the thermocouple reads with a lag and may under-read the peak; conduction during the pulse is neglected; the mean fuel mass is the whole core's. These bias F_tc **low**.

## Stage 2: the peaking from the library's shape arrays

At the experiment's rod state (safety, shim, transient fully withdrawn; regulating at its step position `x = (900 − step)/719`) and the mean fuel temperature of the state, rebuild the power shape with the library's own separable form (`base + Σ rod deltas + temperature delta`, `physics_ref.engine.Engine.shape`). For element `e` and the centre-plane axial bin:

    F_shape = (fraction(e, centre bin) / bin height) / (1 / (N · L))      N = elements with power, L = 38.1 cm

Candidates for `e`: each B-ring element (B1–B6; the Ravnik description says the instrumented elements sit "in the locations with maximum power density (normally B ring)"). Primary: the B element with the largest centre-bin factor. Also reported: the hottest bin of that element and the lowest B element.

## Stage 3: the steady-state hot-element temperature

At each measured state (power `P`, the fitted law `dT = (P·100^n/h0)^(1/(1+n))` from the heat-transfer protocol, same sensitivities) with the fuel geometry of Svajger 2024 Table 1 (Zr rod radius `Ri` = 0.31750 cm, fuel radius `Ro` = 1.82245 cm; no heat flows through the Zr rod):

1. Mean element: `q'_mean = P / (N·L)`, `q'''_mean = q'_mean / (π(Ro² − Ri²))`.
2. Conduction drop at radius `r`, for volumetric power `q'''` and conductivity `k`: `ΔT_cond(r) = q''' · c(r) / k`, with `c(r) = [(Ro² − r²) − 2Ri² ln(Ro/r)] / 4`. The volume-mean drop uses `c̄ = (2/(Ro² − Ri²)) ∫ c(r) r dr`.
3. Surface rise of the mean element: `dT_s,mean = dT − ΔT_cond,avg(q'''_mean)` (the law's `dT` is the mean fuel rise over the pool).
4. Hot element at local peaking `F`: heat flux scales by `F`, so the surface rise is `dT_s,hot = dT_s,mean · F^(1/(1+n))`, and the conduction drop at the thermocouple's radius is `F · q'''_mean · c(r_tc) / k`.
5. **Thermocouple temperature rise:** `T_tc − T_pool = dT_s,hot + F · q'''_mean · c(r_tc) / k`. Compare the difference between each state and state 1 with the measured `T_f(state) − T_f(state 1)`.

`F` is **F_tc** (Stage 1) in the primary variant **H-pulse**, and **F_shape** (Stage 2) in the comparison variant **H-shape**.

Inputs fixed now:

| Input | Primary | Sensitivities | Source and caveat |
|---|---|---|---|
| Conductivity `k` | 18 W/m·K | 15 and 25 | the value usually quoted for U-ZrH1.6; **to be confirmed against Simnad, GA-A16377 (1981), before the run**; if that gives a value outside 15–25 the bracket is widened to include it, and that is the only allowed change. Temperature dependence ignored |
| Thermocouple radius `r_tc` | `Ri` (the hottest radius, next to the Zr rod) | 0.762 cm (the placement of the KSU instrumented elements) | the JSI description says only that the tip is "in the centre of the fuel element" |
| Axial position | centre-plane bin | the element's hottest bin | |
| Elements | the B element above | each of B1–B6 | position of the instrumented elements in cores 242 and 246 is not known |
| Heat transfer fits, T0, power axis, pool case | as in the heat-transfer protocol (eight combinations per core) | | |

## Metrics and bands (fixed now)

| # | Quantity | Bands |
|---|---|---|
| **G** | Consistency of the two peakings: `F_tc / F_shape` (primary configurations) | **good** 0.85–1.15, **plausible** 0.70–1.40, **fails** outside |
| **H1** | Predicted / measured thermocouple rise at 250 kW (201 K), for H-pulse and for H-shape | **good** 0.85–1.15, **plausible** 0.70–1.40, **fails** outside (reported as "high" or "low") |
| **H2** | Temperature shape of the thermocouple, `θ(P) = (T(P) − T(0.09 kW)) / (T(250 kW) − T(0.09 kW))`, at the held-out states 4, 5, 6: max difference from the measured θ | **good** ≤ 0.05, **plausible** ≤ 0.10, **fails** above |
| **R** | Implied fuel coefficient: the mean rise `dT_inf` for which the chain reproduces the measured 201 K (with F_tc and with F_shape), and `R_α = 1426.8 pcm / library defect at dT_inf` | reported; read as **consistent** if 0.8 ≤ R_α ≤ 1.25 |

The labels are the worst over the sensitivities that the table lists, with the best beside them, and the primary configuration given on its own line.

## Decision process

1. **G good or plausible, H1 (H-shape) fails high:** the peaking is understood and the chain predicts a hotter thermocouple than measured. Then R_α says by how much the library's mean fuel rise (or its coefficient) would have to differ; the fitted `h0` is shipped as "fitted to the reactivity; the library's mean fuel temperature rise may be too large by R_α⁻¹" in the manifest's source string, and the fuel coefficient goes on the list for an independent check (not fitted here).
2. **G fails (F_tc well below F_shape) and H1 (H-pulse) good or plausible:** the thermocouples are in elements with lower peaking than the library's hottest B element, and the steady-state data are consistent with the fitted law once the thermocouple's real peaking is used. The fitted `h0` is shipped as "consistent with the hot-element data" and the peaking factor of 1.15–1.25 is explained.
3. **Both fail, or Stage 1 is "not computed":** the explanation is not found in these inputs. Record it; the open candidates are the fuel coefficient, the conductivity, an element outside the B ring, and a pool or instrument effect. Each would need independent data.
4. **In every case:** nothing fitted is changed (not `h0`, not `n`, not `k`, not the fuel tables); the library status stays `experimental`; the format change for the heat transfer law can proceed independently, because the law's shape and exponent do not depend on this protocol.
5. **Not tried after seeing the results:** other conductivities, thermocouple radii or axial positions than those listed, a temperature-dependent conductivity, a gap conductance model, other elements than B1–B6, any change to the shape arrays.

## Implementation (to be written after this protocol)

`validation/m7_hot_element.py`: the pulse reader and Stage 1 (the pulse columns and core numbers checked on the first run, the report listing the counts), Stage 2 through the reference engine's shape reconstruction, Stage 3 in closed form with numerical integration for `c̄`, reusing the heat-transfer script's fits. A regression test on a synthetic library with known peaking, conduction constants and a known adiabatic pulse; the report `validation/m7_hot_element_report.json`; the results note `docs/validation/m7-hot-element-results.md`. The script is run once.

## Limits, repeated

One steady-state exercise and a pulse database whose thermocouple readings lag; unknown instrumented-element positions and core; the conduction model is a constant-conductivity annulus with no gap, clad or flux depression in the pellet; all of these enter `F`, so a "good" result means the chain is consistent with the data, not that each factor is right.
