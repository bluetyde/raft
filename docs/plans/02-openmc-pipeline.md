# Plan 02: OpenMC pipeline

The offline side: build the reactor in OpenMC, run it over many states and extract everything the library needs.
It runs in WSL2 in the dedicated `openmc-vr` conda env (cloned from `openmc-mcnp`, which stays untouched), with ENDF/B-VIII.0 at `/root/nuclear_data`.
Milestone: M2.

## Stages

```
 model  ──▶  verify  ──▶  plan runs  ──▶  run  ──▶  extract  ──▶  build library  ──▶  validate
 (.py)       (k vs        (config →      (resumable,  (tables,      (schema-valid      (plan 07)
             benchmark)    case list,     cached)      shapes,       folder)
                           cost estimate)              uncertainty)
```

Each stage reads the previous stage's output from disk, so any stage can be rerun alone.

## 1. Model: the JSI TRIGA Mark II

- **Source:** the ICSBEP benchmark **`IEU-COMP-THERM-003`** (confirmed): "TRIGA Mark II Reactor: U(20)-Zirconium Hydride Fuel Rods in Water with Graphite Reflector",
  with two core configurations (132 and 133). It isn't in `mit-crpg/benchmarks`, so we write the model ourselves.
  Cross-check against published MCNP, TRIPOLI, MVP and SuperMC analyses of the same benchmark, and `mit-crpg/openmc-reactor-examples/TRIGA.ipynb` (a generic TRIGA, no license: reference only).
- **Contents:** UZrH fuel elements (standard and instrumented), graphite reflector elements, control rods
  (JSI has four rods: safety, regulating, compensating/shim and pulse; confirm from the benchmark), central thimble, source, radial graphite reflector, pool water.
- **Thermal scattering:** hydrogen and zirconium bound in ZrH need their own S(α,β) data (`c_H_in_ZrH`, `c_Zr_in_ZrH` in OpenMC names).
  They drive much of the prompt temperature feedback.
  **Checked:** our library has both at 296, 400, 500, 600, 700, 800, 1000 and 1200 K, which is enough (no NJOY needed).
  Nuclide cross sections are coarser (250, 294, 600, 900, 1200, 2500 K), so fuel-temperature runs use `settings.temperature = {'method': 'interpolation'}`.
- **Code layout:** `pipeline/models/triga_jsi.py` builds an `openmc.Model` from a parameter dict
  (rod positions, fuel temperature, coolant temperature, xenon density).
  Every run in the pipeline is this one function with different parameters.
- **Tagging for shapes:** each fuel element carries a stable ID (ring and position, e.g. `C3`). The extractor and 3D view both use it.

## 2. Verify

- Compare k-eff at benchmark conditions with the benchmark value. Record the difference in pcm and its statistical uncertainty.
- Compare measured rod worths if the benchmark includes them.
- **Stop and investigate** if the difference is well outside what published OpenMC/MCNP models of the same benchmark get. Don't continue with a bad model.

## 3. Plan runs

A YAML config lists the **cases**. The planner expands it, estimates cost, and writes a case list.

| Family | What varies | Gives |
|---|---|---|
| `reference` | Nothing (benchmark state) | k₀, excess reactivity, flux-per-watt factor |
| `rod-worth` | One rod at a time over N positions, others at the reference state | Integral and differential worth curves |
| `rod-pairs` | A few joint configurations | Check on superposition and rod shadowing |
| `fuel-temp` | T_f over a grid (room temperature to above the highest pulse temperature) | ρ_fuel(T) |
| `coolant-temp` | T_c over the pool's range | ρ_cool(T) |
| `xenon` | Xe-135 density over a range | ρ_xe(X) |
| `kinetics` | Reference state, delayed neutrons on/off or IFP tallies | β_eff, β_i, λ_i, Λ |
| `shapes` | Grid over rod positions and T_f | 3D power shapes |
| `holdout` | Random states *between* grid points | Interpolation error (plan 07) |

**The curse of dimensionality:** four rods × ten positions × several temperatures is already thousands of shape runs.
Start with a **separable approximation**:

```
shape(z₁…z₄, T_f) ≈ shape_ref + Σ_r Δshape_r(z_r) + Δshape_T(T_f)
```

Then use `rod-pairs` and `holdout` runs to measure the error.
Add joint grid dimensions only where that error is too large.
The library format ([03](03-library-format.md)) supports both forms.

**Budget first:** the planner estimates core-hours from a quick timing run and a target uncertainty.
Rod-worth differences are small, so they need tight k uncertainty (on the order of 10 pcm).
That dominates the cost. Agree on the budget before starting the big runs.

## 4. Run

- `pipeline/runs/runner.py` runs cases one by one or in parallel.
  Each case goes in its own folder named by a **content hash** of: the generated model XML (not just its parameters), a digest of the nuclear data actually used
  (`cross_sections.xml` plus file checksums, not just the path), the OpenMC version and relevant dependencies, the tally definitions and the run settings.
  An existing **completed** result with a matching hash is reused and not rerun.
- **Case states:** `pending`, `running`, `failed`, `completed`. A result counts only after completion checks (statepoint present, batches complete).
  Failed cases retry a bounded number of times, and each cause is recorded. An interrupted run can never be read as complete.
- **Raw and derived are separate:** statepoints are raw; extraction products have their own hash (raw hash + extractor version),
  so an extractor change re-extracts without rerunning transport.
- Resumable: a crash or reboot loses only the case that was running.
- Logs record the OpenMC version, nuclear data path and git commit for each case.
- Runs happen in WSL. Big folders stay out of git (`pipeline/cache/` in `.gitignore`).

## 5. Extract

- **Reference state:** the extractor records the reference rod vector, temperatures and xenon, and the transport-computed reference reactivity. Every table is a delta from it.
- **k and reactivity:** ρ = (k − 1)/k, uncertainties propagated.
  Worth curves are fitted with a monotonic smoothing fit, so noise doesn't create negative differential worth.
  The raw points are kept alongside.
- **Kinetics:**
  - β_eff by the prompt method: ≈ 1 − k_prompt/k, with delayed neutrons turned off in the settings.
  - β_i and λ_i from delayed-group tallies or from the nuclear data.
  - Λ and adjoint-weighted β_eff from IFP tallies. **Checked:** OpenMC 0.15.3 supports them (`Settings.ifp_n_generation`; scores `ifp-time-numerator`, `ifp-beta-numerator`, `ifp-denominator`).
- **Shapes:** one declared tally basis per library (**fission rate or deposited heating, never mixed** without a documented conversion) per **fuel element × axial bin** (about 10–20 bins).
  Record bin volumes, array order, tally basis, normalization basis and which regions receive the power.
  That matches TRIGA's pin geometry and is much smaller than a Cartesian mesh. Shapes are normalized to a total of 1.
  Relative uncertainty is stored per bin, so the viewer can grey out noisy bins.
- **Flux-per-watt** `k_φ` for xenon: from flux and heating tallies at the reference state.
- **Thermal properties** (heat capacity, masses, h·A): not from OpenMC.
  They come from published TRIGA data, and each one is recorded with its source.

## 6. Build the library

`pipeline/library/build.py` collects everything into the format in [03](03-library-format.md).
It builds into a **staging folder** and publishes the manifest only after every asset and validation check passes.
It writes provenance (model hash, OpenMC version, nuclear data, git commit, dates) and validity ranges for each axis.
It then validates against the schema.

## 7. Validate

Handed over to [07-validation.md](07-validation.md): benchmark comparisons, holdout interpolation error and the pulse comparison.

## Open questions

- Run the pipeline in a dedicated `openmc-vr` env (see [TOOLING.md](../TOOLING.md) §2), and decide whether to move to OpenMC 0.16 before the big runs.
- Configs: TOML (stdlib `tomllib`) instead of YAML, so the shared env needs no new package.
- Do we need burnup (the JSI core's fuel isn't fresh)? The benchmark state defines the composition. Depletion is a later extension.
- How can we run this in parallel on this one machine? Pick a sensible thread count so it doesn't clash with other agents' OpenMC work (see WORKFLOWS).
