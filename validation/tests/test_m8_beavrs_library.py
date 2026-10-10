"""Tests for validation/m8_beavrs_library.py on a planted library: the real library is analysed once, by the script.

The library is built by the real exporter from a planted separable sweep (pipeline/tests/test_export_beavrs.py): known linear bank worths, known
temperature and boron slopes. The analysis must recover the planted numbers, refuse another manifest, and say "not computed" outside the domain.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.library import export_beavrs as xb
from pipeline.tests import test_export_beavrs as planted
from validation import m8_beavrs_hzp as t11
from validation import m8_beavrs_library as lb


def build(interaction=0.0):
    rows = planted.make_rows(interaction)
    m, blobs, _ = xb.build(rows, planted.CORE, created="2026-10-10")
    d = tempfile.TemporaryDirectory()
    folder = Path(d.name) / "lib"
    xb.write_library(folder, m, blobs)
    return d, folder, rows


def planted_critical(state: int) -> float:
    """The planted critical boron, from the planted constants only."""
    rho = planted.RHO0
    for b in t11.banks_in(state):
        rho -= planted.W[b] * planted.x_frac(planted.REF_STEPS[b])          # the bank goes from its reference position to 0
    return 975.0 + rho / -planted.BORON_SLOPE


class PlantedAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.folder, cls.rows = build()
        cls.model = lb.Model(cls.folder, expect_digest=None)
        cls.m = lb.analyse(cls.model, cls.rows)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_critical_boron_matches_the_planted_value_at_every_state(self):
        for s, e in self.m["A"].items():
            self.assertTrue(e["computed"], s)
            self.assertAlmostEqual(e["criticalPpm"], planted_critical(s), places=2)
            self.assertAlmostEqual(e["errorPpm"], e["criticalPpm"] - t11.CB[s][0], places=9)
        self.assertAlmostEqual(self.m["A"][0]["criticalPpm"], 975.0 + planted.RHO0 / -planted.BORON_SLOPE, places=2)

    def test_sequential_worths_and_the_total_are_the_planted_worths(self):
        total = 0.0
        for b in t11.BANKS:
            want = planted.W[b] * planted.x_frac(planted.REF_STEPS[b]) * lb.PCM
            self.assertAlmostEqual(self.m["B"]["banks"][b]["worthPcm"], want, places=4)
            total += want
        self.assertAlmostEqual(self.m["B"]["total"]["worthPcm"], total, places=3)
        self.assertEqual(self.m["B"]["banks"]["C"]["label"], "fails")           # 2800 against the measured 1203: far outside its band

    def test_the_itc_is_the_planted_slope_with_fuel_and_coolant_shifted_together(self):
        want = (planted.FUEL_SLOPE + planted.WATER_SLOPE) * (2 * t11.T_STEP) * lb.PCM / t11.DELTA_F
        for s in (0, 2):
            self.assertAlmostEqual(self.m["C"][s]["itcPcmPerF"], want, places=3)

    def test_a_separable_sweep_has_no_difference_from_its_source(self):
        for c, e in self.m["F"].items():
            self.assertTrue(e["computed"], c)
            self.assertAlmostEqual(e["differencePcm"], 0.0, places=3)
            self.assertFalse(e["exceeds"])

    def test_a_planted_interaction_shows_up_as_the_difference_and_trips_the_limit(self):
        tmp, folder, rows = build(interaction=-4.0e-4)
        try:
            m = lb.analyse(lb.Model(folder, expect_digest=None), rows)
        finally:
            tmp.cleanup()
        self.assertAlmostEqual(m["F"]["J-W2"]["differencePcm"], 40.0, places=2)         # one interaction unit, +40 pcm: the library is less negative
        self.assertAlmostEqual(m["F"]["J-W7"]["differencePcm"], 240.0, places=2)
        self.assertFalse(m["F"]["J-W2"]["exceeds"])                                      # under the 100 pcm floor
        self.assertTrue(m["F"]["J-W4"]["exceeds"] or m["F"]["J-W7"]["exceeds"])
        self.assertTrue(m["F"]["J-W7"]["exceeds"])
        self.assertTrue(any(i.startswith("4. the summed tables differ") for i in m["decision"]["items"]))

    def test_the_error_of_a_state_includes_every_table_it_uses(self):
        rods = self.model.rods(0)
        base = self.model.sigma(rods, 975.0)
        at = self.model.sigma(rods, 1300.0)
        unc = lb._interp(*self.model.unc_boron, 1300.0) * lb.PCM
        self.assertGreater(unc, 0.0)
        self.assertAlmostEqual(at ** 2 - base ** 2, unc ** 2, places=6)               # the boron table's error enters in quadrature
        both = self.model.sigma(self.model.rods(2), 975.0)
        self.assertGreater(both, base)                                                  # two banks in: two more rod tables with an error

    def test_another_manifest_is_refused(self):
        with self.assertRaises(lb.DigestError):
            lb.Model(self.folder)                                                         # the protocol's digest is the real library's

    def test_a_critical_boron_outside_the_domain_is_not_computed_and_enters_nothing(self):
        m = lb.analyse(self.model, self.rows, bounds=(900.0, 1600.0))
        self.assertFalse(m["A"][7]["computed"])
        self.assertTrue(m["A"][0]["computed"])
        self.assertTrue(any(i.startswith("5. not computed") and "A:S7" in i for i in m["decision"]["items"]))

    def test_the_decision_names_the_states_that_pass(self):
        items = self.m["decision"]["items"]
        self.assertTrue(items[0].startswith("1."))
        self.assertTrue(items[-1].startswith("6. the library status stays experimental"))


if __name__ == "__main__":
    unittest.main()
