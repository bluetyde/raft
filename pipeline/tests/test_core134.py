"""Tests for the core 133/134 additions to the OpenMC pipeline (no OpenMC needed: the model builder imports it lazily)."""
from __future__ import annotations

import json
import math
import unittest

from pipeline.openmc import core_model as cm


class Occupancy(unittest.TestCase):
    def test_cores_133_and_134_are_the_benchmark_loadings(self):
        occ = json.loads((cm.DATA / "jsi_core_occupancy.json").read_text(encoding="utf-8"))["cores"]
        c133, c134 = occ["133"], occ["134"]
        self.assertEqual((c133["fuelCount"], c134["fuelCount"]), (40, 45))
        self.assertEqual(len(c133["fuel"]), 40)
        for rod_pos, code in (("C4", "P"), ("C10", "V"), ("D1", "R"), ("D10", "K")):
            self.assertEqual(c134["other"][rod_pos], code)
        self.assertEqual(c134["other"]["E7"], "NI")
        self.assertEqual(c133["other"]["E12"], "NI")
        inner = {p: e for p, e in c134["fuel"].items() if p[0] in "ABCD"}
        self.assertEqual(inner, {p: e for p, e in c133["fuel"].items() if p[0] in "ABCD"})   # rings A to D are the same in both cores
        uranium = {row.split(",")[0] for row in (cm.REPO_ROOT / "validation/data/jsi-core134/fuel_content.csv").read_text(encoding="utf-8").splitlines()[1:]}
        self.assertTrue(set(c134["fuel"].values()) <= uranium)                                   # every element has a Table III entry
        # positions that are labelled in the rings of the model
        for pos in c134["fuel"]:
            self.assertIn(pos[0], cm.RINGS)
            self.assertLessEqual(int(pos[1:]), cm.RINGS[pos[0]])


class Fuel1994(unittest.TestCase):
    def test_the_benchmark_composition_conserves_mass_and_keeps_the_uranium(self):
        fd = json.loads((cm.DATA / "jsi_standard_fuel.json").read_text(encoding="utf-8"))
        d, base = cm.fuel_1994(fd), fd["fuel"]["atomDensityPerBarnCm"]
        self.assertAlmostEqual(d["U235"] / base["U235"], 1.0, delta=1e-3)         # the default composition has the same uranium
        self.assertAlmostEqual(d["U238"] / base["U238"], 1.0, delta=1e-3)
        zr = sum(v for k, v in d.items() if k.startswith("Zr"))
        self.assertAlmostEqual(d["H1"] / zr, 1.65, places=6)
        rad = fd["radiiCm"]
        vol = math.pi * (rad["fuel"] ** 2 - rad["zrRod"] ** 2) * 38.1
        grams = vol / 0.6022140857 * (d["U235"] * 235.0439 + d["U238"] * 238.0508 + zr * 91.224 + d["H1"] * 1.00794)
        self.assertAlmostEqual(grams, 2360.0, delta=0.5)                           # Table II: 2360 g of U-ZrH per element
        self.assertGreater(d["H1"], base["H1"])


if __name__ == "__main__":
    unittest.main()
