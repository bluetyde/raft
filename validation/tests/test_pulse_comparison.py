"""
Unit tests for JSI TRIGA pulse comparison and M1 validation module.

Verifies:
- Prompt-critical pulse simulation with physics_ref.Engine.
- Agreement between simulation and Nordheim-Fuchs theoretical limits.
- Monotonic power scaling with prompt reactivity.
- Experimental dataset matching and the summary structure (no automatic verdict).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from physics_ref import Library
from validation.pulse_comparison import (
    DEFAULT_LIBRARY_PATH,
    run_pulse_comparison,
    simulate_pulse,
)


class TestPulseComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = Library(DEFAULT_LIBRARY_PATH)

    def test_simulate_pulse_prompt_critical(self):
        """Simulate a 1.50 $ ($0.50 prompt excess) pulse and verify burst parameters."""
        sim = simulate_pulse(self.lib, 1.50, initial_power=10.0, max_t=0.6)

        self.assertAlmostEqual(sim.rho_dollars, 1.50, places=2)
        self.assertAlmostEqual(sim.rho_prompt_dollars, 0.50, places=2)
        # Windows from Fuchs-Hansen with Vavtar & Snoj 2021's own inputs (gamma = 2.1e-9 /J, Lambda = 4e-5 s,
        # beta = 0.007): rho' = 0.0035 gives Pmax = rho'^2 / (2 gamma Lambda) = 72.9 MW and E = 2 rho' / gamma = 3.33 MWs.
        # Their improved model sits below FH in Pmax and above it in energy (their Fig. 4), hence the asymmetric windows.
        fh_pmax, fh_energy = 0.0035 ** 2 / (2 * 2.1e-9 * 4e-5) / 1e6, 2 * 0.0035 / 2.1e-9 / 1e6
        self.assertGreater(sim.peak_power_mw, 0.75 * fh_pmax)
        self.assertLess(sim.peak_power_mw, 1.10 * fh_pmax)
        self.assertGreater(sim.energy_mws, 1.0 * fh_energy)
        self.assertLess(sim.energy_mws, 1.6 * fh_energy)
        # FWHM should be approximately 30-50 ms
        self.assertIsNotNone(sim.fwhm_s)
        self.assertGreater(sim.fwhm_s, 0.025)
        self.assertLess(sim.fwhm_s, 0.060)
        # Fuel temperature rise must be positive
        self.assertGreater(sim.delta_tf_c, 50.0)

    def test_nordheim_fuchs_agreement(self):
        """Simulated peak power should agree with Nordheim-Fuchs within delayed-return margin (15%)."""
        sim = simulate_pulse(self.lib, 1.60, initial_power=10.0, max_t=0.6)
        # Theoretical NF without delayed return vs simulated with delayed return and cp(T)
        self.assertGreater(sim.nf_peak_power_mw, 0.0)
        discrepancy = abs(sim.peak_power_mw - sim.nf_peak_power_mw) / sim.nf_peak_power_mw
        self.assertLess(discrepancy, 0.15)

    def test_prompt_scaling_monotonicity(self):
        """Higher prompt reactivity must produce monotonically higher peak power and shorter FWHM."""
        p_140 = simulate_pulse(self.lib, 1.40)
        p_170 = simulate_pulse(self.lib, 1.70)
        p_200 = simulate_pulse(self.lib, 2.00)

        self.assertLess(p_140.peak_power_mw, p_170.peak_power_mw)
        self.assertLess(p_170.peak_power_mw, p_200.peak_power_mw)

        self.assertGreater(p_140.fwhm_s, p_170.fwhm_s)
        self.assertGreater(p_170.fwhm_s, p_200.fwhm_s)

    def test_comparison_summary_has_no_automatic_verdict(self):
        """The comparison reports numbers and the full sim/exp ratio range, never a GO/NO-GO (review 2026-09-26)."""
        summary = run_pulse_comparison(
            library_path=DEFAULT_LIBRARY_PATH,
            rho_sweep=[1.50, 1.80, 2.00],
        )

        self.assertEqual(summary.library_id, "triga-jsi")
        self.assertEqual(len(summary.points), 3)
        self.assertGreater(summary.total_experimental_pulses_matched, 50)
        self.assertIsNone(summary.verdict)
        self.assertIn("No automatic verdict", summary.note)
        self.assertIsNotNone(summary.pmax_ratio_min)
        self.assertLessEqual(summary.pmax_ratio_min, summary.pmax_ratio_max)

        point_200 = next(p for p in summary.points if abs(p.rho_dollars - 2.00) < 1e-4)
        self.assertIsNotNone(point_200.exp_pmax_median_mw)
        self.assertGreater(point_200.exp_count, 10)


if __name__ == "__main__":
    unittest.main()
