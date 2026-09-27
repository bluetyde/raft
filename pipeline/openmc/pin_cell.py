"""Standard JSI TRIGA fuel element in an equivalent unit cell: fuel temperature reactivity vs svajger2024 Table 2.

Open data only (pipeline/openmc/data/jsi_standard_fuel.json). The cell is a square with reflective sides whose area gives the
core-average water-to-fuel ratio of the JSI core (fuel and water volumes of core 133, svajger2024 section 4.2); axially infinite.
Only the fuel temperature changes (other materials at 294 K), as in the reference. The reference is a full-core model, so the
comparison target is the temperature difference of reactivity, not absolute k.

Nuclear data: ENDF/B-VIII.0 (OpenMC library). Nuclide data exist at 294/600/900 K only, so 400, 500, 700 and 800 K use OpenMC's
temperature interpolation (the reference used exactly broadened ENDF/B-VII.0 data); H and Zr in ZrH have S(a,b) data at
every temperature used here.

Run in the openmc-vr env (WSL):  python -m pipeline.openmc.pin_cell [--particles 40000 --batches 300 --out report.json]
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "pipeline" / "openmc" / "data" / "jsi_standard_fuel.json"


def cell_side(d: dict) -> float:
    r = d["radiiCm"]
    h = d["activeHeightCm"]["value"]
    c = d["coreAverageCell"]
    meat_per_element = math.pi * (r["fuel"] ** 2 - r["zrRod"] ** 2) * h
    elements = c["fuelVolumeCm3"] / meat_per_element
    water_area = c["waterVolumeCm3"] / elements / h
    return math.sqrt(water_area + math.pi * r["clad"] ** 2)


def build_model(d: dict, fuel_temp: float, particles: int, batches: int, inactive: int):
    import openmc

    fuel = openmc.Material(name="U-ZrH1.6", temperature=fuel_temp)
    for nuc, n in d["fuel"]["atomDensityPerBarnCm"].items():
        fuel.add_nuclide(nuc, n)
    fuel.set_density("sum")
    fuel.add_s_alpha_beta("c_H_in_ZrH")
    fuel.add_s_alpha_beta("c_Zr_in_ZrH")

    zr = openmc.Material(name="Zr rod", temperature=294.0)
    zr.add_element("Zr", 1.0)
    zr.set_density("g/cm3", d["zrRod"]["densityGPerCm3"])

    clad = openmc.Material(name="SS304", temperature=294.0)
    for el, w in d["cladding"]["weightFractions"].items():
        clad.add_element(el, w, percent_type="wo")
    clad.set_density("g/cm3", d["cladding"]["densityGPerCm3"])

    water = openmc.Material(name="water", temperature=294.0)
    water.add_nuclide("H1", 2.0)
    water.add_nuclide("O16", 1.0)
    water.set_density("g/cm3", d["water"]["densityGPerCm3"])
    water.add_s_alpha_beta("c_H_in_H2O")

    r = d["radiiCm"]
    s_zr, s_fuel, s_gap, s_clad = (openmc.ZCylinder(r=r[k]) for k in ("zrRod", "fuel", "gap", "clad"))
    a = cell_side(d) / 2.0
    box = openmc.model.RectangularPrism(2 * a, 2 * a, boundary_type="reflective")
    zlo, zhi = openmc.ZPlane(-1.0, boundary_type="reflective"), openmc.ZPlane(1.0, boundary_type="reflective")
    ax = +zlo & -zhi
    cells = [openmc.Cell(fill=zr, region=-s_zr & ax), openmc.Cell(fill=fuel, region=+s_zr & -s_fuel & ax),
             openmc.Cell(fill=None, region=+s_fuel & -s_gap & ax), openmc.Cell(fill=clad, region=+s_gap & -s_clad & ax),
             openmc.Cell(fill=water, region=+s_clad & -box & ax)]
    model = openmc.model.Model(geometry=openmc.Geometry(cells), materials=openmc.Materials([fuel, zr, clad, water]))
    st = model.settings
    st.run_mode, st.particles, st.batches, st.inactive = "eigenvalue", particles, batches, inactive
    st.temperature = {"method": "interpolation", "default": 294.0}
    st.source = openmc.IndependentSource(space=openmc.stats.Box((-r["fuel"], -r["fuel"], -1), (r["fuel"], r["fuel"], 1)),
                                         constraints={"fissionable": True})
    st.output = {"summary": False}
    st.seed = 1
    return model


def run(temps, particles: int, batches: int, inactive: int) -> dict:
    import openmc

    d = json.loads(DATA.read_text(encoding="utf-8"))
    rows = []
    for T in temps:
        model = build_model(d, T, particles, batches, inactive)
        with tempfile.TemporaryDirectory() as tmp:
            sp = model.run(cwd=tmp, output=False)
            with openmc.StatePoint(sp) as p:
                k = p.keff
        rows.append({"T": T, "k": k.nominal_value, "kUnc": k.std_dev,
                     "rhoPcm": (k.nominal_value - 1.0) / k.nominal_value * 1e5, "rhoUncPcm": k.std_dev / k.nominal_value ** 2 * 1e5})
    ref = d["referenceAlpha"]
    ref_by_T = dict(zip(ref["temperaturesK"], ref["rhoPcm"]))
    base = rows[0]["rhoPcm"]
    for row in rows:
        row["dRhoPcm"] = row["rhoPcm"] - base
        if row["T"] in ref_by_T:
            row["refDRhoPcm"] = ref_by_T[row["T"]] - ref_by_T[temps[0]]
    return {"cellSideCm": cell_side(d), "particles": particles, "batches": batches, "inactive": inactive,
            "openmc": openmc.__version__, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--temps", type=float, nargs="+", default=[294.0, 400.0, 500.0, 600.0, 700.0, 800.0])
    ap.add_argument("--particles", type=int, default=40000)
    ap.add_argument("--batches", type=int, default=300)
    ap.add_argument("--inactive", type=int, default=50)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "pipeline" / "openmc" / "pin_cell_report.json")
    a = ap.parse_args(argv)
    rep = run(a.temps, a.particles, a.batches, a.inactive)
    a.out.write_bytes((json.dumps(rep, indent=1) + "\n").encode("utf-8"))
    print(f"cell side {rep['cellSideCm']:.4f} cm")
    for row in rep["rows"]:
        print(f"T {row['T']:6.1f} K  k {row['k']:.5f} +- {row['kUnc']:.5f}  d-rho {row['dRhoPcm']:8.1f} pcm  ref {row.get('refDRhoPcm', float('nan')):8.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
