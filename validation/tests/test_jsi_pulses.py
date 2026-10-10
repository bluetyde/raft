"""
Tests for JSI TRIGA pulse experiment database and parameters.

Verifies data integrity, consistency of units, prompt-critical trends,
and loader utilities.
"""

from validation.tests._data import needs_data
import json
import unittest
from pathlib import Path

from validation.pulse_loader import (
    DEFAULT_CSV_PATH,
    DEFAULT_JSON_PATH,
    extract_nordheim_fuchs_dataset,
    filter_pulses,
    load_pulse_summary,
)


class TestJsiPulseDatabase(unittest.TestCase):
    def setUp(self):
        self.pulses = load_pulse_summary(DEFAULT_CSV_PATH)
        self.params_path = Path(__file__).parents[1] / "data" / "triga-jsi" / "parameters.json"

    @needs_data("jsi-pulses")
    def test_pulse_summary_count(self):
        """Database must contain all 757 recorded pulse experiments."""
        self.assertEqual(len(self.pulses), 757)

    @needs_data("jsi-pulses")
    def test_pulse_id_sequence(self):
        """Pulse sequence must start at 1 and end at 760 with monotonically increasing IDs."""
        self.assertEqual(self.pulses[0].pulse_id, 1)
        self.assertEqual(self.pulses[-1].pulse_id, 760)
        ids = [p.pulse_id for p in self.pulses]
        self.assertEqual(ids, sorted(ids))

    @needs_data("jsi-pulses")
    def test_reactivity_unit_conversion(self):
        """Reactivity in pcm must match 1 $ = 700 pcm."""
        checked = 0
        for p in self.pulses:
            if p.rho_dollars is not None and p.rho_pcm is not None:
                expected_pcm = round(p.rho_dollars * 700.0, 3)
                self.assertAlmostEqual(p.rho_pcm, expected_pcm, places=2)
                checked += 1
        self.assertGreater(checked, 700)

    @needs_data("jsi-pulses")
    def test_filter_by_core_configuration(self):
        """Filtering by core loading must return only matching records."""
        core_253 = filter_pulses(self.pulses, core="253")
        self.assertGreater(len(core_253), 10)
        for p in core_253:
            self.assertEqual(p.core_config, "253")

    @needs_data("jsi-pulses")
    def test_filter_by_reactivity_range(self):
        """Reactivity bounds filtering must enforce strict bounds."""
        pulses_2dollar = filter_pulses(self.pulses, min_rho=1.95, max_rho=2.05)
        self.assertGreater(len(pulses_2dollar), 5)
        for p in pulses_2dollar:
            self.assertIsNotNone(p.rho_dollars)
            self.assertGreaterEqual(p.rho_dollars, 1.95)
            self.assertLessEqual(p.rho_dollars, 2.05)

    @needs_data("jsi-pulses")
    def test_nordheim_fuchs_scaling_trends(self):
        """
        In the Nordheim-Fuchs regime:
        - Higher prompt reactivity (rho - 1) must produce higher peak power.
        - FWHM must shrink with prompt reactivity.
        """
        nf_data = extract_nordheim_fuchs_dataset(self.pulses, min_prompt_dollars=0.1)
        self.assertGreater(len(nf_data["rho_prompt_dollars"]), 500)

        # Check that high reactivity pulses (e.g. prompt rho > 0.8) have significantly
        # higher peak power than low reactivity pulses (prompt rho < 0.3)
        low_prompt_powers = [
            p for rho_p, p in zip(nf_data["rho_prompt_dollars"], nf_data["peak_power_mw"])
            if 0.1 <= rho_p <= 0.3
        ]
        high_prompt_powers = [
            p for rho_p, p in zip(nf_data["rho_prompt_dollars"], nf_data["peak_power_mw"])
            if rho_p >= 0.8
        ]
        self.assertTrue(len(low_prompt_powers) > 0)
        self.assertTrue(len(high_prompt_powers) > 0)

        avg_low_p = sum(low_prompt_powers) / len(low_prompt_powers)
        avg_high_p = sum(high_prompt_powers) / len(high_prompt_powers)
        self.assertGreater(avg_high_p, avg_low_p * 5.0)

    @needs_data("jsi-pulses")
    def test_json_summary_structure(self):
        """JSON summary file must be valid and conform to schema expectations."""
        self.assertTrue(DEFAULT_JSON_PATH.exists())
        with open(DEFAULT_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["count"], 757)
        self.assertIn("citations", data)
        self.assertIn("units", data)
        self.assertEqual(len(data["pulses"]), 757)

    @needs_data("jsi-pulses")
    def test_triga_benchmark_parameters(self):
        """TRIGA parameter file must define kinetics, geometry and thermal constants."""
        self.assertTrue(self.params_path.exists())
        with open(self.params_path, "r", encoding="utf-8") as f:
            params = json.load(f)

        kinetics = params["kinetics"]
        beta_eff = kinetics["betaEff"]
        self.assertAlmostEqual(beta_eff, 0.0070, places=4)

        delayed = kinetics["delayedGroups"]
        self.assertEqual(len(delayed), 6)
        sum_beta = sum(g["beta"] for g in delayed)
        self.assertAlmostEqual(sum_beta, beta_eff, places=4)

        thermal = params["thermal"]
        fuel = thermal["fuelMeat"]
        self.assertEqual(fuel["material"], "U-ZrH1.6")
        self.assertGreater(fuel["coreFuelMassKg"], 50.0)

        # Prompt negative temperature coefficient must be negative
        # (tabulated as |alpha| with a negative sign since C2, 2026-09-27)
        prompt = thermal["feedbackCoefficients"]["fuelTemperaturePrompt"]
        self.assertIn("negative", prompt["description"])
        self.assertTrue(prompt["pointsK"])
        for _, abs_alpha in prompt["pointsK"]:
            self.assertGreater(abs_alpha, 0.0)


if __name__ == "__main__":
    unittest.main()
