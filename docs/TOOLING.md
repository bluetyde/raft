# Tooling and ecosystem survey

A reference for future sessions: every repo and tool this project uses or could use, what state each is in,
and where something old could be upgraded, reused or built instead.
**Surveyed 2026-09-25.** Versions and activity dates came from the installed environment, the GitHub API and PyPI on that date.
Re-check anything you're about to rely on if this is months old.
**This is a survey, not setup instructions.** The canonical setup (envs, ports, processes) is [WORKFLOWS.md](WORKFLOWS.md) section 0.

---

## 1. Our own repos

| Repo | Where | Stack | Relationship to this project |
|---|---|---|---|
| **virtual-reactor** (this) | `C:\Users\jwncr\Claude Code Test\virtual-reactor` | Planned: Python pipeline + TS/Vite/three.js web | Not a git repo yet (TODO: private `bluetyde/virtual-reactor`) |
| **openmc-studio** | `bluetyde/openmc-studio` (public or going public). Daily install `C:\OpenMC`, SSD/shared checkout `D:\OpenMC`, Claude clone `C:\agents\claude\openmc-studio` | Python stdlib `http.server` + OpenMC; single `static/index.html`; hand-written **WebGL2** CSG ray tracer with a **BVH** in textures (since `4b163a6`, 2026-09-17; 10,000+ parts); FreeCAD CAD import (`openmc-cad` env); ParaView export | **Main reuse source.** It already has a CSG ray tracer, cutaways, a flux-map slice, a 3D volume view, CAD import and a material library (PNNL-15870). A possible later "export simulator library" button |
| **openmc-mcnp-project** | `bluetyde/openmc-mcnp-project`, WSL `~/openmc-mcnp-project` (a stray untracked copy exists under `C:\...`; ignore it) | Python; OpenMC → MCNPy → MontePy; deck validation | Only needed if we want MCNP cross-checks of the TRIGA model. Useful for level-3 validation against published MCNP results |

Multi-agent rules for all three: `messages/INSTRUCTIONS.md`. This project's log: `messages/virtual-reactor.md`.

---

## 2. Installed environment (checked 2026-09-25)

**WSL2 Ubuntu, conda env `openmc-mcnp`** (shared with Studio and the exporter, so **don't upgrade it in place**):

| Package | Installed | Latest seen | Note |
|---|---|---|---|
| Python | 3.11.15 | — | `tomllib` is in the stdlib, so TOML configs need no install |
| **openmc** | **0.15.3** | **0.16.0** (2026-08-05) | Has IFP kinetics (see §3). Upgrade in a separate env first |
| numpy / scipy | 2.4.6 / 1.17.1 | — | scipy `solve_ivp` (Radau, BDF, LSODA) is enough for the Python reference solver |
| h5py / pandas / matplotlib | 3.16.0 / 3.0.3 / 3.11.1 | — | Fine |
| uncertainties | 3.2.3 | — | Use it for propagating k-eff → ρ uncertainty |
| montepy | **1.1.3** | **1.5.0** (2026-07-25) | 1.1.3 can't parse `<` tally chains (a Studio issue). Check whether 1.5 fixes that |
| mcnpy / metapy | 0.0.7 / 0.0.1 (RPI wheels, py4j Java bridge) | — | Slow (~8 s per translation) and its lattice translation is wrong. PyPI also has an unrelated-looking `mcnpy` 0.2.5, so don't mix them up |
| PyYAML, numba, pytest | **missing** | — | Prefer TOML (stdlib) over YAML; `unittest` or a separate env for pytest |

Other envs: `openmc-cad` (FreeCAD, for Studio's CAD import) and `base`.
Nuclear data: ENDF/B-VIII.0 HDF5 at `/root/nuclear_data/endfb-viii.0-hdf5` (556 neutron, 34 thermal, 100 photon).

**Windows side:** Node 24.18, npm 11.16, git 2.55, Python 3.14 (not used for OpenMC). **WSL has no Node.**
So the web app builds on Windows and the pipeline runs in WSL. The library folder is the handoff: WSL writes it to a path under `/mnt/c/...`.
It's only a few MB, so cross-filesystem speed isn't a problem.

**Recommendation:** create a dedicated env `openmc-vr` (clone of `openmc-mcnp`, plus pytest, and later OpenMC 0.16).
Then the pipeline can upgrade without risking Studio's env. There's precedent: `openmc-cad` is already separate.

---

## 3. Facts checked that close TODO items

| Question | Answer | Source |
|---|---|---|
| JSI TRIGA benchmark ID | **`IEU-COMP-THERM-003`**, "TRIGA Mark II Reactor: U(20)-Zirconium Hydride Fuel Rods in Water with Graphite Reflector". Two core configurations (132 and 133) | [OSTI/ETDEWEB](https://www.osti.gov/etdeweb/biblio/20510819) |
| `c_H_in_ZrH`, `c_Zr_in_ZrH` temperatures in our data | **296, 400, 500, 600, 700, 800, 1000, 1200 K**. That covers everything from room temperature to far above TRIGA pulse fuel temperatures in 100 K steps up to 800 K. **NJOY is not needed** | Our HDF5 files |
| Other thermal data we'll need | `c_H_in_H2O` 284–800 K (17 points), `c_Graphite` 296–2000 K, `c_Al27` (20–800 K, for aluminium clad) | Our HDF5 files |
| U-235 (and other nuclide) temperatures | 250, 294, 600, 900, 1200, 2500 K. **Coarse**, so fuel-temperature runs should use `settings.temperature = {'method': 'interpolation'}` (or the windowed multipole data, which our library doesn't include) | Our HDF5 files |
| IFP kinetics in our OpenMC | **Yes**, in 0.15.3: `Settings.ifp_n_generation` plus scores `ifp-time-numerator`, `ifp-beta-numerator`, `ifp-denominator` → Λ and β_eff directly | Installed source |
| Measured pulse data | **Public JSI database** at [trigapulse.ijs.si](http://trigapulse.ijs.si/): **493 pulses (1991–2021)** with ρ in $, rod position, P_max, energy, FWHM, T_max, plus raw and processed traces. **No license statement**, so ask the listed contact before redistributing | Site |

---

## 4. External tools by project area

Legend: **Use** = depend on it · **Ref** = read it or compare against it, don't depend on it · **Watch** = maybe later · **Avoid** = reason given

### Physics core (plan 01)
| Tool | Status (2026-09-25) | License | Verdict |
|---|---|---|---|
| scipy `solve_ivp` (Radau/BDF) | Installed | BSD | **Use** for the Python reference solver. Well tested, so our own scheme can be compared against it |
| [PyRK](https://github.com/pyrk/pyrk) | Last push 2025-09, last PyPI release 2023; 37★ | **No standard license** (the author asks to be contacted) | **Ref only.** Compare results. Don't copy code |
| [diff-grok](https://github.com/datagrok-ai/diff-grok) | TypeScript ports of CVODE/LSODA/Rosenbrock; active but 1★ | MIT | **Watch.** Plan: write our own small Rosenbrock or BDF2 in TS (a 10-variable system), and use diff-grok only as an independent check in tests |
| [openpointkinetics](https://github.com/richmorrison/openpointkinetics) | Dormant since 2018 | GPL-3.0 | **Ref** for teaching examples only |

### OpenMC pipeline (plan 02)
| Tool | Status | License | Verdict |
|---|---|---|---|
| [OpenMC](https://github.com/openmc-dev/openmc) | 0.15.3 installed, 0.16.0 out; very active | MIT-style | **Use.** Test 0.16 in `openmc-vr` before M2's big runs |
| [OpenMC Plotter](https://github.com/openmc-dev/plotter) | Active | MIT | **Use** for debugging the TRIGA geometry by eye (no runtime dependency) |
| [mit-crpg/openmc-reactor-examples](https://github.com/mit-crpg/openmc-reactor-examples) `TRIGA.ipynb` | Last push 2025-02 | **No license** | **Ref only.** A generic TRIGA template, not the JSI core. Useful for cross-checking dimensions |
| [mit-crpg/benchmarks](https://github.com/mit-crpg/benchmarks) | Active, MIT; has an `icsbep/` folder | MIT | **Doesn't contain IEU-COMP-THERM-003** (checked), so we build the JSI model ourselves from the handbook. Contributing it back later would be a real contribution |
| [WATTS](https://github.com/watts-dev/watts) | Active (2026-07) | MIT | **Watch.** Templated parameter sweeps. Our run config plus hash cache is simpler for now. Revisit if sweeps get complicated |
| [NCrystal](https://github.com/mctools/ncrystal) | Very active | Apache-2.0 | **Not needed** (our ZrH data covers the range). Keep in mind if S(α,β) data is ever missing |
| NJOY / FrendyPlus | — | — | **Not needed** (see §3) |

### Library format and render geometry (plan 03)
| Tool | Verdict |
|---|---|
| JSON Schema (+ `jsonschema` in Python, `ajv` in TS) | **Use.** Check whether `jsonschema` is in the env |
| glTF (`.glb`) for meshes | **Use** later for non-primitive geometry. It's the standard three.js format |
| **Studio's CSG ray tracer** (alternative logic) | **Reuse instead of meshing.** Studio already ray-traces OpenMC-style CSG in a WebGL2 shader (GLSL `#version 300 es`), with the BVH built in JS and packed into a texture, and it scales to 10,000+ parts. A TRIGA's few hundred regions are well within that. The library could ship CSG, skipping marching cubes and glTF for most reactors. See `studio/openmc_studio/static/index.html` ("3D Viewport: ray-traced CSG in WebGL 2 with BVH", plus the JS BVH walk used for clicking) |
| [DAGMC](https://github.com/svalinn/DAGMC), [GEOUNED](https://github.com/GEOUNED-org/GEOUNED), CAD_to_OpenMC | **Ref.** Only relevant if a future reactor comes from CAD. Studio already covers CAD import via FreeCAD |

### 3D explorer (plan 04)
| Tool | Status | Verdict |
|---|---|---|
| [three.js](https://github.com/mrdoob/three.js) | r186 (2026-09-24), MIT | **Use, with `WebGLRenderer` (WebGL2).** WebGPURenderer has been production-ready since r171, but **custom GLSL (`ShaderMaterial`/`RawShaderMaterial`) doesn't run on it**, so Studio's GLSL ray tracer couldn't be reused there. WebGPU brings nothing this scene size needs. Revisit only if a WebGPU-only feature becomes worth porting the shaders to TSL |
| Vite | Active, MIT | **Use** (matches the other projects) |
| Vitest | — | **Use** for TS tests |

### ARMI (plan 08)
| Tool | Status | Verdict |
|---|---|---|
| [ARMI](https://github.com/terrapower/armi) | 0.6.4 (2026-03), pushed 2026-09; very active; Apache-2.0; not on PyPI | **Watch.** Plan 08 unchanged |
| [armicontrib-openmc](https://github.com/terrapower/armicontrib-openmc) | **Exists.** Apache-2.0, **only 4 commits, last push 2025-09-24**; hex or Cartesian; "only supports a subset of OpenMC geometries" | Plan 08's first question is answered: a plugin exists, but it's thin and probably behind current ARMI. The likely path is to **update or extend it rather than write a new one**, and to offer the fixes upstream |

### Model conversion (only for MCNP cross-checks)
| Tool | Status | Verdict |
|---|---|---|
| [openmc_mcnp_adapter](https://github.com/openmc-dev/openmc_mcnp_adapter) | Active (2026-09), MIT; geometry and materials only; "no methodical V&V" | **Ref.** Direction is MCNP → OpenMC. Useful if a published MCNP JSI deck appears |
| [openmc_serpent_adapter](https://github.com/openmc-dev/openmc_serpent_adapter) | Active, MIT | **Ref.** Same idea for Serpent decks (JSI publishes Serpent work too) |
| [csg2csg](https://github.com/makeclean/csg2csg) | Last push 2025-05, EUPL-1.2 | **Watch** |
| [MontePy](https://github.com/idaholab/MontePy) | 1.5.0 on PyPI vs 1.1.3 installed | Not needed here. **For Studio:** check whether 1.5 parses `<` chains |

---

## 5. Existing simulators: what's already out there

**This changes the gap analysis in PLAN.md. JSI already has its own TRIGA simulator.**

| Simulator | What it is | How we differ |
|---|---|---|
| **JSI Research Reactor Simulator** ([reactorsimulator.ijs.si](https://reactorsimulator.ijs.si/)) | By JSI, for their own TRIGA. Point kinetics with a source, six groups, xenon, temperature feedback. **Windows desktop app** (C++, OpenGL). **Source on GitHub** (the EPFL [CROCUS fork](https://github.com/Matteo-Ale-Meneghini/CROCUS-simulator) is GPL-3.0, which suggests the original is GPL too; check). Explicitly not for thermal hydraulics or accidents | We're **browser-based**, **reactor-agnostic** (a library from any OpenMC model, not hand-coded for one reactor), and have a **3D core with real Monte Carlo power shapes**. **Use it as a validation cross-check** (same reactor, independent code), and don't copy GPL code into a permissively licensed project |
| [whatisnuclear/simulator](https://github.com/whatisnuclear/simulator) | **A design document only, no code** (README + MIT license, 3 commits 2019–2020). By Nick Touran (whatisnuclear.com). Browser simulator for several reactor types, never built past planning. Companion solver [partofthething/keepinpace](https://github.com/partofthething/keepinpace): Python point kinetics, MIT, 2019 | **Read for ideas:** its requirements (≤1 s response, phone to 50" screens, several reactor types) and its pointer to Sandia's 1984 TOPAZ 1-D transient code for thermal-hydraulics. It stalled partly on a server-side physics design; ours runs in the browser. Nothing to reuse except keepinpace (MIT) |
| [TH462/Reactor-Dynamics](https://github.com/TH462/Reactor-Dynamics) | Vanilla-JS browser power-plant simulator with six-group point kinetics; AGPL-3.0; very new (3★) | Hand-set parameters, no OpenMC link, no 3D core. Don't copy AGPL code |
| [OpenReactor](https://github.com/yasinldev/OpenReactor) | Claims point and spatial kinetics; 0★, dormant since 2024 | Ignore |
| IAEA PC-based simulators, commercial full-scope | Closed | — |

**Updated gap statement:** point-kinetics simulators, including one for this exact reactor, already exist.
What doesn't exist, as far as this survey found, is an **open, browser-based tool that takes any OpenMC model and produces a live, operable reactor with a 3D core showing transport-computed power shapes.**
The library format and the OpenMC → library pipeline are the new parts. The kinetics solver isn't.

---

## 6. Upgrade, reuse and build candidates

Ranked by value to this project.

1. **Reuse Studio's WebGL2 BVH CSG ray tracer (reuse, later).** It's already current: WebGL2, BVH, 10,000+ parts.
   **Primitives come first** (plan 04); CSG reuse is evaluated at a later gate, behind the geometry adapter.
   At that gate choose either a versioned shared module or a deliberately vendored snapshot. A snapshot records the Studio commit, local changes,
   notices, and how upstream fixes get evaluated (tech-debt TD-07).
2. **Dedicated `openmc-vr` env with OpenMC 0.16 (upgrade).** Keeps the shared env stable. Re-run the benchmark check on 0.16 and record any change in k.
3. **Stay on WebGL2 (three.js `WebGLRenderer`), not WebGPU.** That keeps Studio's GLSL reusable. Porting to TSL would only be worth it for a WebGPU-only feature.
4. **armicontrib-openmc (reuse and upgrade).** Update it for current ARMI instead of writing a plugin from scratch. That's also a visible upstream contribution.
5. **JSI TRIGA model contributed to `mit-crpg/benchmarks` (build, give back).** The ICSBEP model we must write anyway is missing from the main public OpenMC benchmark set.
6. **Pulse database (reuse).** 493 measured pulses is far better validation data than anything digitized from figures. Ask about terms before shipping derived data.
7. **JSI's simulator as an independent comparison (reuse, as a reference only).** Same reactor, different code. Differences in the pulse or xenon behavior are worth understanding.
8. **TOML configs instead of YAML (alternative logic).** `tomllib` is in the stdlib, so there's one less dependency in a shared env.
9. **MontePy 1.1.3 → 1.5.0 (upgrade; Studio, not this project).** Check whether the `<` tally-chain parsing gap is fixed.
10. **MCNPy's slow py4j bridge and wrong lattices (Studio, not this project).** Watch openmc_mcnp_adapter and csg2csg for an OpenMC → MCNP path. Nothing clearly better exists yet.

---

## 7. How to refresh this survey

```bash
# repo activity and license (Windows git-bash, gh authenticated)
gh api repos/OWNER/REPO --jq '"\(.full_name) ★\(.stargazers_count) pushed \(.pushed_at[:10]) license=\(.license.spdx_id // "none")"'
# latest PyPI version
curl -s https://pypi.org/pypi/PACKAGE/json | python -c "import json,sys;print(json.load(sys.stdin)['info']['version'])"
```

The WSL environment check script is described in the `messages/virtual-reactor.md` entry for 2026-09-25.
Good starting points for new tools: [openmc-dev/openmc-ecosystem](https://github.com/openmc-dev/openmc-ecosystem) and [paulromano/awesome-nuclear](https://github.com/paulromano/awesome-nuclear).
