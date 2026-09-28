"""pin_depletion.kept_densities (M2 Codex review 2026-09-28, finding 12): invalid densities are errors, not dropped nuclides.
Needs no OpenMC."""
from __future__ import annotations

import math
import unittest

from pipeline.openmc import pin_depletion as pd


class KeptDensitiesTests(unittest.TestCase):
    def test_keeps_positive_drops_trace_and_roundoff(self):
        out = pd.kept_densities({"U235": 3e-4, "Kr83": 1e-14, "Fe56": -5e-17}, 10.0)
        self.assertEqual(out, {"U235": 3e-4})

    def test_nan_or_inf_is_an_error(self):
        for bad in (math.nan, math.inf):
            with self.assertRaises(ValueError) as ctx:
                pd.kept_densities({"U235": bad, "U238": 1e-3}, 4.0)
            self.assertIn("U235", str(ctx.exception))
            self.assertIn("4.0", str(ctx.exception))

    def test_clearly_negative_is_an_error(self):
        with self.assertRaises(ValueError):
            pd.kept_densities({"Pu239": -1e-6}, 2.0)


if __name__ == "__main__":
    unittest.main()
