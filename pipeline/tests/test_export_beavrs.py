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
from pipeline.openmc.beavrs_cases import near_cases, path_cases, shadow_cases, sweep_cases

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


def planted_sum(steps) -> float:
    """The planted sum of the single-bank reactivities relative to the reference."""
    return sum(W[b] * (x_frac(steps[b]) - x_frac(REF_STEPS[b])) for b in xb.BANKS)


S_DEEPEST = -max(W[b] * x_frac(REF_STEPS[b]) for b in xb.BANKS)      # the deepest single-bank worth, where the planted correction starts


def planted_c(s: float) -> float:
    """A planted correction that is a function of the summed worth only: zero down to the deepest single bank, then half the further sum."""
    return 0.5 * min(0.0, s - S_DEEPEST)


def planted_rho(steps, boron, t_fuel, t_water, interaction=0.0, correction=None, shadow=None) -> float:
    rho = RHO0 + planted_sum(steps)
    rho += FUEL_SLOPE * ((t_fuel if t_fuel is not None else T_REF) - T_REF) + WATER_SLOPE * ((t_water if t_water is not None else T_REF) - T_REF)
    rho += BORON_SLOPE * (boron - B_REF)
    inserted = sum(1 for b in xb.BANKS if steps[b] < REF_STEPS[b] - 100)
    if correction is not None:
        rho += correction(planted_sum(steps))
    if shadow is not None:
        ws = [W[b] * (x_frac(steps[b]) - x_frac(REF_STEPS[b])) for b in xb.BANKS]
        s = math.fsum(ws)
        rho += math.fsum(w * shadow(s - w) for w in ws if w != 0.0)
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


def make_rows(interaction=0.0, plan=None, correction=None, shadow=None) -> list[dict]:
    rows = []
    for name, c in (plan or sweep_cases()).items():       # exactly the plan the real sweep ran (or the path plan)
        steps, boron, tf, tw = c["steps"], c["boron"], c["tFuel"], c["tWater"]
        rho = planted_rho(steps, boron, tf, tw, interaction, correction, shadow)
        units = planted_units(steps, tf)
        rows.append({"case": name, "role": c["role"], **{k: c[k] for k in ("particles", "batches", "inactive", "ifp")}, "steps": steps, "boron": boron, "tFuel": tf, "tWater": tw, "k": 1.0 / (1.0 - rho), "kStd": 2.5e-4,
                     "kBatches": [1.0 / (1.0 - rho) + (0.001 if i % 2 else -0.001) for i in range(c["batches"])],
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

    # the deltas of the shapes and the joint states are covered by the path-case tests below

    def test_the_fitted_table_holds_the_planted_corrections_at_the_combined_states(self):
        m, _, report = xb.build(make_rows(interaction=-4.0e-4), CORE, created="2026-10-10")
        t = m["reactivity"]["rodInteraction"]
        want = {}
        for c, n_in in (("J-W2", 2), ("J-W4", 4), ("J-W7", 7)):
            want[round(planted_sum(sweep_cases()[c]["steps"]), 9)] = -4.0e-4 * (n_in - 1)
        got = {round(s, 9): r for s, r in zip(t["S"], t["rho"])}
        for s, r in want.items():
            self.assertAlmostEqual(got[s], r, places=12)
        self.assertEqual(got[0.0], 0.0)
        self.assertEqual(got[xb.S_ABOVE], 0.0)
        self.assertAlmostEqual(min(t["S"]), planted_sum(sweep_cases()["J-W7"]["steps"]), places=9)
        # fitted to these cases, so they are reproduced exactly, with and without a boron change (the planted interaction does not depend on boron)
        for c in ("J-W2", "J-W4", "J-W7", "J-B4", "J-B7"):
            self.assertLess(report["cases"][c]["rhoErr"], 1e-9, c)
        self.assertFalse(report["cases"]["J-W2"]["rhoErr"] > report["cases"]["J-W2"]["rhoSigma"])
        self.assertTrue(all(report["cases"][c]["usedInFit"] for c in xb.FIT_CASES))
        self.assertEqual(m["domain"]["jointChecked"], [])                       # the fit cases are never listed as checked, and no path cases were given

    def test_a_planted_nonseparable_sweep_is_recovered_by_the_table_between_its_nodes(self):
        rows = make_rows(correction=planted_c)
        m, blobs, _ = xb.build(rows, CORE, created="2026-10-10")
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, m, blobs, validate=True)
            lib = Library(folder)
            self.assertTrue(lib.has_rod_interaction)
            order = ["D", "C", "B", "A", "SE", "SD", "SC"]
            states = [{**REF_STEPS, "D": 0, "C": 0}, {**REF_STEPS, "D": 0, "C": 0, "B": 0}, {**REF_STEPS, **{b: 0 for b in order[:4]}},
                      {**REF_STEPS, "D": 0, "C": 0, "B": 0, "A": 76}, {**REF_STEPS, **{b: 0 for b in order[:6]}, "SC": 76},
                      {**REF_STEPS, "D": 0, "C": 100}, {**REF_STEPS, **{b: 0 for b in order}}]
            for steps in states:
                init = {"rods": {b.lower(): x_frac(s) for b, s in steps.items()}, "power": {"mode": "given", "value": 1e-3}, "poisons": {"mode": "zero"}}
                e = Engine(lib, init)
                self.assertAlmostEqual(e.reactivity(0.0, e.y)["total"], planted_rho(steps, B_REF, None, None, 0.0, planted_c), places=9, msg=str(steps))

    def test_break_a_sign_error_in_the_fitted_correction_is_caught(self):
        rows = make_rows(correction=planted_c)
        m, blobs, _ = xb.build(rows, CORE, created="2026-10-10")
        t = m["reactivity"]["rodInteraction"]
        t["rho"] = [-v for v in t["rho"]]
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, m, blobs)
            lib = Library(folder)
            steps = {**REF_STEPS, "D": 0, "C": 0, "B": 0, "A": 0}
            e = Engine(lib, {"rods": {b.lower(): x_frac(s) for b, s in steps.items()}, "power": {"mode": "given", "value": 1e-3}, "poisons": {"mode": "zero"}})
            self.assertGreater(abs(e.reactivity(0.0, e.y)["total"] - planted_rho(steps, B_REF, None, None, 0.0, planted_c)), 1e-4)

    def test_held_out_path_cases_are_labelled_and_only_the_good_ones_are_listed_as_checked(self):
        rows = make_rows(correction=planted_c)
        path = make_rows(correction=planted_c, plan=path_cases())
        m, _, report = xb.build(rows, CORE, created="2026-10-10", path_rows=path)
        self.assertEqual(len(report["pathCases"]), 9)
        self.assertTrue(all(v["label"] == "good" for v in report["pathCases"].values()))
        self.assertEqual(len(m["domain"]["jointChecked"]), 9)
        # one path case that the correction cannot know about (an effect that is not a function of the summed worth)
        bad = copy.deepcopy(path)
        r = next(x for x in bad if x["case"] == "P-SD-76")
        rho = (r["k"] - 1.0) / r["k"] + 3.0e-3
        r["k"] = 1.0 / (1.0 - rho)
        mid = copy.deepcopy(path)
        r2 = next(x for x in mid if x["case"] == "P-B-76")
        rho2 = (r2["k"] - 1.0) / r2["k"] + 1.5e-3
        r2["k"] = 1.0 / (1.0 - rho2)
        m2, _, report2 = xb.build(rows, CORE, created="2026-10-10", path_rows=bad + [x for x in mid if x["case"] == "P-B-76"][:0])
        self.assertEqual(report2["pathCases"]["P-SD-76"]["label"], "fails")
        self.assertEqual(len(m2["domain"]["jointChecked"]), 8)
        m3, _, report3 = xb.build(rows, CORE, created="2026-10-10", path_rows=mid)
        self.assertEqual(report3["pathCases"]["P-B-76"]["label"], "plausible")           # 150 pcm: beyond 100, within 200
        self.assertEqual(len(m3["domain"]["jointChecked"]), 8)
        self.assertAlmostEqual(report3["pathCases"]["P-B-76"]["difference"], -1.5e-3, places=9)       # the library minus transport

    def test_the_path_rows_must_be_exactly_the_plan(self):
        path = make_rows(plan=path_cases())
        with self.assertRaises(ValueError):
            xb.check_path(path[:-1])
        with self.assertRaises(ValueError):
            xb.check_path(path + [copy.deepcopy(path[0])])
        bad = copy.deepcopy(path)
        bad[0]["steps"]["SC"] = 0
        with self.assertRaises(ValueError):
            xb.check_path(bad)
        bad = copy.deepcopy(path)
        bad[1]["particles"] = 4000
        with self.assertRaises(ValueError):
            xb.check_path(bad)

    def test_an_unconverged_path_case_is_not_labelled_and_not_listed(self):
        rows = make_rows(correction=planted_c)
        path = make_rows(correction=planted_c, plan=path_cases())
        r = next(x for x in path if x["case"] == "P-S5")
        r["kBatches"] = [(r["k"] - 0.05 if i < 200 else r["k"] + 0.05) + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]
        m, _, report = xb.build(rows, CORE, created="2026-10-11", path_rows=path)
        self.assertFalse(report["pathCases"]["P-S5"]["computed"])
        self.assertEqual(len(m["domain"]["jointChecked"]), 8)
        self.assertEqual(sum(1 for e in report["pathCases"].values() if e["computed"]), 8)

    def test_path_rows_without_per_batch_k_are_refused(self):
        rows = make_rows(correction=planted_c)
        path = make_rows(correction=planted_c, plan=path_cases())
        del path[0]["kBatches"]
        with self.assertRaises(ValueError):
            xb.build(rows, CORE, created="2026-10-11", path_rows=path)

    def test_the_notes_say_whether_the_path_was_checked(self):
        rows = make_rows(correction=planted_c)
        m0, _, _ = xb.build(rows, CORE, created="2026-10-11")
        self.assertIn("NOT checked against held-out", m0["provenance"]["notes"])
        m1, _, _ = xb.build(rows, CORE, created="2026-10-11", path_rows=make_rows(correction=planted_c, plan=path_cases()))
        self.assertIn("Checked against 9 held-out cases: 9 within the limit", m1["provenance"]["notes"])
        self.assertNotIn("NOT checked", m1["provenance"]["notes"])

    def test_an_absent_path_file_is_an_error_unless_no_path_is_given(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "lib"
            args = ["--out", str(out), "--report", str(Path(d) / "rep.json"), "--path", str(Path(d) / "nothing.jsonl")]
            with self.assertRaises(SystemExit):
                xb.main(args)
            self.assertFalse(out.exists())
            self.assertEqual(xb.main(args + ["--model", "interaction", "--no-path"]), 0)
            self.assertTrue((out / "manifest.json").exists())

    def test_holding_the_anchors_cannot_leave_a_decreasing_table(self):
        pts = [{"a": 0.0, "rho": 0.0, "sigma": 0.0}, {"a": 1.0e-3, "rho": 0.0, "sigma": 0.0}, {"a": -8.0e-3, "rho": 0.0, "sigma": 0.0},
               {"a": -9.0e-3, "rho": 5.0e-4, "sigma": 1.0e-4}]       # a positive correction deeper than the zero anchor: the fit would have to decrease
        with self.assertRaises(ValueError):
            xb.fit_correction(pts)

    def test_the_fit_refuses_points_with_the_same_summed_reactivity(self):
        with self.assertRaises(ValueError):
            xb.fit_correction([{"a": 0.0, "rho": 0.0, "sigma": 0.0}, {"a": 0.0, "rho": 1.0e-3, "sigma": 1.0e-4}])

    def test_a_library_without_a_combined_sweep_effect_has_a_flat_table(self):
        m, _, _ = xb.build(self.rows, CORE, created="2026-10-10")
        self.assertTrue(all(abs(v) < 1e-9 for v in m["reactivity"]["rodInteraction"]["rho"]))
        self.assertIn("point-kinetics/rod-interaction-v1", m["capabilities"])

    def test_the_deltas_and_the_boron_axis_are_unchanged_by_the_table(self):
        self.assertEqual(self.m["reactivity"]["boron"]["C"], [300.0, 600.0, 975.0, 1300.0, 1600.0])


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

    def test_a_failed_replacement_restores_the_old_library(self):
        from unittest import mock
        blobs = {f"arrays/{n}.f32": (self.folder / f"arrays/{n}.f32").read_bytes() for n in self.m["arrays"]}
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, self.m, blobs, validate=True)
            before = (folder / "manifest.json").read_bytes()
            real = Path.rename

            def fail_on_stage(self_, target):
                if self_.name.endswith(".new"):
                    raise OSError("simulated failure of the final rename")
                return real(self_, target)

            with mock.patch.object(Path, "rename", fail_on_stage):
                with self.assertRaises(OSError):
                    xb.write_library(folder, self.m, blobs, validate=True)
            self.assertEqual((folder / "manifest.json").read_bytes(), before)
            self.assertFalse((Path(d) / "lib.old").exists())

    def test_a_missing_case_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            xb.build([r for r in self.rows if r["case"] != "TC-600"], CORE)

    def test_a_wrong_reference_configuration_is_refused(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["steps"]["D"] = 228
        with self.assertRaises(ValueError):
            xb.build(rows, CORE)


# --- the shadowing model (fifteenth protocol): each rod's worth scaled by 1 + g(the others' summed reactivity) -------------------------------------------
SHADOW_A = 3.0          # planted g(R) = SHADOW_A * R for R <= 0 (zero above), held at its value at the deepest knot
KNOTS = (-0.003, -0.006, -0.009, -0.0125)       # the planted bank worths are about a third of the real ones, so the free knots are scaled to the deepest R the planted fit cases reach (-0.0126)


def planted_g(r: float) -> float:
    return SHADOW_A * max(min(r, 0.0), KNOTS[-1])


def planted_g_other(r: float) -> float:
    return -5.0 * planted_g(r)              # a different planted law (the planted corrections are small, so it must differ a lot to pass the 100 pcm limit), for the held-out cases that must fail


def worths_planted(steps) -> list[float]:
    return [W[b] * (x_frac(steps[b]) - x_frac(REF_STEPS[b])) for b in xb.BANKS]


def planted_shadow_sum(steps, g) -> float:
    ws = worths_planted(steps)
    s = math.fsum(ws)
    return math.fsum(w * g(s - w) for w in ws if w != 0.0)


class PlantedShadowing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = make_rows(shadow=planted_g)
        cls.path = make_rows(plan=path_cases(), shadow=planted_g)
        cls.held = make_rows(plan=shadow_cases(), shadow=planted_g)
        cls.m, cls.blobs, cls.report = xb.build(cls.rows, CORE, created="2026-10-15", path_rows=cls.path, model="shadowing", shadow_rows=cls.held, shadow_knots=KNOTS)

    def test_the_fit_recovers_the_planted_g_at_every_knot(self):
        t = self.m["reactivity"]["rodShadowing"]
        self.assertEqual(t["R"], sorted([0.0, xb.R_ABOVE] + list(KNOTS)))
        for r, g in zip(t["R"], t["g"]):
            self.assertAlmostEqual(g, planted_g(r) if r <= 0.0 else 0.0, places=7, msg=str(r))
        self.assertEqual(t["g"][t["R"].index(0.0)], 0.0)
        self.assertEqual(t["g"][-1], 0.0)

    def test_the_table_carries_the_fits_uncertainty_at_the_free_knots_only(self):
        t = self.m["reactivity"]["rodShadowing"]
        for r, u in zip(t["R"], t["unc"]):
            if r < 0.0:
                self.assertGreater(u, 0.0, r)
                self.assertLess(u, 0.1, r)            # g is dimensionless: errors of 1e-4 in reactivity on worths of 1e-3 give an uncertainty of a few percent
            else:
                self.assertEqual(u, 0.0, r)

    def test_the_library_has_v2_only_and_validates(self):
        self.assertIn(xb.ROD_SHADOW_CAPABILITY, self.m["capabilities"])
        self.assertNotIn(xb.ROD_INTERACTION_CAPABILITY, self.m["capabilities"])
        self.assertNotIn("rodInteraction", self.m["reactivity"])
        with tempfile.TemporaryDirectory() as d:
            xb.write_library(Path(d) / "lib", self.m, self.blobs)
            self.assertEqual(validate_library(Path(d) / "lib"), [])

    def test_the_engine_reproduces_the_planted_reactivity_at_nonseparable_states(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, self.m, self.blobs)
            lib = Library(folder)
            for steps in (dict(REF_STEPS), {**REF_STEPS, "D": 0, "C": 60}, {**REF_STEPS, "SC": 0, "SD": 0, "SE": 0, "A": 100},
                          {**REF_STEPS, "D": 0, "C": 0, "B": 0, "A": 30}, {b: 0 for b in xb.BANKS}):
                init = {"rods": {b.lower(): x_frac(s) for b, s in steps.items()}, "boron": B_REF, "Tfuel": T_REF, "Tcoolant": T_REF,
                        "power": {"mode": "given", "value": 1e-3}, "poisons": {"mode": "zero"}}
                e = Engine(lib, init)
                want = planted_rho(steps, B_REF, None, None) + planted_shadow_sum(steps, planted_g)
                self.assertAlmostEqual(e.reactivity(0.0, e.y)["total"], want, places=8, msg=str(steps))

    def test_the_fit_cases_are_the_twelve_and_the_held_out_cases_are_not_in_it(self):
        self.assertEqual(sorted(self.report["tables"]["rodShadowing"]["fitCases"]), sorted(list(xb.FIT_CASES) + list(path_cases())))
        self.assertEqual(set(self.report["heldOutCases"]), set(shadow_cases()))
        self.assertEqual(self.report["pathCases"], {})
        self.assertEqual(self.report["model"], "shadowing")

    def test_held_out_cases_that_agree_are_good_and_listed_as_checked(self):
        for cid, e in self.report["heldOutCases"].items():
            self.assertTrue(e["computed"], cid)
            self.assertEqual(e["label"], "good", cid)
            self.assertLess(abs(e["difference"]), 1e-7, cid)
        self.assertEqual(len(self.m["domain"]["jointChecked"]), 13)
        self.assertIn("Checked against 13 held-out cases: 13 within the limit", self.m["provenance"]["notes"])

    def test_held_out_cases_from_another_law_are_labelled_and_not_listed(self):
        held = make_rows(plan=shadow_cases(), shadow=planted_g_other)
        m, _, report = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_rows=held, shadow_knots=KNOTS)
        deep = report["heldOutCases"]["X-9"]
        self.assertGreater(abs(deep["difference"]), 2e-3)
        self.assertEqual(deep["label"], "fails")
        self.assertLess(len(m["domain"]["jointChecked"]), 13)
        listed = {tuple(sorted(j["rods"].items())) for j in m["domain"]["jointChecked"]}
        for cid, e in report["heldOutCases"].items():
            if e["label"] != "good":
                self.assertNotIn(tuple(sorted({b.lower(): x_frac(s) for b, s in shadow_cases()[cid]["steps"].items()}.items())), listed, cid)

    def test_an_unconverged_held_out_case_is_not_computed(self):
        held = make_rows(plan=shadow_cases(), shadow=planted_g)
        r = next(x for x in held if x["case"] == "O-S3")
        r["kBatches"] = [(r["k"] - 0.05 if i < 200 else r["k"] + 0.05) + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]
        m, _, report = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_rows=held, shadow_knots=KNOTS)
        self.assertFalse(report["heldOutCases"]["O-S3"]["computed"])
        self.assertEqual(len(m["domain"]["jointChecked"]), 12)

    def test_a_held_out_case_missing_from_the_run_is_not_computed_and_the_rest_are_used(self):
        held = [r for r in make_rows(plan=shadow_cases(), shadow=planted_g) if r["case"] != "O-S3"]
        m, _, report = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_rows=held, shadow_knots=KNOTS)
        self.assertFalse(report["heldOutCases"]["O-S3"]["computed"])
        self.assertIn("missing", report["heldOutCases"]["O-S3"]["reason"])
        self.assertEqual(len(m["domain"]["jointChecked"]), 12)
        self.assertIn("Checked against 12 held-out cases: 12 within the limit", m["provenance"]["notes"])
        with self.assertRaises(ValueError):                              # an unknown case is still refused
            xb.build(self.rows, CORE, path_rows=self.path, model="shadowing", shadow_rows=[dict(held[0], case="Z-1")], shadow_knots=KNOTS)

    def test_the_near_critical_cases_of_the_sixteenth_protocol_are_held_out_too(self):
        held = self.held + make_rows(plan=near_cases(), shadow=planted_g)
        m, _, report = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_rows=held, shadow_knots=KNOTS)
        for cid in near_cases():
            self.assertEqual(report["heldOutCases"][cid]["label"], "good", cid)
        self.assertEqual(len(m["domain"]["jointChecked"]), 20)
        self.assertEqual(report["tables"]["rodShadowing"]["fitCases"], self.report["tables"]["rodShadowing"]["fitCases"])      # they do not enter the fit
        self.assertEqual(m["reactivity"]["rodShadowing"], self.m["reactivity"]["rodShadowing"])

    def test_the_notes_say_that_checks_at_another_boron_hold_there_only(self):
        self.assertIn("860 ppm hold at that boron only", self.m["provenance"]["notes"])
        no_lesson = [r for r in make_rows(plan=shadow_cases(), shadow=planted_g) if r["boron"] == 975.0]
        m, _, _ = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_rows=no_lesson, shadow_knots=KNOTS)
        self.assertNotIn("hold at that boron only", m["provenance"]["notes"])

    def test_without_held_out_cases_the_notes_say_so_and_nothing_is_listed(self):
        m, _, _ = xb.build(self.rows, CORE, created="2026-10-15", path_rows=self.path, model="shadowing", shadow_knots=KNOTS)
        self.assertEqual(m["domain"]["jointChecked"], [])
        self.assertIn("NOT checked against held-out", m["provenance"]["notes"])

    def test_the_nine_path_cases_are_required_and_the_models_do_not_mix(self):
        with self.assertRaises(ValueError):
            xb.build(self.rows, CORE, model="shadowing")                                   # no fit data for g
        with self.assertRaises(ValueError):
            xb.build(make_rows(), CORE, model="interaction", shadow_rows=self.held)
        with self.assertRaises(ValueError):
            xb.build(self.rows, CORE, model="other")
        short = [r for r in self.path if r["case"] != "P-S5"]
        with self.assertRaises(ValueError):
            xb.build(self.rows, CORE, path_rows=short, model="shadowing")
        wrong = [dict(r, boron=975.0) if r["case"] == "L-C-0" else r for r in self.held]
        with self.assertRaises(ValueError):
            xb.build(self.rows, CORE, path_rows=self.path, model="shadowing", shadow_rows=wrong)

    def test_a_fit_that_cannot_determine_every_knot_is_refused(self):
        ws = worths_planted({**REF_STEPS, "D": 0, "C": 0})
        cases = [{"case": "only", "ws": ws, "y": planted_shadow_sum({**REF_STEPS, "D": 0, "C": 0}, planted_g), "sigma": 1e-4}]
        with self.assertRaises(ValueError):
            xb.fit_shadowing(cases, KNOTS)

    def test_the_fit_weights_the_cases_by_their_statistical_errors(self):
        # the twelve planted fit cases, one of them given a wrong value: believed (small error) it moves the table, doubted (large error) it does not
        states = [sweep_cases()[c]["steps"] for c in xb.FIT_CASES] + [c["steps"] for c in path_cases().values()]
        base = [{"case": str(i), "ws": worths_planted(st), "y": planted_shadow_sum(st, planted_g), "sigma": 1e-4} for i, st in enumerate(states)]
        wrong = dict(base[2], y=base[2]["y"] + 5e-4)
        tb = xb.fit_shadowing(base, KNOTS)
        for r, g in zip(tb["a"], tb["rho"]):
            self.assertAlmostEqual(g, planted_g(r) if r <= 0.0 else 0.0, places=7)
        believed = xb.fit_shadowing(base[:2] + [wrong] + base[3:], KNOTS)
        doubted = xb.fit_shadowing(base[:2] + [dict(wrong, sigma=1e-1)] + base[3:], KNOTS)
        self.assertGreater(max(abs(a - b) for a, b in zip(believed["rho"], tb["rho"])), 1e-2)
        self.assertLess(max(abs(a - b) for a, b in zip(doubted["rho"], tb["rho"])), 1e-3)


if __name__ == "__main__":
    unittest.main()
