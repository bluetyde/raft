"""Tests for validation/m7_core134_feedback.py on planted reactivities (the real runs are analysed once, by the script)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation import m7_core134_feedback as fb
from validation.tests.test_m7_fuel_coefficient import planted, synthetic

SIGMA = 30.0


def line(rho_pcm, tfuel=None, fuel1994=False, particles=100000):
    rho = rho_pcm / fb.PCM
    k = 1.0 / (1.0 - rho)
    ov = {}
    if tfuel is not None:
        ov["tfuel"] = tfuel
    if fuel1994:
        ov["fuel1994"] = True
    return {"core": "134", "overrides": ov, "particles": particles, "k": k, "kStd": SIGMA / fb.PCM * k**2}


def planted_runs(slope_a=10.0, slope_b=10.0, offset=0.0, bend=0.0, base_rho=300.0):
    """Reactivities of the nine runs: loss slope_a pcm/K (composition A) from 294 K, `offset` between the reference and the 294 K run, `bend` > 0 makes the first interval convex."""
    out = [line(base_rho - offset)]                          # A0, the reference treatment
    for comp, slope in (("A", slope_a), ("B", slope_b)):
        for t in fb.TEMPS:
            dt = t - 294.0
            loss = slope * dt * (1.0 - bend * (400.0 - t) / 106.0) if t < 400.0 else slope * dt
            out.append(line(base_rho - loss, tfuel=t, fuel1994=(comp == "B")))
    return out


def load(lines):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "runs.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return fb.load_runs(p)


class Runs(unittest.TestCase):
    def test_reactivity_and_its_error_are_recovered_and_the_nine_runs_are_keyed(self):
        runs = load(planted_runs())
        self.assertEqual(len(runs), 9)
        self.assertAlmostEqual(runs[("A", 294.0)]["rho"], 300.0, places=6)
        self.assertAlmostEqual(runs[("A", 294.0)]["sigma"], SIGMA, places=6)
        s, e = fb.slope(runs, "A", 400.0)
        self.assertAlmostEqual(s, -10.0, places=6)
        self.assertAlmostEqual(e, SIGMA * 2 ** 0.5 / 106.0, places=6)


class Metrics(unittest.TestCase):
    def analyse(self, **kw):
        lib = synthetic()
        return fb.analyse(lib, load(planted_runs(**kw)), planted(lib))

    def test_a_clean_linear_case_has_no_artefact_and_the_default_table_is_good(self):
        r = self.analyse()
        self.assertEqual((r["D1"]["label"], r["D2"]["label"], r["D3"]["label"]), ("no artefact", "linear", "no effect"))
        self.assertEqual(r["D4"]["A"]["primary"]["worst"], "good")
        self.assertIn("4.", r["decision"]["items"][0])

    def test_a_method_offset_is_detected_only_beyond_two_sigma(self):
        self.assertEqual(self.analyse(offset=60.0)["D1"]["label"], "no artefact")        # 60 pcm against 2 x 42 pcm
        r = self.analyse(offset=200.0)
        self.assertEqual(r["D1"]["label"], "artefact")
        self.assertAlmostEqual(r["D1"]["deltaPcm"], 200.0, places=6)

    def test_convexity_and_composition_are_classified(self):
        self.assertEqual(self.analyse(bend=1.0)["D2"]["label"], "convex")
        stronger = self.analyse(slope_b=14.0)
        self.assertEqual(stronger["D3"]["label"], "stronger")
        self.assertAlmostEqual(stronger["D3"]["ratio372"][0], 1.4, places=6)
        self.assertEqual(self.analyse(slope_b=7.0)["D3"]["label"], "weaker")

    def test_the_decision_items(self):
        # the default composition far too weak, the 1994 composition right: the hydrogen item and no explanation by D1 or D2
        lib = synthetic()
        runs = load(planted_runs(slope_a=5.0, slope_b=10.0))
        r = fb.analyse(lib, runs, planted(lib))
        self.assertEqual(r["D4"]["A"]["primary"]["worst"], "fails")
        self.assertEqual(r["D4"]["B"]["primary"]["worst"], "good")
        self.assertTrue(any(i.startswith("3.") for i in r["decision"]["items"]))
        # both too weak and nothing else different: the outside-the-tables item
        both = fb.analyse(lib, load(planted_runs(slope_a=5.0, slope_b=5.0)), planted(lib))
        self.assertTrue(any(i.startswith("5.") for i in both["decision"]["items"]))
        self.assertFalse(both["decision"]["libraryChanged"])

    def test_missing_runs_are_refused(self):
        lib = synthetic()
        with self.assertRaises(ValueError):
            fb.analyse(lib, load(planted_runs()[:-1]), planted(lib))


class Report(unittest.TestCase):
    def test_the_report_has_the_documented_shape(self):
        lib = synthetic()
        rep = fb.run(lib, load(planted_runs()), planted(lib))
        for key in ("D1", "D2", "D3", "D4", "D5", "decision"):
            self.assertIn(key, rep)
        self.assertEqual(len(rep["D5"]["runs"]), 9)
        self.assertEqual(len(rep["D4"]["A"]["cases"]), 6)


class RealLibraryLoads(unittest.TestCase):
    def test_the_library_has_the_table_the_protocol_names(self):
        from physics_ref.library import Library
        lib = Library(fb.LIBRARY)
        self.assertAlmostEqual(lib.fuel_temp(400.0) * fb.PCM, -657.0, delta=2.0)
        self.assertEqual(lib.fuel_temp.xs[:5], [294.0, 400.0, 500.0, 600.0, 800.0])


if __name__ == "__main__":
    unittest.main()
