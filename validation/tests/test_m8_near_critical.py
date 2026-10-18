"""Tests for validation/m8_near_critical.py on a planted library: the real library and the 7 near-critical cases are analysed once, by the script.

The library is built by the real exporter from a planted sweep with a known shadowing law (pipeline/tests/test_export_beavrs.py). The planted world is critical
somewhere else than the real one, so the tests plant the 7 cases at a boron where the planted library crosses zero (950 ppm) and say so; the pin, the labels and
the decision rules do not depend on that.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.openmc.beavrs_cases import near_cases, path_cases, shadow_cases
from pipeline.tests import test_export_beavrs as planted
from validation import m8_beavrs_library as lb
from validation import m8_near_critical as nc
from validation import m8_rod_shadowing as rs

BORON = 950.0                  # where the planted library is critical with D and C in and C part-way


def planted_near_rows():
    rows = planted.make_rows(plan=near_cases(), shadow=planted.planted_g)
    for r in rows:
        r["boron"] = BORON
        rho = planted.planted_rho(r["steps"], BORON, None, None) + planted.planted_shadow_sum(r["steps"], planted.planted_g)
        r["k"] = 1.0 / (1.0 - rho)
        r["kBatches"] = [r["k"] + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]
    return rows


def shift(rows, case, drho):
    r = next(x for x in rows if x["case"] == case)
    rho = (r["k"] - 1.0) / r["k"] + drho
    r["k"] = 1.0 / (1.0 - rho)
    r["kBatches"] = [r["k"] + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]


def shift_all(rows, drho):
    for r in rows:
        shift(rows, r["case"], drho)


def unconverge(rows, case):
    r = next(x for x in rows if x["case"] == case)
    r["kBatches"] = [(r["k"] - 0.05 if i < 200 else r["k"] + 0.05) + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]


def items(report, prefix):
    return [i for i in report["decision"]["items"] if i.startswith(prefix)]


class PlantedAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sweep = planted.make_rows(shadow=planted.planted_g)
        path = planted.make_rows(plan=path_cases(), shadow=planted.planted_g)
        held = planted.make_rows(plan=shadow_cases(), shadow=planted.planted_g)
        m, blobs, _ = xb.build(sweep, planted.CORE, created="2026-10-15", path_rows=path, model="shadowing", shadow_rows=held, shadow_knots=planted.KNOTS)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name) / "lib"
        xb.write_library(cls.folder, m, blobs, validate=True)
        cls.model = rs.ShadowModel(cls.folder)
        cls.rows = planted_near_rows()
        cls.report = nc.analyse(cls.model, cls.rows, digest=None, boron=BORON)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_with(self, rows):
        return nc.analyse(self.model, rows, digest=None, boron=BORON)

    def test_a_planted_law_is_reproduced_and_the_critical_position_agrees(self):
        p = self.report["P"]
        self.assertEqual(len(p), 7)
        for c, e in p.items():
            self.assertTrue(e["computed"], c)
            self.assertAlmostEqual(e["differencePcm"], 0.0, places=3, msg=c)
            self.assertEqual(e["label"], "good", c)
        crit = self.report["critical"]
        self.assertTrue(crit["computed"])
        self.assertAlmostEqual(crit["differenceSteps"], 0.0, delta=0.5)         # the planted reactivity is linear in C between the bracketing cases
        self.assertEqual(len(items(self.report, "Q1.")), 1)
        self.assertEqual(items(self.report, "Q2."), [])

    def test_the_library_critical_position_is_the_zero_of_the_planted_reactivity(self):
        base = near_cases()["N-C-0"]["steps"]

        def rho(c):
            st = {**base, "C": c}
            return planted.planted_rho(st, BORON, None, None) + planted.planted_shadow_sum(st, planted.planted_g)
        lo, hi = 0.0, 228.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if rho(mid) < 0 else (lo, mid)
        self.assertAlmostEqual(nc.library_critical(self.model, BORON), lo, delta=1e-3)
        self.assertIsNone(nc.library_critical(self.model, 1500.0))               # subcritical everywhere
        self.assertIsNone(nc.library_critical(self.model, 600.0))                # supercritical everywhere

    def test_the_critical_position_labels_sit_on_their_boundaries(self):
        slope = (planted.W["C"] * 1e5) / 228.0                                    # pcm per step, the planted bank C
        for d, want in ((10.0, "good"), (14.0, "good"), (20.0, "plausible"), (28.0, "plausible"), (40.0, "fails")):
            rows = copy.deepcopy(self.rows)
            shift_all(rows, -d * slope / 1e5)                                     # the transport zero moves by d steps
            r = self.run_with(rows)
            self.assertAlmostEqual(abs(r["critical"]["differenceSteps"]), d, delta=2.0)
            self.assertEqual(r["critical"]["label"], want, (d, r["critical"]["differenceSteps"]))

    def test_the_critical_position_label_boundaries_are_15_and_30_steps(self):
        for d, want in ((15.0, "good"), (-15.0, "good"), (15.01, "plausible"), (-30.0, "plausible"), (30.0, "plausible"), (30.01, "fails"), (-30.01, "fails"), (0.0, "good")):
            self.assertEqual(nc.crit_label(d), want, d)

    def test_the_signs_are_library_minus_transport(self):
        slope = (planted.W["C"] * 1e5) / 228.0
        rows = copy.deepcopy(self.rows)
        shift(rows, "N-C-228", 2.5e-3)                                          # transport 250 pcm higher: the library is lower by 250
        self.assertAlmostEqual(self.run_with(rows)["P"]["N-C-228"]["differencePcm"], -250.0, delta=0.5)
        rows = copy.deepcopy(self.rows)
        shift_all(rows, -20.0 * slope / 1e5)                                   # transport lower everywhere: its zero is at a larger C, the library's is earlier: negative
        self.assertAlmostEqual(self.run_with(rows)["critical"]["differenceSteps"], -20.0, delta=2.0)
        rows = copy.deepcopy(self.rows)
        shift_all(rows, 20.0 * slope / 1e5)
        self.assertAlmostEqual(self.run_with(rows)["critical"]["differenceSteps"], 20.0, delta=2.0)

    def test_a_critical_position_that_fails_defeats_the_lesson_even_with_every_case_good(self):
        rows = copy.deepcopy(self.rows)
        shift_all(rows, -5.0e-4)                                       # 50 pcm: every case good (limit 100), the zero moves by about 40 steps
        r = self.run_with(rows)
        self.assertTrue(all(e["label"] == "good" for e in r["P"].values()))
        self.assertEqual(items(r, "Q1."), [])
        self.assertIn("critical C is", items(r, "Q2.")[0])

    def test_without_a_bracketing_pair_the_critical_position_is_not_computed_and_the_lesson_is_not_built(self):
        rows = copy.deepcopy(self.rows)
        shift_all(rows, 4.0e-3)                                        # all transport cases supercritical
        r = self.run_with(rows)
        self.assertFalse(r["critical"]["computed"])
        self.assertEqual(items(r, "Q1."), [])
        self.assertIn("not computed", items(r, "Q2.")[0])

    def test_one_failing_case_under_300_pcm_still_leaves_six_of_seven(self):
        rows = copy.deepcopy(self.rows)
        shift(rows, "N-C-228", 2.5e-3)                                 # 250 pcm: fails (beyond 200), under the 300 line; away from the zero crossing
        r = self.run_with(rows)
        self.assertEqual(r["P"]["N-C-228"]["label"], "fails")
        self.assertEqual(len(items(r, "Q1.")), 1)
        self.assertIn("6 of 7", items(r, "Q1.")[0])

    def test_two_failing_cases_defeat_the_lesson(self):
        rows = copy.deepcopy(self.rows)
        shift(rows, "N-C-228", 2.5e-3)
        shift(rows, "N-C-0", 2.5e-3)
        r = self.run_with(rows)
        self.assertEqual(items(r, "Q1."), [])
        self.assertIn("only 5 of 7 cases good or plausible", items(r, "Q2.")[0])

    def test_a_case_beyond_300_pcm_defeats_the_lesson(self):
        rows = copy.deepcopy(self.rows)
        shift(rows, "N-C-228", 3.5e-3)
        r = self.run_with(rows)
        self.assertEqual(items(r, "Q1."), [])
        self.assertIn("beyond 300 pcm: N-C-228", items(r, "Q2.")[0])

    def test_unconverged_and_missing_cases_are_not_computed_and_the_computed_ones_decide(self):
        rows = copy.deepcopy(self.rows)
        unconverge(rows, "N-C-228")
        r = self.run_with(rows)
        self.assertFalse(r["P"]["N-C-228"]["computed"])
        self.assertEqual(len(items(r, "Q1.")), 1)                      # six computed, all good
        self.assertTrue(any("N-C-228" in i for i in items(r, "Q3.")))
        rows = [x for x in copy.deepcopy(self.rows) if x["case"] not in ("N-C-228", "N-C-180")]
        r = self.run_with(rows)
        self.assertIn("missing", r["P"]["N-C-228"]["reason"])
        self.assertEqual(items(r, "Q1."), [])                          # five computed: six are needed
        self.assertIn("only 5 of 7 cases good or plausible (2 not computed)", items(r, "Q2.")[0])

    def test_the_transport_zero_is_found_between_the_bracketing_neighbours(self):
        pts = {"a": {"C": 100.0, "transportPcm": -200.0, "transportSigmaPcm": 25.0}, "b": {"C": 140.0, "transportPcm": 100.0, "transportSigmaPcm": 30.0},
               "c": {"C": 180.0, "transportPcm": 400.0, "transportSigmaPcm": 25.0}, "d": {"C": 40.0, "transportPcm": -900.0, "transportSigmaPcm": 25.0}}
        t = nc.transport_critical(pts)
        self.assertAlmostEqual(t["steps"], 100.0 + 200.0 / 300.0 * 40.0, places=9)
        self.assertEqual(t["between"], [100.0, 140.0])
        self.assertAlmostEqual(t["sigmaSteps"], 30.0 / (300.0 / 40.0), places=9)
        self.assertIsNone(nc.transport_critical({k: v for k, v in pts.items() if k in ("c", "b")}))             # none below zero
        self.assertIsNone(nc.transport_critical({k: v for k, v in pts.items() if k in ("a", "d")}))             # none above zero
        exact = {"x": {"C": 10.0, "transportPcm": -50.0, "transportSigmaPcm": 1.0}, "y": {"C": 20.0, "transportPcm": 0.0, "transportSigmaPcm": 1.0}}
        self.assertAlmostEqual(nc.transport_critical(exact)["steps"], 20.0)
        # a planned case between the pair that was not computed is reported, not hidden
        gap = nc.transport_critical({k: v for k, v in pts.items() if k in ("a", "c")}, [40.0, 100.0, 120.0, 140.0, 180.0])
        self.assertEqual(gap["between"], [100.0, 180.0])
        self.assertEqual(gap["spansUncomputed"], [120.0, 140.0])
        self.assertEqual(nc.transport_critical(pts, [40.0, 100.0, 140.0, 180.0])["spansUncomputed"], [])

    def test_a_library_whose_reactivity_block_is_not_the_protocols_is_refused(self):
        with self.assertRaises(nc.PinError):
            nc.check_pin(self.model)                                    # the planted library is not the protocol's
        real = rs.ShadowModel(lb.LIBRARY)
        nc.check_pin(real)                                              # the committed library is
        tampered = rs.ShadowModel.__new__(rs.ShadowModel)
        tampered.m = copy.deepcopy(real.m)
        tampered.m["reactivity"]["rodShadowing"]["g"][1] += 1e-6
        with self.assertRaises(nc.PinError):
            nc.check_pin(tampered)
        notes_only = rs.ShadowModel.__new__(rs.ShadowModel)
        notes_only.m = copy.deepcopy(real.m)
        notes_only.m["domain"]["jointChecked"] = []
        notes_only.m["provenance"]["notes"] += " more"
        nc.check_pin(notes_only)                                        # the jointChecked list and the notes may change

    def test_the_file_must_be_the_plan(self):
        with tempfile.TemporaryDirectory() as d:
            def write(rows):
                p = Path(d) / "x.jsonl"
                p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
                return p
            plan_rows = planted.make_rows(plan=near_cases(), shadow=planted.planted_g)
            self.assertEqual(len(nc.load_near(write(plan_rows))), 7)
            self.assertEqual(len(nc.load_near(write(plan_rows[:-1]))), 6)
            wrong = copy.deepcopy(plan_rows)
            wrong[0]["boron"] = 975.0
            with self.assertRaises(ValueError):
                nc.load_near(write(wrong))
            nob = copy.deepcopy(plan_rows)
            del nob[0]["kBatches"]
            with self.assertRaises(ValueError):
                nc.load_near(write(nob))
            with self.assertRaises(ValueError):
                nc.load_near(write(plan_rows + [copy.deepcopy(plan_rows[0])]))
            for key, bad in (("seed", 2), ("beavrsHead", "deadbee")):
                other = copy.deepcopy(plan_rows)
                other[0][key] = bad
                with self.assertRaises(ValueError):
                    nc.load_near(write(other))
            unknown = copy.deepcopy(plan_rows)
            unknown[0]["case"] = "Z-1"
            with self.assertRaises(ValueError):
                nc.load_near(write(unknown))


if __name__ == "__main__":
    unittest.main()
