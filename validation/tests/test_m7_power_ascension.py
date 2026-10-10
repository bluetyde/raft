"""Tests for validation/m7_power_ascension.py on a synthetic library with known coefficients.

The real libraries are only loaded (a smoke test), never evaluated: the comparison is run once, as the protocol says.
"""
from __future__ import annotations
from validation.tests._data import needs_data

import unittest
from types import SimpleNamespace

from physics_ref.library import Table
from validation import m7_power_ascension as m7


def synthetic_lib(alpha_fuel_pcm_per_k=-10.0, alpha_cool_pcm_per_k=4.0, hA=3000.0, rod_rho=None):
    """A library whose feedback is linear: fuel alpha_f pcm/K and coolant alpha_c pcm/K above 294 K."""
    xs = [294.0, 1200.0]
    rod_rho = rod_rho or ([0.0, 1.0], [-0.01, 0.01])
    rod = SimpleNamespace(worth=Table(*rod_rho))
    return SimpleNamespace(
        id="synthetic",
        status="experimental",
        hA=hA,
        fuel_temp=Table(xs, [0.0, alpha_fuel_pcm_per_k * (xs[1] - xs[0]) / m7.PCM]),
        cool_temp=Table(xs, [0.0, alpha_cool_pcm_per_k * (xs[1] - xs[0]) / m7.PCM]),
        rod_by_id={"regulating": rod},
    )


class MeasuredData(unittest.TestCase):
    @needs_data("jsi-steady-power")
    def test_the_data_files_load_as_documented(self):
        meas = m7.load_measured()
        self.assertEqual(len(meas["states"]), 11)
        self.assertEqual(meas["peakIndex"], 6)
        self.assertAlmostEqual(meas["defectPcm"][6], 1426.8, places=1)
        self.assertEqual(meas["defectPcm"][0], 0.0)
        self.assertEqual(len(meas["rodCurve"]), 145)
        self.assertEqual(meas["rodCurve"][-1], (900, 3292.5))
        self.assertEqual(meas["pCalculatedKW"][6], 250.0)


class ModelArithmetic(unittest.TestCase):
    P = [0.09, 2.93, 43.6, 100.3, 188.9, 223.0, 250.0, 191.1, 103.7, 47.5, 0.29]

    def test_defect_follows_the_lumped_balance_for_both_pool_cases(self):
        lib = synthetic_lib()
        dT_peak = (250.0 - 0.09) * 1e3 / 3000.0          # fuel rise over the pool between the reference and the peak state
        rows = m7.model_states(lib, self.P, 299.0, rising=False)
        self.assertAlmostEqual(rows[6]["defectPcm"], 10.0 * dT_peak, places=6)
        rows = m7.model_states(lib, self.P, 299.0, rising=True)
        pool_rise = 6.0 * 6 / 10                           # state 7 of 11
        expected = -((-10.0) * (pool_rise + dT_peak) + 4.0 * pool_rise)
        self.assertAlmostEqual(rows[6]["defectPcm"], expected, places=6)

    def test_a_library_with_a_temperature_dependent_hA_is_refused_as_shipped(self):
        lib = synthetic_lib()
        lib.hA_exponent = 0.25
        with self.assertRaises(ValueError):
            m7.model_states(lib, self.P, 299.0, False)
        self.assertEqual(len(m7.model_states(lib, self.P, 299.0, False, hA=3000.0)), 11)       # an explicit hA is the caller's choice

    def test_hA_calibration_hits_the_target_and_reports_what_it_cannot_reach(self):
        lib = synthetic_lib()
        hA = m7.calibrate_hA(lib, self.P, 299.0, False, 1426.8)
        self.assertAlmostEqual(hA, 10.0 * (250.0 - 0.09) * 1e3 / 1426.8, delta=0.5)
        flat = synthetic_lib(alpha_fuel_pcm_per_k=0.0, alpha_cool_pcm_per_k=0.0)
        self.assertIsNone(m7.calibrate_hA(flat, self.P, 299.0, False, 1426.8))

    @needs_data("jsi-steady-power")
    def test_metrics_and_labels_on_a_known_model(self):
        meas = m7.load_measured()
        lib = synthetic_lib()
        # as shipped: the synthetic fuel rise (83 K, -10 pcm/K) gives 833 pcm, ratio 0.58 of 1426.8: plausible
        out = m7.metrics_for(meas, m7.model_states(lib, meas["pCalculatedKW"], 299.0, False))
        self.assertAlmostEqual(out["A"]["ratio"], 833.0 / 1426.8, delta=0.002)
        self.assertEqual(out["A"]["label"], "plausible")
        # a linear model has theta = P / P_peak, so metric C is the distance of the measured shape from a straight line
        self.assertEqual(out["C"]["label"], "fails")
        # calibrated on the peak state the ratio is 1 and metric B is the shape error alone
        hA = m7.calibrate_hA(lib, meas["pCalculatedKW"], 299.0, False, meas["defectPcm"][6])
        out1 = m7.metrics_for(meas, m7.model_states(lib, meas["pCalculatedKW"], 299.0, False, hA))
        self.assertAlmostEqual(out1["A"]["ratio"], 1.0, places=3)
        self.assertEqual(out1["A"]["label"], "good")

    def test_band_edges(self):
        self.assertEqual([m7.label_A(r) for r in (0.8, 1.25, 0.79, 1.26, 0.5, 2.0, 0.49, 2.01)],
                         ["good", "good", "plausible", "plausible", "plausible", "plausible", "fails", "fails"])
        self.assertEqual([m7.label_diff("B", d) for d in (0.05, 0.051, 0.10, 0.101)], ["good", "plausible", "plausible", "fails"])

    @needs_data("jsi-steady-power")
    def test_rod_curve_metric_is_zero_for_the_measured_curve_itself(self):
        meas = m7.load_measured()
        steps = sorted(meas["rodCurve"])
        xs = [m7._x(s) for s, _ in reversed(steps)]
        rho = [-w / m7.PCM for _, w in reversed(steps)]   # rho_rod(1) = 0 at step 181, rho_rod(0) = -total at step 900
        lib = synthetic_lib(rod_rho=(xs, rho))
        d = m7.metric_D(meas, lib)
        self.assertLess(d["maxAbsDiff"], 1e-9)
        self.assertEqual(d["label"], "good")
        self.assertAlmostEqual(d["reported"]["modelTotalWorthPcm"], 3292.5, places=3)

    @needs_data("jsi-steady-power")
    def test_the_full_run_has_the_documented_shape(self):
        report = m7.run({"syn": synthetic_lib()})
        entry = report["libraries"]["syn"]
        self.assertEqual(set(entry["variants"]), {"V0", "V1"})
        self.assertEqual(len(entry["variants"]["V0"]["cases"]), 8)    # 2 T0 x 2 power axes x 2 pool cases
        for v in entry["variants"].values():
            self.assertEqual(set(v["summary"]), {"A", "B", "C"})
        self.assertIn("D", entry)


class RealLibrariesLoad(unittest.TestCase):
    def test_the_two_libraries_load_with_what_the_script_reads(self):
        for name, path in m7.LIBRARIES.items():
            lib = m7.load_library(path)
            self.assertGreater(lib.hA, 0.0, name)       # 3000 W/K constant when the protocols were run; a fitted law since 2026-10-06
            self.assertIn("regulating", lib.rod_by_id, name)
            self.assertGreater(lib.fuel_mass, 0.0, name)


if __name__ == "__main__":
    unittest.main()
