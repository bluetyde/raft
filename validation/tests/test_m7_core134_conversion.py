"""Tests for validation/m7_core134_conversion.py on synthetic ring temperatures, power shapes and planted measurements (the real data is read once, by the script)."""
from __future__ import annotations
from validation.tests._data import needs_data

import unittest

from physics_ref.library import Table
from validation import m7_core134_conversion as cv
from validation.tests.test_m7_fuel_coefficient import planted, synthetic

RADII = {"A": 0.0, "B": 4.0, "C": 8.0, "D": 12.0, "E": 16.0}
LOADING = {"fuel": {"A1": "1", "B1": "2", "B5": "3", "C1": "4", "D2": "5", "E1": "6"}, "other": {"C10": "safety rod (fuelled follower 7178)", "E7": "neutron source"}}


def rings(a=244.0, b=237.0, c=221.0, d=206.0, e=184.0):
    return {"A-1": {"250": a, "125": a - 60}, "B-2": {"250": b + 3, "125": b - 60}, "B-5": {"250": b - 3, "125": None},
            "C-8": {"250": c + 3, "125": c - 60}, "C-9": {"250": c - 3, "125": None}, "D-11": {"250": d + 5, "125": d - 60},
            "D-13": {"250": d - 5, "125": None}, "E-14": {"250": e, "125": e - 60}}


def shapes_lib():
    """Three elements A1, B5, C1 (all powered), bins: below the core, then three bins of the active height (17.78, 2.54, 17.78 cm)."""
    lib = synthetic()
    edges = [-57.15, -19.05, -1.27, 1.27, 19.05]
    base_arr = [0.0, 0.10, 0.20, 0.10,        # A1: 0.4 of the power, peaked at the midplane
                0.0, 0.05, 0.10, 0.05,        # B5: 0.2
                0.0, 0.10, 0.20, 0.10]        # C1: 0.4
    n = len(base_arr)
    lib.shapes = {"bins": {"elements": ["A1", "B5", "C1"], "axialEdgesCm": edges}, "base": "base", "rodDeltas": {},
                  "tempDelta": {"T": [294.0, 800.0], "array": "td"}}
    lib.arrays = {"base": base_arr, "td": [0.0] * (2 * n)}
    lib.ref_rods = {}
    return lib


class RadialFactor(unittest.TestCase):
    @needs_data("jsi-core134")
    def test_ring_values_and_the_weighted_means(self):
        r = cv.load_rings()
        self.assertEqual(r["A-1"], {"250": 244.0, "125": 176.0})
        self.assertIsNone(r["B-5"]["125"])
        v = cv.ring_values(rings(), "250")
        self.assertEqual(v, {"A": 244.0, "B": 237.0, "C": 221.0, "D": 206.0, "E": 184.0})
        self.assertEqual(cv.ring_values(rings(), "125")["B"], 177.0)                    # only B-2 is given at 125 kW
        fuel, followers = cv.fuel_positions(LOADING)
        self.assertEqual((len(fuel), followers), (6, ["C10"]))
        self.assertAlmostEqual(cv.mean_temperature(v, fuel, followers, "count", RADII), (244 + 237 * 2 + 221 * 2 + 206 + 184) / 7, places=9)   # A, B1, B5, C1, D2, E1 and the C10 follower
        self.assertAlmostEqual(cv.mean_temperature(v, fuel, followers, "count-no-followers", RADII), (244 + 237 * 2 + 221 + 206 + 184) / 6, places=9)
        flat = {r: 100.0 for r in "ABCDE"}
        self.assertAlmostEqual(cv.mean_temperature(flat, fuel, followers, "area", RADII), 100.0, places=9)

    def test_gamma_r_arithmetic_and_labels(self):
        fuel, followers = cv.fuel_positions(LOADING)
        g = cv.gamma_r(rings(), fuel, followers, RADII, "250", "count", 21.6)
        tbar = (244 + 237 * 2 + 221 * 2 + 206 + 184) / 7
        self.assertAlmostEqual(g["A"], (244 - 21.6) / (tbar - 21.6), places=9)
        self.assertAlmostEqual(g["B"], (234 - 21.6) / (tbar - 21.6), places=9)       # B-5 is 234
        self.assertEqual([cv.label_diff(x, cv.BANDS_G1) for x in (0.05, 0.051, 0.10, 0.101)], ["good", "plausible", "plausible", "differs"])
        res = cv.c1(rings(), LOADING, RADII)
        self.assertEqual(len(res["cases"]), 18)                                      # 3 T0 x 3 weightings x 2 powers


class ModelFactors(unittest.TestCase):
    def test_power_factors_and_the_temperature_exponent(self):
        lib = shapes_lib()
        m = cv.model_factors(lib, "A1", 0.0, "midplane")
        self.assertEqual(m["poweredElements"], 3)
        self.assertAlmostEqual(m["Fr"], 0.4 * 3, places=9)
        self.assertAlmostEqual(m["Fz"], (0.2 / 2.54) / (0.4 / 38.1), places=9)
        self.assertAlmostEqual(m["gamma"], m["Fr"] * m["Fz"], places=9)
        m22 = cv.model_factors(lib, "A1", 0.22, "midplane")
        self.assertAlmostEqual(m22["gamma"], (m["Fr"] * m["Fz"]) ** (1 / 1.22), places=9)
        three = cv.model_factors(lib, "B5", 0.0, "three-bins")
        self.assertAlmostEqual(three["Fz"], 1.0, places=9)                           # the three central bins are the whole active height here
        self.assertEqual(len(cv.c2(lib)["cases"]), 8)                                # 2 elements x 2 exponents x 2 axial choices


class Implied(unittest.TestCase):
    def test_the_conversion_that_made_the_data_is_recovered_and_a_weaker_table_needs_less(self):
        lib = synthetic()
        data = planted(lib)
        for step in (1, 4, 7):
            self.assertAlmostEqual(cv.implied_gamma(lib, data, 3, step), 1.525, places=3)
            self.assertAlmostEqual(cv.implied_gamma(lib, data, 2, step), 1.575, places=3)
        weak = synthetic()
        weak.fuel_temp = Table([294.0, 1200.0], [0.0, -5.0 * 906.0 / 1e5])           # half the fuel coefficient
        self.assertLess(cv.implied_gamma(weak, data, 3, 7), 1.525 * 0.7)
        self.assertEqual(cv.labels_for(lib, data, 1.525, 1.575)["primary"]["worst"], "good")

    def test_a_missing_root_makes_the_implied_conversion_incomplete_not_a_partial_mean(self):
        lib = synthetic()
        data = planted(lib)
        data["steps"][7][5] = -1.0e6                                                  # no conversion gives a million pcm at step 7
        res = cv.c3(lib, data, cv.c1(rings(), LOADING, RADII), cv.c2(shapes_lib()))
        im = res["implied"]["B"]
        self.assertIsNone(im["perStep"][7])
        self.assertFalse(im["complete"])
        self.assertIsNone(im["mean"])
        self.assertEqual(im["label"], "not computed")
        self.assertAlmostEqual(im["partialMean"], 1.525, places=3)                   # reported separately, never used
        c1, c2, _ = Implied.make()
        self.assertIsNone(cv.decide(c1, c2, res)["case"])

    def test_the_shortfall_removed_and_the_decision_branches(self):
        lib = synthetic()
        data = planted(lib)
        c1 = cv.c1(rings(), LOADING, RADII)
        c2 = cv.c2(shapes_lib())
        res = cv.c3(lib, data, c1, c2)
        self.assertAlmostEqual(res["implied"]["B"]["ratioToPaper"], 1.0, places=3)
        self.assertEqual(res["implied"]["B"]["label"], "good")
        self.assertAlmostEqual(res["step7"]["paper"]["fractionOfShortfallRemoved"], 0.0, places=9)

    @staticmethod
    def make(g1="good", g2="good", indep="good", paper="fails", g3="differs"):
        c1 = {"primary": {"labelA": g1, "labelB": g1}}
        c2 = {"primary": {"A": {"label": g2}, "B": {"label": g2}}}
        route = lambda l: {"primary": {"worst": l}}
        c3 = {"implied": {"B": {"label": g3}}, "routes": {"paper": route(paper), "table8-radial-times-paper-axial": route(indep), "model-power-factors": route(indep)},
              "step7": {k: {"fractionOfShortfallRemoved": 0.3} for k in ("paper", "table8-radial-times-paper-axial", "model-power-factors")}}
        return c1, c2, c3

    def test_the_decision_cases(self):
        self.assertEqual(cv.decide(*self.make())["case"], 1)                                        # independent conversion passes
        self.assertEqual(cv.decide(*self.make(indep="fails"))["case"], 2)                           # the paper's conversion is supported, the feedback is weak
        self.assertEqual(cv.decide(*self.make(g1="differs", indep="fails"))["case"], 3)             # the conversion is off but does not explain it
        self.assertIsNone(cv.decide(*self.make(g1="differs", indep="good"))["case"])


class RealData(unittest.TestCase):
    @needs_data("jsi-core134")
    def test_the_data_files_and_the_library_have_what_the_protocol_reads(self):
        import json
        from physics_ref.library import Library
        loading = json.loads((cv.DATA / "loading_map.json").read_text(encoding="utf-8"))
        fuel, followers = cv.fuel_positions(loading)
        self.assertEqual((len(fuel), followers), (45, ["C10", "D1", "D10"]))
        lib = Library(cv.LIBRARY)
        elements = lib.shapes["bins"]["elements"]
        self.assertIn("A1", elements)
        self.assertIn("B5", elements)
        self.assertEqual(len(elements), 48)


if __name__ == "__main__":
    unittest.main()
