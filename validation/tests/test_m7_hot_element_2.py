"""Tests for validation/m7_hot_element_2.py on a synthetic library and planted pulse data (the real pulse database is read once, by the script)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from validation import m7_hot_element as he
from validation import m7_hot_element_2 as he2
from validation import m7_power_ascension as base
from validation.tests.test_m7_hot_element import P, T0, ht_rows, lib_with_shapes


def pulse(i, f, energy, lib, core="242", col="energy_1pct_mws", t0=25.0):
    """A pulse whose thermocouples both read peaking f (adiabatic, constant cp 300) in the given energy column."""
    tmax = t0 + f * energy * 1e6 / (lib.fuel_mass * 300.0)
    vals = {"energy_1000pts_mws": energy / 5.0, "energy_1pct_mws": energy, "energy_tangent_mws": energy}
    vals[col] = energy
    return SimpleNamespace(pulse_id=i, core_config=core, t1_max_c=tmax, t2_max_c=tmax, **vals)


class Stability(unittest.TestCase):
    def test_a_stable_adiabatic_data_set_passes_both_checks(self):
        lib = lib_with_shapes()
        recs = [pulse(i, 1.4, 4.0 + i, lib) for i in range(24)]
        st = he2.stability(he2.readings(recs, lib, "242"))["both"]
        self.assertAlmostEqual(st["median"], 1.4, places=9)
        self.assertEqual((st["K1"]["label"], st["T"]["label"]), ("good", "good"))

    def test_a_planted_energy_trend_and_a_planted_parity_split_are_caught(self):
        lib = lib_with_shapes()
        trend = [pulse(i, 1.0 + 0.1 * i, 4.0 + i, lib) for i in range(24)]            # F_tc rises with energy
        st = he2.stability(he2.readings(trend, lib, "242"))["both"]
        self.assertEqual(st["T"]["label"], "fails")
        self.assertLess(st["T"]["ratio"], 1.0)
        parity = [pulse(i, 2.0 if i % 2 == 0 else 1.0, 4.0 + i, lib) for i in range(24)]
        self.assertEqual(he2.stability(he2.readings(parity, lib, "242"))["both"]["K1"]["label"], "fails")

    def test_too_few_readings_are_not_computed(self):
        lib = lib_with_shapes()
        st = he2.stability(he2.readings([pulse(i, 1.4, 5.0, lib) for i in range(2)], lib, "242"))["both"]
        self.assertEqual((st["K1"]["label"], st["T"]["label"]), ("not computed", "not computed"))


class Rings(unittest.TestCase):
    def test_rings_exclude_unpowered_elements_and_name_the_closest_element(self):
        lib = lib_with_shapes()
        w = he2.ring_factors(lib, {"safety": 1.0, "regulating": 0.5}, 294.0, 0.6)
        self.assertEqual(set(w["rings"]), {"B", "C"})                       # C2 has no power
        self.assertEqual(w["rings"]["C"]["n"], 1)
        n_l = 3 * he.L_CM
        self.assertAlmostEqual(w["rings"]["B"]["max"], 0.20 / 2.54 * n_l, places=9)
        self.assertEqual(w["closest"]["element"], "B2")                    # factor 0.01/2.54*114.3 = 0.45 is nearest 0.6


class Decision(unittest.TestCase):
    def test_the_three_cases(self):
        self.assertEqual(he2.decide("good", ["good", "plausible", "good"])["case"], 1)
        self.assertEqual(he2.decide("plausible", ["good", "fails", "good"])["case"], 2)
        self.assertEqual(he2.decide("plausible", ["good", "not computed", "good"])["case"], 2)
        self.assertEqual(he2.decide("fails", ["good", "good", "good"])["case"], 3)
        self.assertIsNone(he2.decide("not computed", ["good", "good", "good"])["case"])       # nothing compared: unresolved, not a failure


class Run(unittest.TestCase):
    def test_the_run_has_the_documented_shape_and_restores_the_column_list(self):
        lib = lib_with_shapes()
        t = he.chain_temperatures(P, base.pool_temperatures(len(P), T0, False), 2000.0, 0.25, 1.5, he.K_PRIMARY, he.RI, 61)
        meas = {"states": [{"regulatingRodStep": 500}] * 11, "pCalculatedKW": P, "pIndicatedKW": P, "fuelTempC": [x - base.K0 for x in t],
                "fuelTempC_table2_first_row": 25.8, "defectPcm": [r["defectPcm"] for r in ht_rows(lib)]}
        before = he.ENERGY_COLUMNS
        recs = [pulse(i, 1.5, 4.0 + i, lib) for i in range(24)] + [pulse(100 + i, 1.5, 4.0 + i, lib, core="246") for i in range(24)]
        report = he2.run({"core242": lib, "core246": lib}, recs, meas)
        self.assertEqual(he.ENERGY_COLUMNS, before)
        self.assertEqual(report["K2"]["label"], "good")
        self.assertEqual(set(report["K2"]["perThermocouple"]), {"tc1", "tc2"})
        self.assertEqual(report["stabilityAggregate"]["both"], {"K1": "good", "T": "good"})
        for name in ("core242", "core246"):
            e = report["libraries"][name]
            for key in ("stability", "decision2", "W", "recordOnly", "H1pulse", "H1shape", "G"):
                self.assertIn(key, e)
            self.assertAlmostEqual(e["stage1"]["primary"]["both"]["median"], 1.5, places=9)
            self.assertIn(e["decision2"]["case"], (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
