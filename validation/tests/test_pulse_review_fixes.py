"""Synthetic checks for the code-review fixes in the pulse loader, screening, comparison and trace scripts (no measured data needed)."""
from __future__ import annotations

import unittest
from unittest import mock

from validation import trace_period
from validation.pulse_loader import _parse_row
from validation.pulse_screening import screen_pulses


def record(pid, rho="0.9", peak="10", core="242"):
    return _parse_row({"pulse_id": str(pid), "date": "01.01.2000", "rho_dollars": rho, "peak_power_mw": peak, "core_config": core})


class TestLoader(unittest.TestCase):
    def test_a_typo_names_the_pulse_and_column(self):
        with self.assertRaisesRegex(ValueError, "pulse 7: column rho_dollars is not a number"):
            _parse_row({"pulse_id": "7", "date": "d", "rho_dollars": "1,2"})
        with self.assertRaisesRegex(ValueError, "not finite"):
            _parse_row({"pulse_id": "7", "date": "d", "peak_power_mw": "nan"})

    def test_blank_and_none_stay_missing(self):
        r = _parse_row({"pulse_id": "7", "date": "d", "rho_dollars": "", "peak_power_mw": "None"})
        self.assertIsNone(r.rho_dollars)
        self.assertIsNone(r.peak_power_mw)


class TestScreening(unittest.TestCase):
    def test_an_excluded_pulse_does_not_set_the_group_median(self):
        # one valid pulse at 10 MW with two impossible ones (sub-prompt, 100 and 110 MW) at the same reactivity: the valid one is not an outlier
        recs = [record(1, peak="10"), record(2, peak="100"), record(3, peak="110")]
        res = screen_pulses(recs)
        self.assertEqual([p.pulse_id for p in res.kept], [1])
        self.assertEqual(res.reason_counts.get("group_outlier", 0), 0)

    def test_duplicate_ids_are_refused(self):
        with self.assertRaisesRegex(ValueError, "duplicate pulse ids"):
            screen_pulses([record(1), record(1, peak="0")])

    def test_a_pulse_with_no_core_is_excluded_with_a_reason(self):
        res = screen_pulses([record(1, core=""), record(2)])
        self.assertEqual([p.pulse_id for p in res.kept], [2])
        self.assertEqual(res.excluded, [(1, ["missing_core_config"])])
        self.assertEqual(sum(c["total"] for c in res.cores) - sum(c["kept"] for c in res.cores), sum(c["excluded"] for c in res.cores))


class TestTraceCurve(unittest.TestCase):
    def test_a_failed_grid_fit_or_a_non_increasing_curve_is_refused(self):
        with mock.patch.object(trace_period, "engine_trace", return_value=[0.0]):
            with mock.patch.object(trace_period, "fit_omega", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "gap"):
                    trace_period.model_curve()
            with mock.patch.object(trace_period, "fit_omega", return_value=(5.0, 10, 0.0)):
                with self.assertRaisesRegex(RuntimeError, "not increasing"):
                    trace_period.model_curve()


class TestComparison(unittest.TestCase):
    def test_the_library_passed_in_is_the_one_simulated(self):
        from physics_ref import Library
        from validation.pulse_comparison import DEFAULT_LIBRARY_PATH, simulate_pulse
        base = Library(DEFAULT_LIBRARY_PATH)
        other = Library(DEFAULT_LIBRARY_PATH)
        other.beta_total = other.beta_total * 1.2   # a different library: the pulse must come out different
        a = simulate_pulse(base, 1.5, max_t=0.3).peak_power_mw
        b = simulate_pulse(other, 1.5, max_t=0.3).peak_power_mw
        self.assertNotAlmostEqual(a, b, places=3)
        self.assertEqual(simulate_pulse(base, 1.5, max_t=0.3).peak_power_mw, a)   # and the copy left the original untouched


if __name__ == "__main__":
    unittest.main()
