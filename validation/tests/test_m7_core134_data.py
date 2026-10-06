"""Tests for validation/m7_core134_data.py on planted pin-cell reactivities, planted bin sets and a synthetic library (the real runs and shapes are analysed once, by the script)."""
from __future__ import annotations

import unittest

from validation import m7_core134_data as dm
from validation.tests.test_m7_fuel_coefficient import planted, synthetic

REF = {294.0: 0.0, 400.0: -694.0, 500.0: -1612.0, 600.0: -2583.0}
SIGMA = 10.0


def rows(factors=None, extra=None):
    """Pin-cell rows whose delta rho against 294 K is factor x the reference at 400, 500 and 600 K and linear in T below 400 K."""
    factors = factors or {400.0: 0.84, 500.0: 0.84, 600.0: 0.84}
    out = {294.0: {"rho": 25000.0, "sigma": SIGMA}}
    for t, f in factors.items():
        out[t] = {"rho": 25000.0 + f * REF[t], "sigma": SIGMA}
    for t in (330.0, 372.0):
        out[t] = {"rho": 25000.0 + factors[400.0] * REF[400.0] * (t - 294.0) / 106.0, "sigma": SIGMA}
    out.update(extra or {})
    return out


class PinCell(unittest.TestCase):
    def test_constant_ratio_and_smooth_curve(self):
        m = dm.p_metrics(rows(), rows(), REF)
        self.assertTrue(m["constant"])
        self.assertTrue(m["smoothAll"])
        for t in dm.R_TEMPS:
            self.assertAlmostEqual(m["R"][t], 0.84, places=9)
        self.assertFalse(any(v["treatmentEffect"] for v in m["p2Effects"].values()))

    def test_a_varying_ratio_a_kinked_curve_and_a_treatment_effect_are_detected(self):
        varying = dm.p_metrics(rows({400.0: 0.80, 500.0: 0.84, 600.0: 0.92}), rows(), REF)
        self.assertFalse(varying["constant"])
        self.assertAlmostEqual(varying["spread"], 0.12, places=9)
        kinked = rows(extra={372.0: {"rho": 25000.0 - 100.0, "sigma": SIGMA}})                # far below the linear 0.74 of the 400 K change
        self.assertFalse(dm.p_metrics(kinked, rows(), REF)["smoothAll"])
        snapped = rows(extra={372.0: {"rho": 25000.0 - 0.84 * 694.0 * 0.74 - 120.0, "sigma": SIGMA}})
        eff = dm.p_metrics(rows(), snapped, REF)["p2Effects"][372.0]
        self.assertTrue(eff["treatmentEffect"])                                                # 120 pcm against 2 x 14 pcm
        self.assertAlmostEqual(eff["sigmaPcm"], (4 * SIGMA ** 2) ** 0.5, places=9)

    def test_the_other_evaluation(self):
        explains = dm.d_metrics(rows({400.0: 1.0, 500.0: 1.01, 600.0: 0.99}), rows(), REF)
        self.assertEqual(explains["label"], "explains")
        self.assertAlmostEqual(explains["factorsVII1OverVIII0"][400.0], 1.0 / 0.84, places=9)
        part = dm.d_metrics(rows({400.0: 0.92, 500.0: 0.92, 600.0: 0.92}), rows(), REF)
        self.assertEqual(part["label"], "part")
        self.assertEqual(dm.d_metrics(rows({400.0: 0.85, 500.0: 0.85, 600.0: 0.85}), rows(), REF)["label"], "not the explanation")


class Kappa(unittest.TestCase):
    def cells(self, densities, volumes=None):
        """(element, bin, fission fraction, volume) with the given power densities (relative to the mean of 1 once normalised)."""
        volumes = volumes or [1.0] * len(densities)
        return [(i, 1, f * v, v) for i, (f, v) in enumerate(zip(densities, volumes))]

    def test_a_uniform_core_has_kappa_one_and_a_known_split_has_its_closed_form(self):
        self.assertAlmostEqual(dm.kappa(self.cells([1.0, 1.0, 1.0]), 2.0, 0.22, "full"), 1.0, places=12)
        c = self.cells([0.5, 1.5])
        self.assertAlmostEqual(dm.kappa(c, 2.0, 0.0, "full"), (0.5 ** 3 + 1.5 ** 3) / (0.5 ** 2 + 1.5 ** 2), places=12)      # 1.4
        self.assertAlmostEqual(dm.kappa(c, 1.0, 0.0, "full"), (0.5 ** 2 + 1.5 ** 2) / (0.5 + 1.5), places=12)                  # 1.25
        # a heat flux scaling flattens the temperature, so kappa falls with n
        self.assertLess(dm.kappa(c, 2.0, 0.22, "full"), dm.kappa(c, 2.0, 0.0, "full"))

    def test_volume_weights_and_the_radial_and_axial_splits(self):
        c = self.cells([0.5, 1.5], [3.0, 1.0])                                   # the mean density is (1.5 + 1.5) / 4 = 0.75
        k = dm.kappa(c, 2.0, 0.0, "full")
        self.assertGreater(k, 1.0)
        elements = [(0, 1, 0.5, 1.0), (0, 2, 0.5, 1.0), (1, 1, 1.5, 1.0), (1, 2, 1.5, 1.0)]       # two elements, two bins each, uniform axially
        radial = dm.kappa(elements, 2.0, 0.0, "radial")
        axial = dm.kappa(elements, 2.0, 0.0, "axial")
        self.assertAlmostEqual(radial, dm.kappa(elements, 2.0, 0.0, "full"), places=12)       # no axial structure: the split equals the whole
        self.assertAlmostEqual(axial, 1.0, places=12)                                         # and the bins are identical, so no axial effect


class WhatIf(unittest.TestCase):
    def test_kappa_one_changes_nothing_and_a_larger_kappa_removes_part_of_the_shortfall(self):
        lib = synthetic()
        data = planted(lib)
        data["steps"][7][5] *= 1.5                                                              # a measurement the planted tables undershoot
        w0 = dm.whatif(lib, data, 1.0)
        self.assertAlmostEqual(w0["fractionOfShortfallRemoved"], 0.0, places=9)
        w1 = dm.whatif(lib, data, 1.3)
        self.assertGreater(w1["fractionOfShortfallRemoved"], 0.0)
        self.assertGreater(w1["step7Pcm"], w0["step7Pcm"])
        stronger = dm.whatif(lib, data, 1.0, 1.4)                                               # a 40 % stronger fuel table
        self.assertGreater(stronger["step7Pcm"], w0["step7Pcm"])

    def test_the_decision_items(self):
        p = {"constant": True, "smoothAll": True}
        c = {"primary": {"kappa": 1.13, "label": "partial"}}
        good = {"labels": {"primary": {"worst": "plausible"}}, "fractionOfShortfallRemoved": 0.9}
        bad = {"labels": {"primary": {"worst": "fails"}}, "fractionOfShortfallRemoved": 0.3}
        w = {"W3": {"status": "not computed"}, "W1": bad}
        out = dm.decide(p, None, c, w)
        self.assertTrue(out["items"][0].startswith("1. OpenMC's temperature treatment is not"))
        self.assertIn("part D not run", out["items"][1])
        self.assertIn("kappa 1.13", out["items"][2])
        self.assertIn("70% of the step 7 shortfall", out["items"][3])
        self.assertTrue(dm.decide({"constant": False, "smoothAll": True}, None, c, {"W3": {"status": "x"}, "W1": good})["items"][0].startswith("1. a treatment artefact"))
        self.assertTrue(dm.decide(p, None, c, {"W3": {"status": "x"}, "W1": good})["items"][3].startswith("4. the candidates"))
        self.assertFalse(out["libraryChanged"])


class RealLibrary(unittest.TestCase):
    def test_the_shape_bins_are_read(self):
        from physics_ref.library import Library
        b = dm.bins_of(Library(dm.LIBRARY))
        self.assertEqual(len(b["elements"]), 48)
        self.assertEqual(len(b["inCoreBins"]), 15)                                              # the bin below the core is left out
        self.assertGreater(len(b["cells"]), 600)


if __name__ == "__main__":
    unittest.main()
