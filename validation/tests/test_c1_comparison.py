"""Tests for the C1 comparison helpers (fast; the full run is `python -m validation.c1_comparison`)."""
from __future__ import annotations
from validation.tests._data import needs_data

import math
import unittest

from physics_ref import Engine
from validation.c1_comparison import (P0_DEFAULT, _fresh_library, core_pulses, mean, rms, simulate,
                                      transient_start_position)


class TestC1Helpers(unittest.TestCase):
    def test_start_position_inserts_exactly_the_requested_dollars(self):
        lib = _fresh_library(1.0)
        w = lib.rod_by_id["transient"].worth
        for d in (1.05, 1.3, 1.77, 2.0):
            x0 = transient_start_position(lib, d)
            self.assertAlmostEqual((w(1.0) - w(x0)) / lib.beta_total, d, places=9)

    def test_too_many_dollars_is_refused(self):
        with self.assertRaises(ValueError):
            transient_start_position(_fresh_library(1.0), 5.0)

    def test_feedback_scale_changes_only_the_fuel_table(self):
        a, b = _fresh_library(1.0), _fresh_library(2.0)
        self.assertEqual([2 * y for y in a.fuel_temp.ys], b.fuel_temp.ys)
        self.assertEqual(a.cool_temp.ys, b.cool_temp.ys)
        self.assertEqual(b.ext_source, 0.0)

    def test_pre_pulse_state_is_critical(self):
        lib = _fresh_library(1.0)
        x0 = transient_start_position(lib, 1.5)
        rods = {r.id: 1.0 for r in lib.rods}
        rods["transient"] = x0
        rho = 0.0
        for r in lib.rods:
            rho += r.worth(rods[r.id])
        lib.calibration = -(lib.ref_rho + rho)
        lib.mark_modified("test")
        e = Engine(lib, {"rods": rods, "mode": "pulse", "power": {"mode": "critical-equilibrium", "value": P0_DEFAULT}})
        self.assertEqual(e.reactivity(0.0, e.y)["total"], 0.0)
        e.advance(0.2)
        # 1 W for 0.2 s heats the fuel ~7e-6 K; that feedback (~ -7.5e-10) lowers power by ~1e-7. Anything much larger is wrong.
        self.assertLess(abs(e.y[0] / P0_DEFAULT - 1.0), 1e-6)

    @needs_data("jsi-pulses")
    def test_split_and_selection(self):
        p = core_pulses("246")
        self.assertEqual(len(p), 148)
        self.assertTrue(all(q.rho_dollars >= 1.05 for q in p))
        odd = [q for q in p if q.pulse_id % 2 == 1]
        even = [q for q in p if q.pulse_id % 2 == 0]
        self.assertEqual(len(odd) + len(even), 148)
        self.assertFalse({q.pulse_id for q in odd} & {q.pulse_id for q in even})

    def test_metrics(self):
        self.assertAlmostEqual(rms([3.0, -4.0]), math.sqrt(12.5))
        self.assertAlmostEqual(mean([1.0, -3.0]), -1.0)
        self.assertIsNone(rms([]))

    def test_higher_dollars_give_a_bigger_pulse(self):
        lo, hi = simulate(1.5), simulate(2.0)
        self.assertGreater(hi.peak_power_w, lo.peak_power_w)
        self.assertLess(hi.peak_time_s, lo.peak_time_s)


if __name__ == "__main__":
    unittest.main()
