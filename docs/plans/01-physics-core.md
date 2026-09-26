# Plan 01: Physics core

The time-dependent model that runs live.
It's written first in Python (`physics_ref/`), which is the reference, and then ported to TypeScript (`web/src/sim/`).
Milestones: M1 (Python prototype), M4 (TypeScript port).

## Scope

In scope for v1:
- Point kinetics with six delayed-neutron groups and an external source (needed for startup from shutdown).
- Reactivity from rods, fuel temperature, coolant temperature and xenon.
- A lumped thermal model: fuel, and coolant/pool.
- Iodine-135 and xenon-135.
- Rod motion, scram and trip logic.

Out of scope for v1, noted for later:
- Samarium (a small effect at TRIGA flux levels, but cheap to add).
- Spatial kinetics or flux-shape changes during fast transients (the precomputed shapes cover slow changes only).
- Photoneutrons from the pool water (they matter mainly for very low-power behavior after shutdown).
- Rod shadowing (one rod's worth changing because of another rod's position). Start with independent worth curves, then check how big the error is during M2.

## State vector

| Variable | Symbol | Unit |
|---|---|---|
| Power (neutron population, scaled) | P | W |
| Delayed precursors, groups 1–6 | C_i | W-equivalent (scaled with P) |
| Fuel temperature (core average) | T_f | K |
| Coolant/pool temperature | T_c | K |
| Iodine-135, xenon-135 (core average) | I, X | atoms/m³ |
| Rod positions | z_r | fraction withdrawn |

Precursors are expressed in power units, so the equations don't need the neutron-to-power conversion.
In this scaled form the source S is in **W/s**.

## Initialization (must be explicit)

At precursor equilibrium `C_i = β_i P / (Λ λ_i)`, and the power equation reduces to `0 = ρP/Λ + S`, so **`P = −SΛ/ρ`**.
Consequences:
- A **critical steady state** (ρ = 0, constant P) exists only with **S = 0**.
- A **source-driven shutdown** equilibrium needs **ρ < 0**. An equilibrium request at ρ ≥ 0 with S > 0 is **rejected** with a reason, never silently solved as critical.
- Initial states say explicitly: equilibrium precursors or supplied inventories; initial iodine/xenon (zero, equilibrium at a stated power, or supplied); fuel and coolant temperatures.

## Equations

Point kinetics with a source:

```
dP/dt   = ((ρ − β)/Λ) · P + Σ_i λ_i C_i + S
dC_i/dt = (β_i/Λ) · P − λ_i C_i
```

Reactivity is a sum of parts. Each part comes from a table in the library, never from a constant in code:

```
ρ = Σ_r ρ_rod,r(z_r)  +  ρ_fuel(T_f)  +  ρ_cool(T_c)  +  ρ_xe(X)  +  ρ_0
```

- `ρ_rod,r(z)` is the integral worth curve for rod r.
- `ρ_fuel(T)` is a **reactivity-vs-temperature table**, not a single coefficient.
  In TRIGA fuel the temperature coefficient changes with temperature, and pulses cover several hundred kelvin.
- `ρ_0` is the **reference reactivity**: the transport-computed reactivity at the library's stored reference state
  (rod vector, temperatures, xenon). Each table is a **delta from that same reference** and is exactly zero there.
  Any adjustment to force criticality is stored separately as a labelled **calibration**, never folded silently into ρ_0 (see [03](03-library-format.md)).

Lumped thermal model:

```
m_f c_f(T_f) · dT_f/dt = P − h A (T_f − T_c)
m_c c_c      · dT_c/dt = h A (T_f − T_c) − Q_hx(T_c)
```

- `c_f(T)` depends on temperature (the heat capacity of UZrH rises noticeably with temperature). It's a table in the library.
- During a pulse (milliseconds), heat has no time to leave the fuel, so the model becomes **adiabatic** on its own. No special case is needed.
- `Q_hx` is heat removal by the pool cooling system. It's zero when the pumps are off.
- **Assumption, stated in the library:** all of P is deposited in the fuel (or a declared fraction; the rest goes to the coolant).
  There's no separate decay-heat inventory in v1, so P is the prompt fission power. If decay heat is added, kinetics power and thermal power become different variables.
- Later option: split the fuel into a hot element (for trip checks) and the average.

Iodine and xenon:

```
dI/dt = γ_I Σ_f φ − λ_I I
dX/dt = γ_X Σ_f φ + λ_I I − λ_X X − σ_X φ X
```

Flux comes from power through a factor in the library: `φ = k_φ · P`. The pipeline computes that factor (average flux per watt).
`ρ_xe(X)` comes from a library table produced by OpenMC runs with xenon added.
Decay constants and yields are nuclear data, but they still go in the library so its provenance stays complete.

## Solver

**Implemented (2026-09-26): ROS2** (two-stage Rosenbrock, order 2, L-stable, embedded order-1 error estimate), dense LU on the ~17-variable system,
finite-difference Jacobian and time derivative, relative + absolute tolerances per component. Rods are known functions of time within a step.
Checkpoints store the current step size, so a restored run is bit-identical. Order 2 is slow for long runs at tight tolerance
(tracking a power decay from 100 kW to source level for an hour takes ~30k steps at rtol 1e-6): **ROS3P or similar is a TODO** before long scenarios.
Verified against scipy's Radau on the same equations (`TestIndependentIntegrator`, runs where scipy is installed).

**Finding:** the full model's pulse peak is 3.4% above Nordheim–Fuchs for the synthetic core, because delayed neutrons return during the ~50 ms pulse.
With return suppressed (the formula's assumption), the engine matches the formula to better than 0.1%.

The equations are **stiff**. Prompt behavior happens on the scale of Λ (tens of microseconds for TRIGA; check the value in M2).
Xenon changes over hours. The solver has to handle both without slowing the browser down.

- **Method:** an implicit, adaptive, L-stable scheme. Candidates are BDF2 with a variable step, or a Rosenbrock (ROS3P-type) method.
  Pick one in M1 by testing both against the analytic cases below. Prefer whichever is simplest to port to TypeScript.
- **Error control:** relative tolerance on P and C_i, because power spans more than ten decades, from source level to pulse peak.
  Consider integrating ln P when P is far below the source-driven equilibrium.
- **Outer step:** fixed, e.g. 10 ms of sim time, matching the runtime clock. At high time rates, work is done in bounded batches and the achieved rate is reported (see ARCHITECTURE).
  Decide here whether slow regimes may use larger scheduling intervals.
- **Restart boundaries:** if a multistep method (BDF2) is chosen, it restarts at canonical checkpoint boundaries in every run, so a restored checkpoint reproduces the same trajectory.
  Inside each outer step, reactivity from rods moving at constant speed is known exactly, so the solver sees smooth inputs.
- **Events inside a step:** a trip setpoint crossing or a command time splits the step at that instant. Scrams must start at the right moment.
- **Check before porting:** the Python version must pass every test below before any TypeScript is written.

## Rods, scram and trips

- Each rod has a drive speed (fraction per second), travel limits and a scram insertion profile (position against time after a scram). All come from the library.
- **Transient rod (pulse):** fired pneumatically. It's modelled as a fast withdrawal over a time from the library, not an instant step, so the pulse shape isn't distorted.
- **Trips:** each trip declares its **input channel** (the ideal modeled quantity or a named instrument channel), threshold direction, and latching and reset behavior.
  Crossings are detected inside a solver step (event location), not at frame times. A trip starts the scram profile for every rod.
  Instrument updates follow sim time, independent of render rate, so a failed instrument feeding a trip behaves the same at any frame rate.
- **Interlocks** (enforced in the sim core, not the UI): for example, pulse mode is blocked above a power limit, and only one rod can be withdrawn at a time.
  The library lists the rules as a **small typed predicate format** (validated signal references, a fixed set of operators). Unknown operators are errors.

## Tests (all in `physics_ref/tests/`, then copied as vectors into `schema/vectors/`)

| Test | Checks | Reference |
|---|---|---|
| Critical steady state | ρ = 0, **S = 0**, equilibrium precursors: P stays constant to machine precision | Trivial |
| Impossible equilibrium | Equilibrium requested at ρ ≥ 0 with S > 0 | Must be rejected with a reason |
| Prompt jump | Immediate power ratio after a small step change in reactivity | P₁/P₀ ≈ β/(β−ρ) |
| Stable period | Asymptotic period after a step change in reactivity | Roots of the inhour equation (computed separately, in the test) |
| Prompt critical | ρ = β behaves continuously, with no solver blow-up | Stability only |
| Nordheim–Fuchs pulse | Adiabatic step above prompt critical with a constant feedback coefficient | Analytic peak power, energy and pulse width |
| Source multiplication | Subcritical equilibrium P = S Λ / (−ρ) | Analytic |
| Xenon equilibrium | Steady power gives equilibrium I and X | Analytic |
| Post-shutdown xenon | Time of the xenon peak after a scram | Analytic, from I and X decay |
| Energy balance | ∫P dt equals the stored heat change plus heat removed | Conservation |
| Determinism | Same pinned inputs twice give bit-identical output (Python vs TS: agreement within tolerance) | — |
| Convergence | Results converge as step size and tolerance shrink | Self-convergence |
| Checkpoint and events | Restoring a checkpoint and replaying matches the uninterrupted run; a trip inside a step fires at the right time | Uninterrupted run |

Tolerances are **absolute plus relative**, so near-zero quantities don't produce meaningless relative errors.
Approximate analytic references (e.g. Nordheim–Fuchs assumes adiabatic, constant feedback) state their assumptions in the test.
An **independent integration path** (scipy `solve_ivp`, configured separately) checks our own scheme. Golden vectors only catch port drift, not mistakes both versions share.

Then the **M1 go/no-go:** use published JSI TRIGA parameters (entered by hand into a test library) and reproduce published pulse data.
That means peak power, FWHM and energy against inserted reactivity. See [07-validation.md](07-validation.md).

## Porting to TypeScript (M4)

- Port function by function, keeping the same names and structure as the Python version.
- `schema/vectors/` holds input/output pairs produced by Python. The TypeScript test suite (Vitest) must match them within stated tolerances.
- Whenever the Python reference changes, the vectors are regenerated and the TypeScript tests must pass again.
- Run the core in a Web Worker with no DOM dependencies, so it also runs under Node for tests and command-line replays.

## Open questions

- Is one lumped fuel temperature enough for the pulse shape, or does TRIGA need a few radial nodes in the fuel? Decide from M1 results.
- Should the reactivity tables be linear or spline interpolated? Splines give smooth derivatives, but can overshoot.
- Where does the pool heat-exchanger model come from? JSI publications, or a generic model with a clear label saying so?
