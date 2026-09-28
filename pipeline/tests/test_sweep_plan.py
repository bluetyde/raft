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


class SummaryCompletenessTests(unittest.TestCase):
    """M2 Codex review (2026-09-28), finding 9: one core's missing case must not mark another core incomplete."""

    def test_missing_case_is_counted_per_core(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        lost = sweep.plan("242")[3]["name"]
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(sweep, "build_case", lambda c, stats: (c["name"], ["A1"])), \
                mock.patch.object(sweep.cache, "openmc_inputs", lambda model, wd: {"name": model.encode()}), \
                mock.patch.object(sweep.cache, "openmc_data_files", lambda model: []), \
                mock.patch.object(sweep.cache, "data_digest", lambda files, root: "d"), \
                mock.patch.object(sweep.cache, "openmc_versions", lambda: {}), \
                mock.patch.object(sweep.cache, "case_key", lambda inputs, d, v: inputs["name"].decode()), \
                mock.patch.object(sweep.cache, "is_complete", lambda d, verify: d.name != lost), \
                mock.patch.object(sweep.cache, "derived", lambda *a, **k: {}):
            rc = sweep.summary(["242", "246"], sweep.STANDARD, Path(t), Path(t) / "out")
            s242 = json.loads((Path(t) / "out" / "sweep_242.json").read_text(encoding="utf-8"))
            s246 = json.loads((Path(t) / "out" / "sweep_246.json").read_text(encoding="utf-8"))
        self.assertEqual(rc, 1)
        self.assertFalse(s242["complete"])
        self.assertTrue(s246["complete"])
        self.assertEqual(len(s246["cases"]), len(sweep.plan("246")))


if __name__ == "__main__":
    unittest.main()
