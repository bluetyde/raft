"""Tests for validation/m7_core134_transport.py on planted reactivities and the real library's shape bins (the runs are analysed once, by the script)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation import m7_core134_transport as tr
from validation.tests.test_m7_fuel_coefficient import planted, synthetic

SIGMA = 16.0
POSITIONS = {"A1": 1.0, "B1": 2.0}


def line(rho_pcm, overrides, particles=600000):
    rho = rho_pcm / tr.base.PCM
    k = 1.0 / (1.0 - rho)
    return {"core": "134", "rods": dict(tr.EXPECTED["rods"]), "overrides": overrides, "particles": particles, "batches": 150, "inactive": 50,
            "k": k, "kStd": SIGMA / tr.base.PCM * k ** 2}


def run_lines(delta_u=-500.0, delta_n=-540.0, temps=None):
    temps = temps or {"A1": 380.0, "B1": 368.0}
    return [line(300.0, {"tfuel": 294.0}), line(300.0 + delta_u, {"tfuel": 372.0}), line(300.0 + delta_n, {"elementTfuel": temps})], temps


def load(lines, temps):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "runs.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return tr.load_runs(p, temps)


class RunChecks(unittest.TestCase):
    def test_prompt_runs_and_unusable_uncertainties_are_refused(self):
        lines, temps = run_lines()
        load(lines, temps)
        with self.assertRaisesRegex(ValueError, "prompt-only"):
            load([dict(lines[0], prompt=True)] + lines[1:], temps)
        for bad in (float("nan"), 0.0, -1.0, float("inf")):
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                load([dict(lines[0], kStd=bad)] + lines[1:], temps)

    def test_saved_temperatures_must_match_the_rule(self):
        tr.check_saved_temperatures({"A1": 380.0, "B1": 368.0}, {"A1": 380.0000004, "B1": 368.0})
        with self.assertRaisesRegex(ValueError, "differ"):
            tr.check_saved_temperatures({"A1": 372.0, "B1": 372.0}, {"A1": 380.0, "B1": 368.0})
        with self.assertRaisesRegex(ValueError, "name"):
            tr.check_saved_temperatures({"A1": 372.0}, {"A1": 380.0, "B1": 368.0})


class ElementTemperatures(unittest.TestCase):
    def test_the_volume_mean_rise_is_the_requested_one_and_the_hot_elements_are_hotter(self):
        from physics_ref.library import Library
        lib = Library(tr.LIBRARY)
        temps, volumes = tr.element_temperatures(lib)
        rep = tr.temperature_report(temps, volumes)
        self.assertEqual(rep["count"], 48)
        self.assertAlmostEqual(rep["volumeMeanK"] - tr.BASE_K, tr.MEAN_RISE_K, places=6)
        self.assertGreater(rep["max"], rep["min"])
        self.assertGreater(rep["min"], tr.BASE_K)
        self.assertGreater(temps["B5"], temps["E1"])                                     # an inner element runs hotter than an outer one
        flat, _ = tr.element_temperatures(lib, n=0.0, mean_rise=0.0)
        self.assertTrue(all(abs(t - tr.BASE_K) < 1e-9 for t in flat.values()))           # no rise, no spread

    def test_the_positions_cover_what_core_model_needs(self):
        from physics_ref.library import Library
        from pipeline.openmc import core_model as cm
        temps, _ = tr.element_temperatures(Library(tr.LIBRARY))
        occ = json.loads((cm.DATA / "jsi_core_occupancy.json").read_text(encoding="utf-8"))["cores"]["134"]
        needed = set(occ["fuel"]) | {p for r, p in cm.ROD_AT.items() if r in ("K", "V", "R")}
        self.assertEqual(set(temps), needed)


class Runs(unittest.TestCase):
    def test_the_three_runs_are_keyed_and_anything_else_is_refused(self):
        lines, temps = run_lines()
        runs = load(lines, temps)
        self.assertEqual(set(runs), {"R294", "U372", "NU372"})
        self.assertAlmostEqual(runs["R294"]["rho"], 300.0, places=6)
        bad_t = {"A1": 381.0, "B1": 368.0}
        with self.assertRaises(ValueError):
            load(lines, bad_t)                                                          # the run's temperatures are not the protocol's
        with self.assertRaises(ValueError):
            load(lines + [lines[0]], temps)                                             # a run twice
        with self.assertRaises(ValueError):
            load(lines[:2], temps)                                                      # a run missing
        wrong = [dict(lines[0], particles=100000)] + lines[1:]
        with self.assertRaises(ValueError):
            load(wrong, temps)
        odd = [dict(lines[0], overrides={"tfuel": 294.0, "fuel1994": True})] + lines[1:]
        with self.assertRaises(ValueError):
            load(odd, temps)


class Metrics(unittest.TestCase):
    def analyse(self, du, dn, proxy=1.08):
        lines, temps = run_lines(du, dn)
        lib = synthetic()
        return tr.analyse(lib, load(lines, temps), planted(lib), proxy)

    def test_kappa_and_its_error(self):
        r = self.analyse(-500.0, -540.0)
        self.assertAlmostEqual(r["T1"]["kappa"], 1.08, places=6)
        self.assertEqual(r["T1"]["label"], "partial")
        self.assertTrue(r["T2"]["agrees"])
        self.assertAlmostEqual(r["T1"]["deltaUniformPcm"], -500.0, places=6)
        # sigma by partial derivatives: kappa = (N - R) / (U - R)
        k, du = 1.08, -500.0
        expected = (((1 / du) * SIGMA) ** 2 + ((-k / du) * SIGMA) ** 2 + (((k - 1) / du) * SIGMA) ** 2) ** 0.5
        self.assertAlmostEqual(r["T1"]["sigma"], expected, delta=1e-3)

    def test_labels_and_the_comparison_with_the_proxy(self):
        self.assertEqual(self.analyse(-500.0, -510.0)["T1"]["label"], "none")                   # kappa 1.02
        self.assertEqual(self.analyse(-500.0, -700.0)["T1"]["label"], "large")                  # kappa 1.40
        high = self.analyse(-500.0, -640.0)
        self.assertEqual(high["T2"]["direction"], "higher")                                    # 1.28 against 1.08 with sigma about 0.07
        self.assertTrue(any(i.startswith("3.") for i in high["decision"]["items"]))
        low = self.analyse(-500.0, -510.0)
        self.assertTrue(any(i.startswith("2.") for i in low["decision"]["items"]))
        self.assertFalse(low["decision"]["libraryChanged"])

    def test_the_what_if_uses_the_transport_factor(self):
        lib = synthetic()
        lines, temps = run_lines(-500.0, -600.0)
        data = planted(lib)
        data["steps"][7][5] *= 1.5
        r = tr.analyse(lib, load(lines, temps), data, 1.08)
        self.assertGreater(r["T3"]["fractionOfShortfallRemoved"], 0.0)
        self.assertAlmostEqual(r["T1"]["kappa"], 1.2, places=6)


if __name__ == "__main__":
    unittest.main()
