"""Tests for validation/m8_rod_shadowing.py on a planted library: the real library and the 13 held-out cases are analysed once, by the script.

The library is built by the real exporter from a planted sweep whose combined rod worth follows a known shadowing law (pipeline/tests/test_export_beavrs.py),
and the 13 held-out rows are planted from the same law, so the right answer is known at every case.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.openmc.beavrs_cases import path_cases, shadow_cases
from pipeline.tests import test_export_beavrs as planted
from validation import m8_beavrs_library as lb
from validation import m8_rod_shadowing as rs


def shift(rows, case, drho):
    r = next(x for x in rows if x["case"] == case)
    rho = (r["k"] - 1.0) / r["k"] + drho
    r["k"] = 1.0 / (1.0 - rho)
    r["kBatches"] = [r["k"] + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]


def unconverge(rows, case):
    r = next(x for x in rows if x["case"] == case)
    r["kBatches"] = [(r["k"] - 0.05 if i < 200 else r["k"] + 0.05) + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]


def items(report, prefix):
    return [i for i in report["decision"]["items"] if i.startswith(prefix)]


class PlantedAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sweep = planted.make_rows(shadow=planted.planted_g)
        cls.path = planted.make_rows(plan=path_cases(), shadow=planted.planted_g)
        cls.held = planted.make_rows(plan=shadow_cases(), shadow=planted.planted_g)
        m, blobs, _ = xb.build(cls.sweep, planted.CORE, created="2026-10-15", path_rows=cls.path, model="shadowing", shadow_rows=cls.held, shadow_knots=planted.KNOTS)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name) / "lib"
        xb.write_library(cls.folder, m, blobs, validate=True)
        cls.model = rs.ShadowModel(cls.folder)
        cls.report = rs.analyse(cls.model, cls.sweep, cls.held, pin=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_with(self, held):
        return rs.analyse(self.model, self.sweep, held, pin=None)

    def test_a_planted_law_is_reproduced_at_every_held_out_case_and_the_lesson_is_allowed(self):
        p = self.report["P"]
        self.assertEqual(len(p), 13)
        for c, e in p.items():
            self.assertTrue(e["computed"], c)
            self.assertAlmostEqual(e["differencePcm"], 0.0, places=3, msg=c)
            self.assertEqual(e["label"], "good", c)
        self.assertEqual(len(items(self.report, "P1.")), 1)
        self.assertEqual(items(self.report, "P2."), [])
        self.assertIn("lesson may be built", items(self.report, "P1.")[0])

    def test_the_shadowing_improves_on_the_summed_model_in_deep_states(self):
        e = self.report["P"]["X-9"]
        self.assertTrue(e["improvesOnTheSum"])
        self.assertGreater(abs(e["correctionPcm"]), 10.0)          # the planted law weakens the rods (the real one strengthens them); the sign does not matter here
        self.assertAlmostEqual(e["differenceWithoutTablePcm"], -e["correctionPcm"], places=3)
        self.assertAlmostEqual(self.report["P"]["L-ARO-860"]["correctionPcm"], 0.0, places=6)         # nothing moved: no shadowing

    def test_the_correction_is_the_planted_law_and_the_difference_is_library_minus_transport(self):
        want = planted.planted_shadow_sum(shadow_cases()["X-9"]["steps"], planted.planted_g) * 1e5
        e = self.report["P"]["X-9"]
        self.assertAlmostEqual(e["correctionPcm"], want, places=3)
        held = copy.deepcopy(self.held)
        shift(held, "X-9", 2.5e-3)                                       # transport 250 pcm higher: the library is 250 pcm lower
        r = self.run_with(held)
        self.assertAlmostEqual(r["P"]["X-9"]["differencePcm"], -250.0, delta=0.5)
        shift(held, "X-9", -5.0e-3)                                      # and 250 pcm lower than the planted: the library is 250 pcm higher
        r = self.run_with(held)
        self.assertAlmostEqual(r["P"]["X-9"]["differencePcm"], 250.0, delta=0.5)

    def test_a_table_that_makes_a_case_worse_is_flagged(self):
        held = copy.deepcopy(self.held)
        shift(held, "X-9", -self.report["P"]["X-9"]["correctionPcm"] / 1e5)       # the transport case equals the summed model
        r = self.run_with(held)
        self.assertFalse(r["P"]["X-9"]["improvesOnTheSum"])
        self.assertTrue(self.report["P"]["X-9"]["improvesOnTheSum"])

    def test_cases_that_are_not_computed_can_keep_the_decision_open_when_they_could_still_save_it(self):
        held = copy.deepcopy(self.held)
        for c in ("O-S3", "O-S5", "O-S6", "X-5"):
            unconverge(held, c)                                          # nine computed, all good: ten are needed, and four are missing
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertEqual(items(r, "P2."), [])
        self.assertTrue(any("not decided" in i for i in items(r, "P4.")))
        shift(held, "L-C-0", 2.5e-3)                                      # now only eight good or plausible even with the four, still reachable (8 + 4 = 12): open
        shift(held, "L-C-160", 2.5e-3)                                    # two lesson fails: lesson cases 3 of 5 and none missing: defeated
        r = self.run_with(held)
        self.assertTrue(items(r, "P2."))

    def test_part_m_is_the_twelfth_protocols_analysis_of_the_library(self):
        m = self.report["M"]
        for key in ("A", "B", "C", "F"):
            self.assertIn(key, m)
        self.assertEqual(set(self.report["libraryPcmAtS3S5S6"]), {"S3", "S5", "S6"})

    def test_the_other_order_and_sa_sb_states_are_reported_apart(self):
        self.assertTrue(any(i.startswith("P3.") and "4 of 4" in i and "may state" in i for i in self.report["decision"]["items"]))
        self.assertTrue(any(i.startswith("P5.") and "X-9" in i for i in self.report["decision"]["items"]))

    def test_one_lesson_case_that_fails_under_300_pcm_still_leaves_four_of_five(self):
        held = copy.deepcopy(self.held)
        shift(held, "L-C-83", 2.5e-3)                                    # 250 pcm: fails (beyond 200), under the 300 pcm line
        r = self.run_with(held)
        self.assertEqual(r["P"]["L-C-83"]["label"], "fails")
        self.assertEqual(len(items(r, "P1.")), 1)
        self.assertIn("4 of 5 lesson cases", items(r, "P1.")[0])

    def test_two_lesson_cases_that_fail_defeat_the_lesson(self):
        held = copy.deepcopy(self.held)
        shift(held, "L-C-83", 2.5e-3)
        shift(held, "L-C-40", 2.5e-3)
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertTrue(items(r, "P2.") and "only 3 of 5 lesson cases" in items(r, "P2.")[0])

    def test_a_lesson_case_beyond_300_pcm_defeats_the_lesson_even_with_four_of_five(self):
        held = copy.deepcopy(self.held)
        shift(held, "L-C-83", 3.5e-3)
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertIn("lesson cases beyond 300 pcm: L-C-83", items(r, "P2.")[0])

    def test_the_boron_reference_failing_names_the_boron_table(self):
        held = copy.deepcopy(self.held)
        shift(held, "L-ARO-860", 2.5e-3)
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertIn("the boron table, not the rods", items(r, "P2.")[0])

    def test_fewer_than_ten_of_thirteen_defeat_the_lesson(self):
        held = copy.deepcopy(self.held)
        for c in ("O-S3", "O-S5", "O-S6", "X-5"):
            shift(held, c, 2.5e-3)                                       # four fails: nine good or plausible
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertIn("only 9 of 13 good or plausible overall", items(r, "P2.")[0])

    def test_any_case_beyond_400_pcm_defeats_the_lesson(self):
        held = copy.deepcopy(self.held)
        shift(held, "X-9", 5.0e-3)
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertIn("beyond 400 pcm: X-9", items(r, "P2.")[0])

    def test_the_order_claim_needs_three_of_four(self):
        held = copy.deepcopy(self.held)
        shift(held, "O-S3", 2.5e-3)
        r = self.run_with(held)
        self.assertTrue(any(i.startswith("P3.") and "3 of 4" in i and "may state" in i for i in r["decision"]["items"]))
        shift(held, "O-S5", 2.5e-3)
        r = self.run_with(held)
        self.assertTrue(any(i.startswith("P3.") and "2 of 4" in i and "benchmark order and the lesson's path only" in i for i in r["decision"]["items"]))

    def test_one_unconverged_lesson_case_is_not_computed_and_four_of_four_still_allow_the_lesson(self):
        held = copy.deepcopy(self.held)
        unconverge(held, "L-C-40")
        r = self.run_with(held)
        self.assertFalse(r["P"]["L-C-40"]["computed"])
        self.assertEqual(len(items(r, "P1.")), 1)
        self.assertTrue(any("not computed" in i and "L-C-40" in i for i in items(r, "P4.")))

    def test_two_unconverged_lesson_cases_leave_the_decision_open(self):
        held = copy.deepcopy(self.held)
        unconverge(held, "L-C-40")
        unconverge(held, "L-C-120")
        shift(held, "L-C-83", 2.5e-3)                                    # computed: 2 good or plausible of 5 (one fails, two missing): the thresholds need the missing ones
        r = self.run_with(held)
        self.assertEqual(items(r, "P1."), [])
        self.assertEqual(items(r, "P2."), [])
        self.assertTrue(any("not decided" in i for i in items(r, "P4.")))

    def test_the_three_sigma_rule_widens_the_limit_for_an_uncertain_transport_case(self):
        held = copy.deepcopy(self.held)
        r0 = next(x for x in held if x["case"] == "L-C-83")
        r0["kStd"] = 1.1e-3                                              # sigma about 110 pcm: limit 330 pcm
        shift(held, "L-C-83", 2.5e-3)
        r = self.run_with(held)
        self.assertEqual(r["P"]["L-C-83"]["label"], "good")
        self.assertAlmostEqual(r["P"]["L-C-83"]["limitPcm"], 3.0 * r["P"]["L-C-83"]["transportSigmaPcm"], places=6)

    def test_the_labels_sit_exactly_on_the_boundaries(self):
        self.assertEqual(rs.label_of(100.0, 20.0)[0], "good")
        self.assertEqual(rs.label_of(100.1, 20.0)[0], "plausible")
        self.assertEqual(rs.label_of(200.0, 20.0)[0], "plausible")
        self.assertEqual(rs.label_of(200.1, 20.0)[0], "fails")
        self.assertEqual(rs.label_of(-100.0, 20.0)[0], "good")
        self.assertEqual(rs.label_of(120.0, 40.0)[0], "good")           # 3 sigma = 120 pcm
        self.assertEqual(rs.label_of(120.1, 40.0)[0], "plausible")
        self.assertEqual(rs.label_of(240.0, 40.0)[0], "plausible")
        self.assertEqual(rs.label_of(240.1, 40.0)[0], "fails")

    def test_a_library_that_is_not_the_protocols_is_refused(self):
        with self.assertRaises(rs.PinError):
            rs.check_pin(self.model)                                     # the planted g is not the protocol's
        bad = copy.deepcopy(self.model.m)
        m = rs.ShadowModel.__new__(rs.ShadowModel)
        m.m = bad
        real = rs.ShadowModel(lb.LIBRARY)
        rs.check_pin(real)                                               # the committed library carries the protocol's table
        m.m = copy.deepcopy(real.m)
        m.m["reactivity"]["rodShadowing"]["g"][1] += 0.05
        with self.assertRaises(rs.PinError):
            rs.check_pin(m)
        m.m = copy.deepcopy(real.m)
        m.m["reactivity"]["rodShadowing"]["g"][-1] = 0.01
        with self.assertRaises(rs.PinError):
            rs.check_pin(m)

    def test_the_held_out_file_must_be_the_plan(self):
        with tempfile.TemporaryDirectory() as d:
            def write(rows):
                p = Path(d) / "x.jsonl"
                p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
                return p
            self.assertEqual(len(rs.load_shadow(write(self.held))), 13)
            with self.assertRaises(ValueError):
                rs.load_shadow(write(self.held[:-1]))
            wrong = copy.deepcopy(self.held)
            wrong[0]["boron"] = 975.0
            with self.assertRaises(ValueError):
                rs.load_shadow(write(wrong))
            nob = copy.deepcopy(self.held)
            del nob[0]["kBatches"]
            with self.assertRaises(ValueError):
                rs.load_shadow(write(nob))
            dup = copy.deepcopy(self.held) + [copy.deepcopy(self.held[0])]
            with self.assertRaises(ValueError):
                rs.load_shadow(write(dup))


if __name__ == "__main__":
    unittest.main()
