"""Tests for validation/m8_rod_interaction.py on a planted library: the real library and the nine held-out cases are analysed once, by the script.

The library is built by the real exporter from a planted sweep whose combined rod worth is a known function of the summed worth (pipeline/tests/test_export_beavrs.py),
and the nine path rows are planted from the same function, so the right answer is known at every case.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.openmc.beavrs_cases import path_cases
from pipeline.tests import test_export_beavrs as planted
from validation import m8_beavrs_library as lb
from validation import m8_rod_interaction as ri

BATCHES = 300


def with_batches(rows):
    out = copy.deepcopy(rows)
    for r in out:
        r["kBatches"] = [r["k"] + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]
    return out


def shift(rows, case, drho):
    r = next(x for x in rows if x["case"] == case)
    rho = (r["k"] - 1.0) / r["k"] + drho
    r["k"] = 1.0 / (1.0 - rho)
    r["kBatches"] = [r["k"] + (0.001 if i % 2 else -0.001) for i in range(r["batches"])]


class PlantedAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sweep = planted.make_rows(correction=planted.planted_c)
        cls.path = with_batches(planted.make_rows(correction=planted.planted_c, plan=path_cases()))
        m, blobs, _ = xb.build(cls.sweep, planted.CORE, created="2026-10-11", path_rows=cls.path)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name) / "lib"
        xb.write_library(cls.folder, m, blobs, validate=True)
        cls.model = ri.RIModel(cls.folder)
        cls.report = ri.analyse(cls.model, cls.sweep, cls.path, pin=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_planted_path_is_reproduced_and_the_assumption_holds(self):
        p = self.report["P"]
        self.assertEqual(len(p), 9)
        for c, e in p.items():
            self.assertTrue(e["computed"], c)
            self.assertAlmostEqual(e["differencePcm"], 0.0, places=3, msg=c)
            self.assertEqual(e["label"], "good")
        self.assertTrue(any(i.startswith("P1.") for i in self.report["decision"]["items"]))

    def test_the_table_improves_on_the_summed_model_where_it_matters(self):
        p = self.report["P"]
        # the planted correction is zero for a sum shallower than the deepest single bank, so only the deeper states gain
        self.assertTrue(p["P-S6"]["improvesOnTheSum"])
        self.assertLess(p["P-S6"]["correctionPcm"], -100.0)
        self.assertAlmostEqual(p["P-S6"]["differenceWithoutTablePcm"], -p["P-S6"]["correctionPcm"], places=3)

    def test_part_m_is_the_twelfth_protocols_analysis_of_the_library(self):
        m = self.report["M"]
        for key in ("A", "B", "C", "F"):
            self.assertIn(key, m)
        self.assertEqual(set(self.report["libraryPcmAtS3S5S6"]), {"S3", "S5", "S6"})
        self.assertTrue(all(e["computed"] for e in m["A"].values()))

    def test_one_case_beyond_its_limit_fails_but_does_not_defeat_the_assumption(self):
        path = copy.deepcopy(self.path)
        shift(path, "P-SD-76", 3.0e-3)                                 # 300 pcm off: fails, under the 400 pcm line
        r = ri.analyse(self.model, self.sweep, path, pin=None)
        self.assertEqual(r["P"]["P-SD-76"]["label"], "fails")
        self.assertTrue(any(i.startswith("P1.") for i in r["decision"]["items"]))        # 8 of 9, none beyond 400

    def test_cases_beyond_400_pcm_defeat_the_assumption(self):
        path = copy.deepcopy(self.path)
        shift(path, "P-SD-76", 5.0e-3)
        r = ri.analyse(self.model, self.sweep, path, pin=None)
        items = r["decision"]["items"]
        self.assertFalse(any(i.startswith("P1.") for i in items))
        self.assertTrue(any(i.startswith("P2.") and "P-SD-76" in i for i in items))

    def test_fewer_than_seven_good_or_plausible_defeats_the_assumption(self):
        path = copy.deepcopy(self.path)
        for c in ("P-S3", "P-S5", "P-C-76"):
            shift(path, c, 3.0e-3)                                      # three fails: six good or plausible
        r = ri.analyse(self.model, self.sweep, path, pin=None)
        self.assertTrue(any(i.startswith("P2.") for i in r["decision"]["items"]))
        self.assertFalse(any(i.startswith("P1.") for i in r["decision"]["items"]))

    def test_a_label_follows_the_limit_of_100_pcm_or_three_sigma(self):
        path = copy.deepcopy(self.path)
        shift(path, "P-B-76", 1.5e-3)                                   # 150 pcm: plausible (limit 100 pcm, twice that is 200)
        r = ri.analyse(self.model, self.sweep, path, pin=None)
        e = r["P"]["P-B-76"]
        self.assertEqual(e["label"], "plausible")
        self.assertAlmostEqual(e["differencePcm"], -150.0, places=3)     # library minus transport
        self.assertGreaterEqual(e["limitPcm"], 100.0)

    def test_the_limit_is_three_sigma_when_that_is_larger_than_100_pcm(self):
        path = copy.deepcopy(self.path)
        shift(path, "P-B-76", 1.5e-3)                                 # 150 pcm off: beyond 100 but within 180
        r_ = next(x for x in path if x["case"] == "P-B-76")
        r_["kStd"] = 6.0e-4 * r_["k"] ** 2                             # sigma = 60 pcm: three sigma is 180 pcm
        e = ri.analyse(self.model, self.sweep, path, pin=None)["P"]["P-B-76"]
        self.assertAlmostEqual(e["transportSigmaPcm"], 60.0, places=6)
        self.assertAlmostEqual(e["limitPcm"], 180.0, places=6)
        self.assertEqual(e["label"], "good")

    def test_a_table_that_makes_a_case_worse_is_seen(self):
        flat = with_batches(planted.make_rows(plan=path_cases()))      # a path with no combined effect: the table over-corrects the deep states
        r = ri.analyse(self.model, self.sweep, flat, pin=None)
        self.assertFalse(r["P"]["P-S6"]["improvesOnTheSum"])
        self.assertLess(r["P"]["P-S6"]["differenceWithoutTablePcm"], 1.0)           # the summed model was right there
        self.assertTrue(any(i.startswith("P2b.") or i.startswith("P2.") for i in r["decision"]["items"]))

    def test_an_unconverged_case_is_not_computed_and_enters_nothing(self):
        path = copy.deepcopy(self.path)
        r_ = next(x for x in path if x["case"] == "P-S5")
        r_["kBatches"] = [(r_["k"] - 0.05 if i < 200 else r_["k"] + 0.05) + (0.001 if i % 2 else -0.001) for i in range(r_["batches"])]    # the two windows differ a lot
        r = ri.analyse(self.model, self.sweep, path, pin=None)
        self.assertFalse(r["P"]["P-S5"]["computed"])
        self.assertTrue(any(i.startswith("P4.") and "P-S5" in i for i in r["decision"]["items"]))

    def test_the_protocols_table_is_pinned(self):
        with self.assertRaises(ri.PinError):
            ri.analyse(self.model, self.sweep, self.path)                     # the planted table is not the protocol's
        t = self.model.m["reactivity"]["rodInteraction"]
        pin = tuple(zip((s * 1e5 for s in t["S"]), (r * 1e5 for r in t["rho"])))
        ri.check_pin(self.model, pin)                                        # its own table passes
        off = tuple((s, r + 6.0) for s, r in pin)
        with self.assertRaises(ri.PinError):
            ri.check_pin(self.model, off)                                    # 6 pcm off in a correction: beyond the 5 pcm tolerance
        near = tuple((s, r + 4.0) for s, r in pin)
        ri.check_pin(self.model, near)                                       # 4 pcm: within

    def test_the_model_error_includes_the_table(self):
        rods = self.model.rods(7)
        plain = lb.Model(self.folder, expect_digest=None)
        self.assertGreater(self.model.sigma(rods, lb.BORON_REF), plain.sigma(rods, lb.BORON_REF))
        a = (self.model.rods(0), lb.BORON_REF, None, None)
        b = (self.model.rods(7), lb.BORON_REF, None, None)
        self.assertGreater(self.model.sigma_between(a, b), plain.sigma_between(a, b))
        self.assertEqual(self.model.sigma_between(a, a), 0.0)                 # same state: every error cancels

    def test_loading_refuses_path_files_that_are_not_the_plan(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "path.jsonl"
            good = self.path
            p.write_text("\n".join(json.dumps(r) for r in good) + "\n", encoding="utf-8")
            self.assertEqual(len(ri.load_path(p)), 9)
            p.write_text("\n".join(json.dumps(r) for r in good[:-1]) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ri.load_path(p)
            bad = copy.deepcopy(good)
            del bad[0]["kBatches"]
            p.write_text("\n".join(json.dumps(r) for r in bad) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ri.load_path(p)

    def test_a_library_without_the_table_is_refused(self):
        plain_m, blobs, _ = xb.build(self.sweep, planted.CORE, created="2026-10-11")
        plain_m["capabilities"] = [c for c in plain_m["capabilities"] if c != xb.ROD_INTERACTION_CAPABILITY]
        del plain_m["reactivity"]["rodInteraction"]
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            xb.write_library(folder, plain_m, blobs, validate=True)
            with self.assertRaises(ri.PinError):
                ri.RIModel(folder)


if __name__ == "__main__":
    unittest.main()
