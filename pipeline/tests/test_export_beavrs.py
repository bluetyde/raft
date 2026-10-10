"""export_beavrs on a planted separable model: the library must reproduce the planted reactivity and shapes, and deliberate breaks must be seen.

The planted sweep has the real core layout (193 assemblies, mesh order z, y, x with x fastest, y up) but invented physics: every bank has a linear
worth, temperatures and boron have linear slopes, and every shape change is a known zero-sum pattern times the same linear function.
"""
from __future__ import annotations

import copy
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

from physics_ref.engine import Engine
from physics_ref.library import Library
from pipeline.library import export_beavrs as xb
from pipeline.library.validate import validate_library
from pipeline.openmc.beavrs_cases import sweep_cases

CORE = json.loads(xb.CORE.read_text(encoding="utf-8"))
NXY = 19 * 19
T_REF, B_REF = 566.483, 975.0
RHO0 = 0.001
W = {"A": 0.0010, "B": 0.0030, "C": 0.0028, "D": 0.0026, "SA": 0.0022, "SB": 0.0031, "SC": 0.0016, "SD": 0.0018, "SE": 0.0014}   # total worth per bank
FUEL_SLOPE, WATER_SLOPE, BORON_SLOPE = -2.0e-5, -1.5e-5, -1.2e-4
BETA = [0.00022, 0.00114, 0.00109, 0.00253, 0.00098, 0.00033]
REF_STEPS = {b: (213 if b == "D" else 228) for b in xb.BANKS}


def pattern(seed: int) -> list[float]:
    """A zero-sum, asymmetric pattern over the 193 x 10 bins (element-major)."""
    n = len(CORE["assemblies"]) * xb.N_AXIAL
    v = [math.sin(0.37 * (i + 1) * seed) + 0.3 * math.cos(0.011 * i * seed * seed) for i in range(n)]
    m = math.fsum(v) / n
    return [a - m for a in v]


PATTERNS = {b: pattern(i + 2) for i, b in enumerate(xb.BANKS)}
PATTERNS["TF"] = pattern(13)
BASE_RAW = [1.0 + 0.5 * a["x"] / 18 + 0.3 * a["y"] / 18 + 0.05 * z for a in CORE["assemblies"] for z in range(xb.N_AXIAL)]   # not symmetric in x and y
SCALE = 2.0e-3      # pattern amplitude relative to a mean bin


def x_frac(steps: int) -> float:
    return steps / 228.0


def planted_rho(steps, boron, t_fuel, t_water, interaction=0.0) -> float:
    rho = RHO0 + sum(W[b] * (x_frac(steps[b]) - x_frac(REF_STEPS[b])) for b in xb.BANKS)
    rho += FUEL_SLOPE * ((t_fuel if t_fuel is not None else T_REF) - T_REF) + WATER_SLOPE * ((t_water if t_water is not None else T_REF) - T_REF)
    rho += BORON_SLOPE * (boron - B_REF)
    inserted = sum(1 for b in xb.BANKS if steps[b] < REF_STEPS[b] - 100)
    return rho + interaction * max(0, inserted - 1)


def planted_units(steps, t_fuel) -> list[float]:
    """Unnormalized bins: BASE_RAW plus zero-sum patterns, so the normalization is the same constant in every case."""
    u = list(BASE_RAW)
    for b in xb.BANKS:
        c = SCALE * (x_frac(steps[b]) - x_frac(REF_STEPS[b]))
        u = [a + c * p for a, p in zip(u, PATTERNS[b])]
    if t_fuel is not None:
        c = SCALE * (t_fuel - T_REF) / 100.0
        u = [a + c * p for a, p in zip(u, PATTERNS["TF"])]
    return u


def mesh(units: list[float], core: dict, scale: float) -> list[float]:
    vec = [0.0] * (xb.N_AXIAL * NXY)
    for e, a in enumerate(core["assemblies"]):
        for z in range(xb.N_AXIAL):
            vec[z * NXY + a["y"] * 19 + a["x"]] = units[e * xb.N_AXIAL + z] * scale
    return vec


def make_rows(interaction=0.0) -> list[dict]:
    rows = []
    for name, c in sweep_cases().items():                  # exactly the plan the real sweep ran
        steps, boron, tf, tw = c["steps"], c["boron"], c["tFuel"], c["tWater"]
        rho = planted_rho(steps, boron, tf, tw, interaction)
        units = planted_units(steps, tf)
        rows.append({"case": name, "role": c["role"], **{k: c[k] for k in ("particles", "batches", "inactive", "ifp")}, "steps": steps, "boron": boron, "tFuel": tf, "tWater": tw, "k": 1.0 / (1.0 - rho), "kStd": 2.5e-4,
                     "fission": mesh(units, CORE, 1e-3), "fissionStd": mesh([0.01 * u for u in BASE_RAW], CORE, 1e-3), "betaGroups": BETA,
                     "betaGroupsStd": [1e-5] * 6, "lambdaS": 2.9e-5, "lambdaStdS": 4e-8, "openmc": "0.15.3"})
    return rows


def evaluate(folder: Path, interaction=0.0, ids: dict[str, str] | None = None) -> tuple[float, float]:
    """(largest reactivity error, largest base-shape error) of a written library against the planted model at several states."""
    lib = Library(folder)
    worst = 0.0
    states = [(dict(REF_STEPS), B_REF, T_REF, T_REF), ({**REF_STEPS, "B": 0, "SA": 100}, 1200.0, 640.0, 600.0), ({**REF_STEPS, "D": 100, "C": 60, "SE": 200}, 700.0, 520.0, 540.0),
              ({**REF_STEPS, "A": 150}, 400.0, 800.0, 600.0), ({b: 0 for b in xb.BANKS}, 1500.0, 566.483, 566.483)]
    for steps, boron, tf, tc in states:
        init = {"rods": {(ids or {}).get(b, b.lower()): x_frac(s) for b, s in steps.items()}, "boron": boron, "Tfuel": tf, "Tcoolant": tc,
                "power": {"mode": "given", "value": 1e-3}, "poisons": {"mode": "zero"}}
        e = Engine(lib, init)
        got = e.reactivity(0.0, e.y)["total"]
        want = planted_rho(steps, boron, tf, tc) if interaction == 0.0 else None
        # the planted tables are linear and the planted temperatures are inside the table axes: the model is exact there
        worst = max(worst, abs(got - want))
    return worst


def base_error(folder: Path, core: dict) -> float:
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    d = m["arrays"]["base"]
    raw = (folder / d["file"]).read_bytes()
    got = struct.unpack(f"<{len(raw) // 4}f", raw)
    units = planted_units(REF_STEPS, None)
    s = math.fsum(units)
    # the planted base, element order of the core file the library was written with
    want = [u / s for u in units]
    return max(abs(a - b) for a, b in zip(got, want)) * len(want)


class PlantedExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name) / "lib"
        cls.rows = make_rows()
        m, blobs, cls.report = xb.build(cls.rows, CORE, created="2026-10-10")
        cls.m = m
        xb.write_library(cls.folder, m, blobs)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_library_validates_and_has_the_boron_capability(self):
        self.assertEqual(validate_library(self.folder), [])
        self.assertIn("point-kinetics/boron-v1", self.m["capabilities"])
        self.assertEqual(sorted(r["id"] for r in self.m["reactivity"]["rods"]), sorted(b.lower() for b in xb.BANKS))
        self.assertAlmostEqual(self.m["reference"]["rods"]["d"], 213 / 228, places=11)

    def test_it_reproduces_the_planted_reactivity_at_several_states(self):
        self.assertLess(evaluate(self.folder), 1e-9)

    def test_it_reproduces_the_planted_base_shape_bin_by_bin(self):
        self.assertLess(base_error(self.folder, CORE), 1e-4)       # float32, in units of the mean bin

    def test_deltas_reproduce_a_planted_shape_at_a_case(self):
        # a joint case is separable in the planted model, so the stored prediction error is float32 rounding only
        for j in self.m["domain"]["jointChecked"]:
            self.assertLess(j["maxShapeErr"], 1e-3)
            self.assertLess(j["rhoErr"], 1e-9)
        self.assertEqual(len(self.m["domain"]["jointChecked"]), 3)

    def test_a_planted_interaction_between_banks_is_reported_not_hidden(self):
        rows = make_rows(interaction=-4.0e-4)
        _, _, report = xb.build(rows, CORE, created="2026-10-10")
        err = {c: report["cases"][c]["rhoErr"] for c in xb.JOINT_RHO}
        self.assertAlmostEqual(err["J-W2"], 4.0e-4, places=9)         # two banks in: one interaction unit
        self.assertAlmostEqual(err["J-W4"], 3 * 4.0e-4, places=9)
        self.assertAlmostEqual(err["J-W7"], 6 * 4.0e-4, places=9)
        self.assertAlmostEqual(report["boronSeparability"]["J-B7"]["rhoErr"], 6 * 4.0e-4, places=9)

    def test_the_reference_has_no_calibration_and_the_boron_axis_holds_the_domain(self):
        self.assertIsNone(self.m["reference"]["calibration"])
        self.assertEqual(self.m["domain"]["boron"], [300.0, 1600.0])
        self.assertEqual(self.m["reactivity"]["boron"]["C"], [300.0, 600.0, 975.0, 1300.0, 1600.0])

    # ---- deliberate breaks: the checks above must fail when the exporter is wrong
    def test_break_a_transposed_mesh_index_is_caught(self):
        core = copy.deepcopy(CORE)
        for a in core["assemblies"]:
            a["x"], a["y"] = a["y"], a["x"]
        with tempfile.TemporaryDirectory() as d:
            m, blobs, _ = xb.build(self.rows, core, created="2026-10-10")
            xb.write_library(Path(d) / "lib", m, blobs)
            self.assertGreater(base_error(Path(d) / "lib", CORE), 1e-2)

    def test_break_a_flipped_y_axis_is_caught(self):
        core = copy.deepcopy(CORE)
        for a in core["assemblies"]:
            a["y"] = 18 - a["y"]
        with tempfile.TemporaryDirectory() as d:
            m, blobs, _ = xb.build(self.rows, core, created="2026-10-10")
            xb.write_library(Path(d) / "lib", m, blobs)
            self.assertGreater(base_error(Path(d) / "lib", CORE), 1e-2)

    def test_break_a_sign_error_in_the_boron_table_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            m = copy.deepcopy(self.m)
            m["reactivity"]["boron"]["rho"] = [-v for v in m["reactivity"]["boron"]["rho"]]
            m["reactivity"]["boron"]["unc"] = m["reactivity"]["boron"]["unc"]
            folder = Path(d) / "lib"
            xb.write_library(folder, m, {f"arrays/{n}.f32": (self.folder / f"arrays/{n}.f32").read_bytes() for n in self.m["arrays"]})
            self.assertGreater(evaluate(folder), 1e-4)

    def test_break_a_bank_on_the_wrong_rod_id_is_caught(self):
        swapped = {"a": "b", "b": "a"}
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, self.m, {f"arrays/{n}.f32": (self.folder / f"arrays/{n}.f32").read_bytes() for n in self.m["arrays"]})
            self.assertGreater(evaluate(folder, ids={b.upper(): swapped.get(b, b) for b in ("a", "b")} | {b.upper(): b for b in ("c", "d", "sa", "sb", "sc", "sd", "se")}), 1e-4)

    def test_the_joint_states_are_listed_only_if_the_summed_model_reproduces_them(self):
        self.assertEqual(len(self.m["domain"]["jointChecked"]), 3)
        m, _, report = xb.build(make_rows(interaction=-4.0e-4), CORE, created="2026-10-10")
        self.assertEqual([j["rods"]["c"] for j in m["domain"]["jointChecked"]], [0.0])        # only J-W2 (error 4e-4, under 1e-3) is kept
        self.assertTrue(report["cases"]["J-W2"]["inJointChecked"])
        self.assertFalse(report["cases"]["J-W4"]["inJointChecked"])                            # 1.2e-3
        self.assertFalse(report["cases"]["J-W7"]["inJointChecked"])                            # 2.4e-3

    def test_a_duplicate_case_is_refused(self):
        with self.assertRaises(ValueError):
            xb.build(self.rows + [copy.deepcopy(self.rows[0])], CORE)

    def test_a_case_recorded_with_other_settings_than_planned_is_refused(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r["case"] == "B-300")["boron"] = 600.0
        with self.assertRaises(ValueError):
            xb.build(rows, CORE)

    def test_a_sweep_run_at_other_settings_than_planned_is_refused(self):
        for key, bad in (("particles", 4000), ("batches", 30), ("inactive", 5), ("ifp", False)):
            rows = copy.deepcopy(self.rows)
            next(r for r in rows if r["case"] == "REF")[key] = bad
            with self.assertRaises(ValueError, msg=key):
                xb.build(rows, CORE)

    def test_an_invalid_new_library_leaves_the_old_one_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, self.m, {f"arrays/{n}.f32": (self.folder / f"arrays/{n}.f32").read_bytes() for n in self.m["arrays"]}, validate=True)
            before = (folder / "manifest.json").read_bytes()
            bad = copy.deepcopy(self.m)
            bad["reactivity"]["boron"]["rho"][2] = 1.0e-3                         # not zero at the reference
            with self.assertRaises(ValueError):
                xb.write_library(folder, bad, {f"arrays/{n}.f32": (self.folder / f"arrays/{n}.f32").read_bytes() for n in self.m["arrays"]}, validate=True)
            self.assertEqual((folder / "manifest.json").read_bytes(), before)
            self.assertFalse((Path(d) / "lib.new").exists())

    def test_a_missing_case_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            xb.build([r for r in self.rows if r["case"] != "TC-600"], CORE)

    def test_a_wrong_reference_configuration_is_refused(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["steps"]["D"] = 228
        with self.assertRaises(ValueError):
            xb.build(rows, CORE)


if __name__ == "__main__":
    unittest.main()
