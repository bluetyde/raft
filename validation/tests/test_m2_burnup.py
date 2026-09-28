"""validation.m2_burnup.crossing_std (M2 Codex review 2026-09-28, finding 14): first-order propagation through the actual
interpolation, checked against finite differences at the midpoint and near an endpoint."""
from __future__ import annotations

import math
import unittest

from validation.m2_burnup import crossing_std


def fd_std(b0, b1, r0, r1, s0, s1, h=1e-4):
    B = lambda a, b: b0 + a / (a - b) * (b1 - b0)
    return math.hypot((B(r0 + h, r1) - B(r0 - h, r1)) / (2 * h) * s0, (B(r0, r1 + h) - B(r0, r1 - h)) / (2 * h) * s1)


class CrossingStdTests(unittest.TestCase):
    def test_matches_finite_differences(self):
        for r0, r1 in ((500.0, -500.0), (50.0, -950.0), (950.0, -50.0)):      # midpoint, near b0, near b1
            for s0, s1 in ((70.0, 70.0), (40.0, 90.0)):
                self.assertAlmostEqual(crossing_std(22.0, 24.0, r0, r1, s0, s1), fd_std(22.0, 24.0, r0, r1, s0, s1), places=6)

    def test_near_an_endpoint_the_nearer_point_dominates(self):
        # crossing near b0: its error is carried almost entirely by r0
        s = crossing_std(22.0, 24.0, 50.0, -950.0, 70.0, 0.0)
        self.assertAlmostEqual(s, 70.0 * 950.0 * 2.0 / 1000.0 ** 2, places=9)


if __name__ == "__main__":
    unittest.main()
