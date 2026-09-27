"""Full-core OpenMC model of a JSI TRIGA Mark II core configuration, from open data only.

Inputs: pipeline/openmc/data/jsi_standard_fuel.json (fuel element, materials), jsi_core_geometry.json (grid, reflector, rods,
steps), jsi_core_occupancy.json (which position holds what, from the database core maps). Fuel is fresh by default (per-element
burnup is not in the open sources); `--burnup B` gives every fuel region one burnup from jsi_fuel_depleted.json (pin_depletion.py),
a calibration parameter (docs/validation/m2-burnup-protocol.md). Also: `--kinetics` (beta_eff, Lambda by IFP), `--prompt`,
`--b4c` / `--graphite` density sensitivities, `--json` results.

Simplifications, all labelled `assumed` (no open JSI value found):
- B4C 2.48 g/cm3; reflector graphite 1.6 g/cm3 (as the element end plugs); aluminum 2.7 g/cm3;
- element end fittings, grid plates, irradiation channels (CK, OK, PP, NI, TOK) and empty positions are water;
- the reflector is centred on the fuel midplane and its rotary-rack groove is a void at the top; beam ports are omitted.

Rod positions in steps: fuel-followed rods 200 (up) ... 900 (down), transient 0 (up) ... 900 (down), 0.05443 cm/step
(jsi_core_geometry.json controlRods.stepCm). At 900 steps the absorber's lower end is at the bottom of the fuel (-19.05 cm).

Run in the openmc-vr env (WSL):  python -m pipeline.openmc.core_model --core 242 --rods T=0,K=499,V=200,R=500
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "pipeline" / "openmc" / "data"
IN = 2.54
HALF_FUEL = 19.05
STEP_CM = 38.1 / 700.0
RINGS = {"A": 1, "B": 6, "C": 12, "D": 18, "E": 24, "F": 30}
ROD_AT = {"T": "C4", "V": "C10", "K": "D10", "R": "D1"}
ZMIN, ZMAX = -80.0, 80.0
IFP_GENERATIONS = 10                               # IFP chain length; must not exceed the inactive batches


def position_xy(label: str, ring_radius: dict) -> tuple[float, float]:
    ring, k = label[0], int(label[1:])
    r = ring_radius[ring]
    th = math.radians(-90.0 - (k - 1) * 360.0 / RINGS[ring])
    return r * math.cos(th), r * math.sin(th)


def absorber_bottom(rod: str, steps: float) -> float:
    return -HALF_FUEL + (900.0 - steps) * STEP_CM


def burned_fuel(burnup: float) -> dict[str, float]:
    """Fuel atom densities at `burnup` MWd/kg, linear between the steps of jsi_fuel_depleted.json (pin_depletion.py), restricted to
    nuclides with transport data in the cross-section library."""
    import openmc.data
    table = json.loads((DATA / "jsi_fuel_depleted.json").read_text(encoding="utf-8"))["steps"]
    bus = [r["burnupMWdPerKg"] for r in table]
    if not bus[0] <= burnup <= bus[-1]:
        raise ValueError(f"burnup {burnup} outside the table ({bus[0]}..{bus[-1]} MWd/kg)")
    i = max(j for j, b in enumerate(bus) if b <= burnup)
    j = min(i + 1, len(bus) - 1)
    w = 0.0 if j == i else (burnup - bus[i]) / (bus[j] - bus[i])
    a, b = table[i]["atomDensityPerBarnCm"], table[j]["atomDensityPerBarnCm"]
    lib = {name for m in openmc.data.DataLibrary.from_xml().libraries if m["type"] == "neutron" for name in m["materials"]}
    return {n: (1 - w) * a.get(n, 0.0) + w * b.get(n, 0.0) for n in set(a) | set(b) if n in lib}


def materials(fuel_data: dict, ov: dict | None = None):
    """`ov` overrides assumed values for sensitivity runs: b4c (g/cm3), graphite (g/cm3), burnup (MWd/kg, every fuel region)."""
    import openmc
    ov = ov or {}
    m = {}
    fuel = openmc.Material(name="U-ZrH1.6")
    comp = burned_fuel(ov["burnup"]) if "burnup" in ov else fuel_data["fuel"]["atomDensityPerBarnCm"]
    for nuc, n in comp.items():
        fuel.add_nuclide(nuc, n)
    fuel.set_density("sum")
    fuel.add_s_alpha_beta("c_H_in_ZrH")
    fuel.add_s_alpha_beta("c_Zr_in_ZrH")
    m["fuel"] = fuel
    zr = openmc.Material(name="Zr"); zr.add_element("Zr", 1.0); zr.set_density("g/cm3", 6.49); m["zr"] = zr
    ss = openmc.Material(name="SS304")
    for el, w in fuel_data["cladding"]["weightFractions"].items():
        ss.add_element(el, w, percent_type="wo")
    ss.set_density("g/cm3", fuel_data["cladding"]["densityGPerCm3"]); m["ss"] = ss
    water = openmc.Material(name="water"); water.add_nuclide("H1", 2.0); water.add_nuclide("O16", 1.0)
    water.set_density("g/cm3", fuel_data["water"]["densityGPerCm3"]); water.add_s_alpha_beta("c_H_in_H2O"); m["water"] = water
    gr = openmc.Material(name="graphite"); gr.add_element("C", 1.0); gr.set_density("g/cm3", ov.get("graphite", 1.6))   # assumed for the reflector
    gr.add_s_alpha_beta("c_Graphite"); m["graphite"] = gr
    mo = openmc.Material(name="Mo"); mo.add_element("Mo", 1.0); mo.set_density("g/cm3", 10.2); m["mo"] = mo
    al = openmc.Material(name="Al"); al.add_element("Al", 1.0); al.set_density("g/cm3", 2.7); m["al"] = al   # assumed
    b4c = openmc.Material(name="B4C"); b4c.add_element("B", 4.0); b4c.add_element("C", 1.0)
    b4c.set_density("g/cm3", ov.get("b4c", 2.48)); m["b4c"] = b4c                                                       # assumed
    return m


def layered_cells(x, y, r_pos, layers, fill_default, zbounds):
    """Cells for one grid position: `layers` is a list of (z_lo, z_hi, [(r_outer, material or None), ...]) from the axis out;
    everything else inside the position cylinder is `fill_default`."""
    import openmc
    pos = openmc.ZCylinder(x0=x, y0=y, r=r_pos)
    zlo_s, zhi_s = zbounds
    cells, covered = [], []
    for zlo, zhi, rings in layers:
        zl, zh = openmc.ZPlane(zlo), openmc.ZPlane(zhi)
        slab = +zl & -zh
        inner = None
        for r_out, mat in rings:
            cyl = openmc.ZCylinder(x0=x, y0=y, r=r_out)
            reg = slab & -cyl if inner is None else slab & +inner & -cyl
            cells.append(openmc.Cell(fill=mat, region=reg))
            inner = cyl
        cells.append(openmc.Cell(fill=fill_default, region=slab & +inner & -pos))
        covered.append(slab)
    rest = -pos & +zlo_s & -zhi_s
    for c in covered:
        rest = rest & ~c
    cells.append(openmc.Cell(fill=fill_default, region=rest))
    return pos, cells


def build(core: str, rods: dict[str, float], particles: int, batches: int, inactive: int, source_from: Path | None = None,
          kinetics: bool = False, prompt_only: bool = False, overrides: dict | None = None):
    import openmc
    fd = json.loads((DATA / "jsi_standard_fuel.json").read_text(encoding="utf-8"))
    geo = json.loads((DATA / "jsi_core_geometry.json").read_text(encoding="utf-8"))
    occ = json.loads((DATA / "jsi_core_occupancy.json").read_text(encoding="utf-8"))["cores"][core]
    ov = overrides or {}
    M = materials(fd, ov)
    rr = geo["grid"]["ringRadiiCm"]
    rad = fd["radiiCm"]
    zb_s, zt_s = openmc.ZPlane(ZMIN, boundary_type="vacuum"), openmc.ZPlane(ZMAX, boundary_type="vacuum")
    r_pos = 1.905                                      # position cylinder: the largest object (transient guide tube, 1.5 in)
    fe = geo["fuelElement"]
    g_up, g_lo, mo_t = fe["graphiteUpperIn"] * IN, fe["graphiteLowerIn"] * IN, fe["moDiscIn"] * IN

    def fuel_element_layers():
        clad = (rad["clad"], M["ss"])
        return [
            (-HALF_FUEL, HALF_FUEL, [(rad["zrRod"], M["zr"]), (rad["fuel"], M["fuel"]), (rad["gap"], None), clad]),
            (HALF_FUEL, HALF_FUEL + g_up, [(rad["fuel"], M["graphite"]), (rad["gap"], None), clad]),
            (-HALF_FUEL - mo_t, -HALF_FUEL, [(rad["fuel"], M["mo"]), (rad["gap"], None), clad]),
            (-HALF_FUEL - mo_t - g_lo, -HALF_FUEL - mo_t, [(rad["fuel"], M["graphite"]), (rad["gap"], None), clad]),
        ]

    def ffcr_layers(steps):
        c = geo["controlRods"]["fueledFollower"]
        r_out = c["outerDiameterIn"] * IN / 2
        r_in = r_out - c["cladIn"] * IN
        r_abs = c["absorber"]["diameterIn"] * IN / 2
        zb = absorber_bottom("ffcr", steps)
        L = c["absorber"]["lengthIn"] * IN
        clad = (r_out, M["ss"])
        return [
            (zb, zb + L, [(r_abs, M["b4c"]), (r_in, None), clad]),
            (zb + L, zb + L + c["voidsIn"]["top"] * IN, [(r_in, None), clad]),
            (zb - L, zb, [(rad["zrRod"], M["zr"]), (r_abs, M["fuel"]), (r_in, None), clad]),
            (zb - L - c["voidsIn"]["bottom"] * IN, zb - L, [(r_in, None), clad]),
        ]

    def transient_layers(steps):
        c = geo["controlRods"]["transient"]
        r_out = c["outerDiameterIn"] * IN / 2
        r_in = r_out - c["cladIn"] * IN
        r_abs = c["absorber"]["diameterIn"] * IN / 2
        g_out = c["guideTube"]["outerDiameterIn"] * IN / 2
        g_in = g_out - c["guideTube"]["thicknessMm"] / 10.0
        zb = absorber_bottom("T", steps)
        L = c["absorber"]["lengthIn"] * IN
        af = c["airFollower"]["heightIn"] * IN
        clad = (r_out, M["al"])
        guide = [(g_in, M["water"]), (g_out, M["al"])]
        # the guide tube runs the full core height; the rod moves inside it
        return [(ZMIN + 1e-6, zb - af, [(g_in, M["water"]), (g_out, M["al"])]),
                (zb - af, zb, [(r_in, None), clad] + guide),
                (zb, zb + L, [(r_abs, M["b4c"]), (r_in, None), clad] + guide),
                (zb + L, ZMAX - 1e-6, [(g_in, M["water"]), (g_out, M["al"])])]

    cells, pos_cyls = [], []
    for ring, n in RINGS.items():
        for k in range(1, n + 1):
            lab = f"{ring}{k}"
            x, y = position_xy(lab, rr)
            what = occ["fuel"].get(lab) and "fuel" or occ["other"].get(lab)
            rod = next((rid for rid, p in ROD_AT.items() if p == lab), None)
            if rod == "T":
                layers = transient_layers(rods["T"])
            elif rod is not None:
                layers = ffcr_layers(rods[rod])
            elif what == "fuel":
                layers = fuel_element_layers()
            else:
                layers = []                       # channels and empty positions: water (assumed)
            cyl, pc = layered_cells(x, y, r_pos, layers, M["water"], (zb_s, zt_s))
            pos_cyls.append(cyl)
            cells += pc

    # core water, reflector, pool
    ref = geo["reflector"]
    r_core = 22.098
    r_gi = ref["graphiteInnerDiameterIn"] * IN / 2
    r_go = ref["graphiteOuterDiameterIn"] * IN / 2
    r_ao = r_go + ref["aluminumCladIn"]["outerBottom"] * IN
    h = ref["heightIn"] * IN / 2
    t_top, t_bot = ref["aluminumCladIn"]["innerTop"] * IN, ref["aluminumCladIn"]["outerBottom"] * IN
    g = ref["rotaryRackGroove"]
    gr_i, gr_o, gr_h = g["innerDiameterIn"] * IN / 2, g["outerDiameterIn"] * IN / 2, g["heightIn"] * IN
    c_core = openmc.ZCylinder(r=r_core)
    c_gi, c_go, c_ao = openmc.ZCylinder(r=r_gi), openmc.ZCylinder(r=r_go), openmc.ZCylinder(r=r_ao)
    c_ri, c_ro = openmc.ZCylinder(r=gr_i), openmc.ZCylinder(r=gr_o)
    z_gb, z_gt = openmc.ZPlane(-h), openmc.ZPlane(h)
    z_ab, z_at = openmc.ZPlane(-h - t_bot), openmc.ZPlane(h + t_top)
    z_grv = openmc.ZPlane(h - gr_h)
    pool = openmc.ZCylinder(r=100.0, boundary_type="vacuum")
    zrange = +zb_s & -zt_s
    core_water = -c_core & zrange
    for cyl in pos_cyls:
        core_water = core_water & +cyl
    cells.append(openmc.Cell(fill=M["water"], region=core_water))
    graphite = +c_gi & -c_go & +z_gb & -z_gt & ~(+c_ri & -c_ro & +z_grv & -z_gt)
    cells.append(openmc.Cell(fill=M["graphite"], region=graphite))
    cells.append(openmc.Cell(fill=None, region=+c_ri & -c_ro & +z_grv & -z_gt))            # rotary-rack groove (void)
    casing = (+c_core & -c_ao & +z_ab & -z_at) & ~(+c_gi & -c_go & +z_gb & -z_gt)
    cells.append(openmc.Cell(fill=M["al"], region=casing))
    outside = -pool & zrange & ~(-c_core & zrange) & ~(+c_core & -c_ao & +z_ab & -z_at)
    cells.append(openmc.Cell(fill=M["water"], region=outside))

    model = openmc.model.Model(geometry=openmc.Geometry(cells), materials=openmc.Materials(M.values()))
    st = model.settings
    st.run_mode, st.particles, st.batches, st.inactive = "eigenvalue", particles, batches, inactive
    if source_from is not None:
        # start from a converged fission source of a similar state (e.g. the previous rod position), so fewer inactive batches are needed
        st.source = openmc.FileSource(str(source_from))
    else:
        st.source = openmc.IndependentSource(space=openmc.stats.Box((-20, -20, -19), (20, 20, 19)), constraints={"fissionable": True})
    st.sourcepoint = {"separate": True}
    st.output = {"summary": False}
    st.seed = 1
    if prompt_only:
        st.create_delayed_neutrons = False          # prompt method: beta_eff = 1 - k_prompt / k
    if kinetics:
        # iterated fission probability (IFP): beta_eff per group and the generation time Lambda, from the same run
        st.ifp_n_generation = IFP_GENERATIONS
        model.add_kinetics_parameters_tallies(num_groups=6)
    return model


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--core", default="242")
    ap.add_argument("--rods", default="T=0,K=499,V=200,R=500", help="steps per rod, e.g. T=0,K=499,V=200,R=500")
    ap.add_argument("--particles", type=int, default=20000)
    ap.add_argument("--batches", type=int, default=150)
    ap.add_argument("--inactive", type=int, default=50)
    ap.add_argument("--plot", type=Path, default=None, help="write xy and xz geometry plots here instead of running")
    ap.add_argument("--quick", action="store_true",
                    help="testing only: 4000 particles x 60 batches (20 inactive), about 10x faster, about 3x the statistical error")
    ap.add_argument("--source-from", type=Path, default=None, help="source.h5 from an earlier run; inactive batches default to 10")
    ap.add_argument("--save-source", type=Path, default=None, help="copy this run's final fission source (source.h5) here")
    ap.add_argument("--kinetics", action="store_true", help="also tally beta_eff (6 groups) and Lambda by IFP")
    ap.add_argument("--prompt", action="store_true", help="no delayed neutrons (prompt method: beta_eff = 1 - k_p/k)")
    ap.add_argument("--b4c", type=float, default=None, help="sensitivity: B4C density, g/cm3 (assumed 2.48)")
    ap.add_argument("--graphite", type=float, default=None, help="sensitivity: graphite density, g/cm3 (assumed 1.6)")
    ap.add_argument("--burnup", type=float, default=None,
                    help="calibration: give every fuel region this burnup, MWd/kg (default fresh); see docs/validation/m2-burnup.md")
    ap.add_argument("--json", type=Path, default=None, help="append the result as one JSON line to this file")
    a = ap.parse_args(argv)
    if a.quick:
        a.particles, a.batches, a.inactive = 4000, 60, 20
    if a.source_from is not None and "--inactive" not in (argv or __import__("sys").argv):
        active = a.batches - a.inactive          # keep the same number of active batches; only the warm-up shrinks
        a.inactive = 10
        a.batches = a.inactive + active
    rods = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.rods.split(",")}
    overrides = {k: v for k, v in (("b4c", a.b4c), ("graphite", a.graphite), ("burnup", a.burnup)) if v is not None}
    if a.kinetics and a.inactive < IFP_GENERATIONS:
        ap.error(f"--kinetics needs at least {IFP_GENERATIONS} inactive batches")
    model = build(a.core, rods, a.particles, a.batches, a.inactive, a.source_from,
                  kinetics=a.kinetics, prompt_only=a.prompt, overrides=overrides)
    import openmc
    if a.plot:
        a.plot.mkdir(parents=True, exist_ok=True)
        model.geometry.export_to_xml(a.plot / "geometry.xml")
        for basis, name in (("xy", "xy"), ("xz", "xz")):
            p = openmc.Plot(); p.basis = basis; p.width = (120, 120) if basis == "xy" else (120, 120)
            p.pixels = (800, 800); p.color_by = "material"; p.filename = str(a.plot / name)
            model.plots = openmc.Plots([p]); model.plot_geometry(cwd=a.plot, output=False)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        sp = model.run(cwd=tmp, output=False)
        with openmc.StatePoint(sp) as sp_:
            k = sp_.keff
            kin = sp_.get_kinetics_parameters() if a.kinetics else None
        if a.save_source is not None:
            import shutil
            srcs = sorted(Path(tmp).glob("source*.h5"), key=lambda p: p.stat().st_mtime)   # OpenMC names it source.<batch>.h5
            if not srcs:
                raise FileNotFoundError(f"no source*.h5 written in {tmp}")
            shutil.copy(srcs[-1], a.save_source)
    rho = (k.nominal_value - 1) / k.nominal_value
    print(f"core {a.core} rods {rods}: k = {k.nominal_value:.5f} +- {k.std_dev:.5f}  (rho = {rho*1e5:.0f} pcm = ${rho/0.007:.2f})")
    out = {"core": a.core, "rods": rods, "overrides": overrides, "prompt": a.prompt, "particles": a.particles,
           "batches": a.batches, "inactive": a.inactive, "k": k.nominal_value, "kStd": k.std_dev}
    if kin is not None:
        groups = kin.beta_effective
        beta = sum(groups)
        lam = kin.generation_time
        print(f"  beta_eff = {beta.nominal_value*1e5:.1f} +- {beta.std_dev*1e5:.1f} pcm;  Lambda = {lam.nominal_value*1e6:.2f} +- {lam.std_dev*1e6:.2f} us")
        print("  groups (pcm): " + ", ".join(f"{g.nominal_value*1e5:.1f}" for g in groups))
        out.update(betaEff=beta.nominal_value, betaEffStd=beta.std_dev, betaGroups=[g.nominal_value for g in groups],
                   betaGroupsStd=[g.std_dev for g in groups], lambdaS=lam.nominal_value, lambdaStdS=lam.std_dev)
    if a.json is not None:
        with a.json.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
