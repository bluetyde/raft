# Physics notes: what the engine solves

This is the model in `physics_ref/engine.py` (Python reference) and `web/src/sim/engine.ts` (the browser engine). The two agree on golden vectors. It is a **point model**: no space, no flow loop, no pressure. Read it with [limits in the README](../README.md#limits).

## State

Power `P` (W), six delayed-neutron precursor groups `C_k`, fuel temperature `T_f`, coolant temperature `T_c`, iodine `I`, xenon `X`, plus two integrals (energy, heat removed) and the lagged instrument values.

## Equations

Point kinetics with six delayed groups, generation time `Λ`, delayed fractions `β_k`, decay constants `λ_k`, `β = Σ β_k` and an optional external source `S`:

```
dP/dt   = (ρ − β) / Λ · P + Σ λ_k C_k + S
dC_k/dt = β_k / Λ · P − λ_k C_k
```

Thermal, with `f` the fraction of power deposited in the fuel, `q = hA · ΔT` (or the temperature dependent form in [library format §8](library-format.md)) the fuel to coolant heat flow, and `q_hx = UA · (T_c − T_sink)` the heat exchanger while its pump runs:

```
m_f · c_p,f(T_f) · dT_f/dt = f · P − q
m_c · c_p,c       · dT_c/dt = (1 − f) · P + q − q_hx
```

Poisons, with `φ = flux_per_watt · P`:

```
dI/dt = γ_I Σ_f φ − λ_I I
dX/dt = γ_X Σ_f φ + λ_I I − λ_X X − σ_X φ X
```

## Reactivity is a sum of tables

```
ρ = ρ_ref + calibration + fault + Σ rods + ρ_fuel(T_f) + ρ_coolant(T_c) + ρ_xenon(X)
    [+ ρ_boron(ppm)]  [+ rod interaction]
```

Every term is a table from the library, interpolated piecewise linearly with the library's declared behaviour outside its range (clamp, extrapolate, or reject). Each rod's worth is a table in its position. Boron and the rod interaction (`point-kinetics/rod-interaction-v2`, a shadowing correction on the rods' summed worth) are capabilities a library may or may not carry.

There is no feedback beyond what these tables say. Nothing in the model computes a worth or a coefficient: they come from the library, which is built from transport runs or from cited data, with the uncertainty it records.

## Numerics

A fixed outer step (`config.outerDt`, default 10 ms) with adaptive Rosenbrock sub-steps (ROS2/ROS3P) because kinetics is stiff. Trip crossings inside a step are located by bisection so a trip fires at the right time, not at a step boundary. All sums are explicit loops in a fixed order so that the Python and TypeScript engines give the same results to the last bits that matter (`physics_ref/numerics.py`).

## What the model does not do

No spatial kinetics, no xenon oscillations, no decay heat, no moderator density or void feedback beyond the coolant temperature table, no primary loop or pressure, no fuel burnup during a run. The 3D power shape shown in the viewer is a stored base shape plus rod-position and fuel-temperature corrections from the library; it is output only and does not feed back into the kinetics.

## Where the numbers come from

[library-format.md](library-format.md) lists, per field, whether a value is measured, computed, cited or assumed. [validation/supported-envelope.md](validation/supported-envelope.md) says which states have been compared with transport or measurements and by how much.
