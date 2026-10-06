"""Tests for validation/m7_core134_library.py on a synthetic library built from the measured curves themselves (the real library is read once, by the script)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from physics_ref.library import Table
from validation import m7_core134_library as cl
from validation.tests.test_m7_fuel_coefficient import planted, synthetic


def library_from(rod_data, scale=1.0, shape_power=1.0):
    """A synthetic library whose rod tables are Table VI itself (times scale; shape_power bends the curve) and whose feedback is linear."""
    lib = synthetic()
    rods = {}
    for rid in cl.COLUMNS:
        rows, full = rod_data["rows"][rid], rod_data["full"][rid]
        total = rows[38] if rid == "regulating" else full
        pts = [(cl.x_of(rid, d), -scale * total * (rows[d] / total) ** shape_power / cl.PCM) for d in sorted(rows)]
        pts.append((cl.x_of(rid, 38.1), -scale * (2552.0 if rid == "regulating" else full) / cl.PCM))
        pts.sort()
        if rid == "transient":
            pts.append((1.0, 0.0))
        else:
            pts[-1] = (1.0, -scale * rod_data["rows"][rid][0] / cl.PCM)       # the 0 cm point is x = 1
        xs, ys = zip(*sorted(pts))
        rods[rid] = SimpleNamespace(worth=Table(list(xs), list(ys)))
    lib.rod_by_id = rods
    lib.calibration = -0.003
    return lib


class Data(unittest.TestCase):
    def test_table_vi_is_loaded_with_the_misprint_noted(self):
        d = cl.load_rods()
        self.assertEqual(len(d["rows"]["regulating"]), 39)
        self.assertEqual(d["rows"]["regulating"][38], 2550.0)
        self.assertEqual(d["full"], {"regulating": 2252.0, "shim": 2430.0, "safety": 3440.0, "transient": 2270.0})
        self.assertAlmostEqual(cl.measured_worth_at(d["rows"]["regulating"], 28.7), 2116.0 + 0.7 * 55.0, places=6)
        self.assertEqual(cl.x_of("regulating", 0.0), 1.0)
        self.assertAlmostEqual(cl.x_of("transient", 0.0), 7.0 / 9.0)


class Rods(unittest.TestCase):
    def test_a_library_built_from_the_measured_curves_scores_good_everywhere(self):
        d = cl.load_rods()
        m = cl.rod_metrics(library_from(d), d)
        for rid in cl.COLUMNS:
            self.assertEqual((m[rid]["R1"]["label"], m[rid]["R2"]["label"]), ("good", "good"), rid)
            self.assertAlmostEqual(m[rid]["R1"]["ratio"], 1.0, delta=0.002)
        self.assertEqual(m["regulating"]["R3"]["label"], "good")
        self.assertLess(abs(m["regulating"]["R3"]["differencePcm"]), 5.0)

    def test_scale_and_shape_errors_are_caught_separately(self):
        d = cl.load_rods()
        big = cl.rod_metrics(library_from(d, scale=1.5), d)
        self.assertEqual(big["regulating"]["R1"]["label"], "fails")
        self.assertEqual(big["regulating"]["R2"]["label"], "good")                  # the normalised shape is unchanged
        self.assertEqual(big["regulating"]["R3"]["label"], "fails")
        bent = cl.rod_metrics(library_from(d, shape_power=0.7), d)
        self.assertEqual(bent["regulating"]["R1"]["label"], "good")                 # the total is the same
        self.assertNotEqual(bent["regulating"]["R2"]["label"], "good")

    def test_label_edges(self):
        self.assertEqual([cl.label_ratio(r) for r in (0.9, 1.1, 0.8, 1.25, 0.79, 1.26)], ["good", "good", "plausible", "plausible", "fails", "fails"])
        self.assertEqual([cl.label_diff(x, cl.R2_BANDS) for x in (0.05, 0.051, 0.10, 0.101)], ["good", "plausible", "plausible", "fails"])


class Decision(unittest.TestCase):
    @staticmethod
    def rods(reg="good", other="good"):
        r = {k: {"R1": {"label": reg}, "R2": {"label": reg}, "R3": {"label": reg}} for k in ("regulating",)}
        r.update({k: {"R1": {"label": other}, "R2": {"label": other}} for k in ("shim", "safety", "transient")})
        return r

    def test_the_branches(self):
        self.assertIn("seventh protocol may compare", cl.decide(self.rods(), "plausible")["next"])
        self.assertIn("not usable", cl.decide(self.rods(reg="fails"), "good")["next"])
        self.assertIn("fresh-fuel feedback fails", cl.decide(self.rods(), "fails")["next"])
        self.assertEqual(cl.decide(self.rods(other="fails"), "good")["regulatingRod"], "supported")

    def test_the_full_run_has_the_documented_shape(self):
        d = cl.load_rods()
        lib = library_from(d)
        report = cl.run(lib, d, planted(lib))
        for key in ("rods", "A", "F", "decision"):
            self.assertIn(key, report)
        self.assertEqual(report["A"]["worst"], "good")
        self.assertEqual(len(report["A"]["cases"]), 6)
        self.assertEqual(len(report["F"]["meanRiseAtPowers"]), 11)


class RealLibraryLoads(unittest.TestCase):
    def test_the_library_has_the_four_rods_and_the_calibration_the_protocol_states(self):
        from physics_ref.library import Library
        lib = Library(cl.LIBRARY)
        self.assertEqual(sorted(lib.rod_by_id), ["regulating", "safety", "shim", "transient"])
        self.assertAlmostEqual(-lib.calibration * cl.PCM, 323.5, delta=1.0)
        self.assertEqual(lib.fuel_temp.xs[:2], [294.0, 400.0])


if __name__ == "__main__":
    unittest.main()
