"""Tests for validation/m7_fuel_coefficient.py on a synthetic library and planted core 134 data (the real Table IX is read once, by the script)."""
from __future__ import annotations

import unittest

from validation import m7_fuel_coefficient as fc
from validation import m7_power_ascension as base
from validation.tests.test_m7_hot_element import lib_with_shapes

GAMMA_B, GAMMA_A, T0C = 1.525, 1.575, 21.6
P = [0.0, 5.3, 14.1, 27.1, 45.3, 61.6, 79.4, 95.0, 112.0, 135.0, 160.2, 181.8, 207.7, 235.9, 250.0]


def synthetic():
    lib = lib_with_shapes()
    lib.hA, lib.hA_exponent, lib.hA_dt_ref = 2000.0, 0.25, 100.0
    return lib


def planted(lib, name="core242", n_true=None, ratio=1.0):
    """A Table IX built from the library's own law (scaled to 48 positions) and linear water warming, so the metrics have known answers.
    With n_true the rise follows another exponent instead. The synthetic tables are linear: fuel -10 pcm/K, coolant +4 pcm/K."""
    scale = fc.POSITIONS["primary"] / fc.POSITIONS_LIB[name]
    water = [fc.WATER_RISE_K * i / (len(P) - 1) for i in range(len(P))]
    rows, cum = [], 0.0
    for i, p in enumerate(P):
        if p == 0:
            rise = 0.0
        elif n_true is None:
            rise = ratio * fc.predicted_rise_k(p, lib.hA, lib.hA_exponent, scale)
        else:
            rise = ratio * 20.0 * p ** (1.0 / (1.0 + n_true))
        t_mean = rise + water[i]
        loss = 10.0 * (rise + water[i]) - 4.0 * water[i]
        d = loss - cum
        cum = loss
        rows.append([i, p, T0C + GAMMA_A * t_mean, T0C + GAMMA_B * t_mean, -d, -loss])
    rows[-1][4] = rows[-1][5] = None
    return {"conditions": {"T0C": T0C}, "conversion": {"gammaA": GAMMA_A, "gammaB": GAMMA_B}, "steps": rows}


class Measured(unittest.TestCase):
    def test_the_data_file_is_the_paper_table(self):
        d = fc.load_steps()
        self.assertEqual(len(d["steps"]), 15)
        self.assertEqual(d["steps"][13][5], -1276.3)
        self.assertAlmostEqual(d["conversion"]["gammaB"], 1.525)
        self.assertAlmostEqual(d["conversion"]["gammaA"], 1.575)

    def test_mean_temperature_and_water_profiles(self):
        steps = planted(synthetic())["steps"]
        t = fc.mean_fuel_temps_k(steps, 3, GAMMA_B, T0C)
        self.assertAlmostEqual(t[0], T0C + base.K0)
        self.assertAlmostEqual(t[14] - base.K0, T0C + (steps[14][3] - T0C) / GAMMA_B)
        self.assertEqual(fc.water_rise("none", steps), [0.0] * 15)
        lin, cum = fc.water_rise("linear", steps), fc.water_rise("cumulative", steps)
        self.assertAlmostEqual(lin[14], 8.0)
        self.assertAlmostEqual(cum[14], 8.0)
        self.assertLess(cum[3], lin[3])           # the steps are small at first, so the energy-like warming lags the linear one


class Feedback(unittest.TestCase):
    def test_tables_arithmetic_and_labels(self):
        lib = synthetic()
        out = fc.feedback_cases(lib, planted(lib), "gammaB", 3, "linear")
        for step in out["A"]["perStep"]:
            self.assertAlmostEqual(step["modelPcm"], step["measuredPcm"], places=5)
            self.assertEqual(step["label"], "good")
        self.assertEqual([fc.label_cumulative(m, 500.0) for m in (550, 551, 625, 626)], ["good", "plausible", "plausible", "fails"])
        self.assertEqual(fc.label_cumulative(40.0, 49.6), "good")          # inside the 10 pcm floor
        self.assertEqual(fc.label_cumulative(70.0, 49.6), "plausible")      # 20.4 pcm: inside 25 pcm
        self.assertEqual(fc.label_cumulative(80.0, 49.6), "fails")


class HeatTransfer(unittest.TestCase):
    def test_the_exponent_and_the_absolute_scale_are_recovered(self):
        lib = synthetic()
        out = fc.heat_cases(lib, "core242", planted(lib), "gammaB", 3, "linear", "primary")
        self.assertAlmostEqual(out["n134"], 0.25, places=3)          # the water term is removed, so the planted law comes back
        self.assertEqual(out["D"]["label"], "good")
        self.assertEqual(out["E"]["worst"], "good")
        self.assertAlmostEqual(out["E"]["ratioMin"], 1.0, places=6)
        steeper = fc.heat_cases(lib, "core242", planted(lib, n_true=0.55), "gammaB", 3, "linear", "primary")
        self.assertAlmostEqual(steeper["n134"], 0.55, places=3)
        self.assertEqual(steeper["D"]["label"], "fails")
        hot = fc.heat_cases(lib, "core242", planted(lib, ratio=1.6), "gammaB", 3, "linear", "primary")
        self.assertEqual(hot["E"]["worst"], "fails")
        self.assertLess(hot["E"]["ratioMax"], 1.0)                   # the model is too cold against a 1.6 times hotter measurement

    def test_a_degenerate_fit_is_not_computed(self):
        self.assertIsNone(fc.fit_exponent([10.0, 20.0, 30.0], [5.0, 5.0, 5.0]))
        self.assertIsNone(fc.fit_exponent([0.0, 10.0], [1.0, 2.0]))


class Secondary(unittest.TestCase):
    def test_slopes_and_the_two_2002_comparisons(self):
        lib = synthetic()
        sec = fc.secondary(lib, "core242")
        self.assertAlmostEqual(sec["slopes"]["first-interval"]["fuelPerMeanK"], -10.0, places=6)
        self.assertAlmostEqual(sec["slopes"]["first-interval"]["isothermal"], -6.0, places=6)
        self.assertGreater(sec["rB"], 1.0)
        entry = fc.evaluate_library(lib, "core242", planted(lib))
        self.assertEqual(entry["B"]["primary"]["label"], "fails")                  # -6.0 against +3.5
        self.assertAlmostEqual(entry["C"]["primary"]["perBRingK"], -10.0 / GAMMA_B, places=6)
        self.assertEqual(entry["C"]["primary"]["label"], "plausible")                # 1.76 against the 1.0 and 2.4 bands


class Decision(unittest.TestCase):
    @staticmethod
    def entry(a="good", d="good", e="good"):
        return {"A": {"primary": {"worst": a}}, "D": {"primary": {"label": d}}, "E": {"primary": {"worst": e}},
                "B": {"primary": {"label": "good"}}, "C": {"primary": {"label": "good"}}}

    def test_the_branches(self):
        self.assertIn("transfers", fc.decide(self.entry())["heatTransfer"])
        self.assertIn("exponent does not", fc.decide(self.entry(d="fails"))["heatTransfer"])
        self.assertIn("specific", fc.decide(self.entry(e="fails", d="good"))["heatTransfer"])
        self.assertTrue(fc.decide(self.entry(a="fails"))["feedback"].startswith("fails"))

    def test_the_full_run_has_the_documented_shape(self):
        lib = synthetic()
        report = fc.run({"core242": lib, "core246": lib}, planted(lib))
        e = report["libraries"]["core246"]
        for key in ("A", "B", "C", "D", "E", "F", "decision", "secondary"):
            self.assertIn(key, e)
        self.assertEqual(len(e["A"]["cases"]), 6)                                       # 2 thermocouples x 3 water profiles


class RealLibrariesLoad(unittest.TestCase):
    def test_the_libraries_carry_the_law_and_the_grids_the_protocol_states(self):
        for name, path in base.LIBRARIES.items():
            lib = base.load_library(path)
            self.assertGreater(lib.hA_exponent, 0.0, name)
            self.assertEqual(lib.fuel_temp.xs[:2], [294.0, 400.0], name)
            self.assertEqual(lib.cool_temp.xs, [294.0, 313.15, 333.15], name)
            self.assertEqual(fc.powered_elements(lib), fc.POSITIONS_LIB[name], name)


if __name__ == "__main__":
    unittest.main()
