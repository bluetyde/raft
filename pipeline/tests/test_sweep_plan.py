"""The M2 sweep's case list (pipeline/openmc/sweep.py): deterministic, no duplicates, reference excluded from the rod grids.
Needs no OpenMC (plan() only builds dicts)."""
from __future__ import annotations

import unittest
from collections import Counter

from pipeline.openmc import sweep


class SweepPlanTests(unittest.TestCase):
    def test_counts_per_family(self):
        for core in ("242", "246"):
            fam = Counter(c["family"] for c in sweep.plan(core))
            ref = sweep.REFERENCE_RODS[core]
            n_rod = sum(1 for r, g in sweep.ROD_GRID.items() for s in g if float(s) != ref[r])
            self.assertEqual(fam, Counter({"reference": 1, "rod-worth": n_rod, "fuel-temp": len(sweep.TFUEL_GRID),
                                           "coolant-temp": len(sweep.TCOOL_GRID), "holdout": sweep.HOLDOUT_N}))

    def test_no_duplicate_states_and_reference_not_in_rod_grid(self):
        for core in ("242", "246"):
            names = [c["name"] for c in sweep.plan(core)]
            self.assertEqual(len(names), len(set(names)))
            ref = sweep.REFERENCE_RODS[core]
            for c in sweep.plan(core):
                if c["family"] == "rod-worth":
                    moved = [r for r in ref if c["rods"][r] != ref[r]]
                    self.assertEqual(moved, [c["rod"]])

    def test_holdout_is_deterministic_and_inside_the_grid(self):
        a = [c for c in sweep.plan("242") if c["family"] == "holdout"]
        b = [c for c in sweep.plan("242") if c["family"] == "holdout"]
        self.assertEqual(a, b)                           # the same states every run, so the cache can reuse them
        for c in a:
            self.assertTrue(0 <= c["rods"]["T"] <= 900 and all(200 <= c["rods"][r] <= 900 for r in "KVR"))
            self.assertTrue(294.0 <= c["tfuel"] <= 600.0)
        self.assertNotEqual([c["rods"] for c in a], [c["rods"] for c in sweep.plan("246") if c["family"] == "holdout"])

    def test_sample_takes_one_per_family(self):
        s = sweep.sample(sweep.plan("242") + sweep.plan("246"))
        self.assertEqual(len(s), 10)
        self.assertEqual(len({(c["core"], c["family"]) for c in s}), 10)


if __name__ == "__main__":
    unittest.main()
