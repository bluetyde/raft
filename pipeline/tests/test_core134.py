"""Tests for the core 133/134 additions to the OpenMC pipeline (no OpenMC needed: the model builder imports it lazily)."""
from __future__ import annotations

import importlib.util
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


@unittest.skipUnless(importlib.util.find_spec("openmc"), "OpenMC is not installed (run in the openmc-vr environment)")
class ElementTemperatures(unittest.TestCase):
    RODS = {"T": 0.0, "K": 200.0, "V": 200.0, "R": 727.3}

    def positions(self):
        occ = json.loads((cm.DATA / "jsi_core_occupancy.json").read_text(encoding="utf-8"))["cores"]["134"]
        return sorted(occ["fuel"]) + [p for r, p in cm.ROD_AT.items() if r in ("K", "V", "R")]

    def fuel_cells(self, model):
        return [c for c in model.geometry.get_all_cells().values() if c.name and c.fill is not None and "U-ZrH" in getattr(c.fill, "name", "")]

    def test_equal_element_temperatures_reproduce_the_uniform_model(self):
        uniform = cm.build("134", self.RODS, 1000, 20, 5, overrides={"tfuel": 372.0})
        per = cm.build("134", self.RODS, 1000, 20, 5, overrides={"elementTfuel": {p: 372.0 for p in self.positions()}})
        self.assertEqual(len(uniform.geometry.get_all_cells()), len(per.geometry.get_all_cells()))
        self.assertEqual(len(self.fuel_cells(uniform)), len(self.fuel_cells(per)))
        self.assertEqual({c.fill.temperature for c in self.fuel_cells(per)}, {372.0})
        self.assertEqual(per.settings.temperature["method"], "interpolation")
        self.assertEqual(len({c.fill.id for c in self.fuel_cells(per)}), 48)                # one material per fuel position

    def test_each_position_keeps_its_own_temperature_and_a_missing_one_is_refused(self):
        temps = {p: 300.0 + i for i, p in enumerate(self.positions())}
        model = cm.build("134", self.RODS, 1000, 20, 5, overrides={"elementTfuel": temps})
        by_name = {c.name: c.fill.temperature for c in self.fuel_cells(model)}
        for p, t in temps.items():
            self.assertEqual(by_name[p], t, p)
        temps.pop("B5")
        with self.assertRaises(ValueError):
            cm.build("134", self.RODS, 1000, 20, 5, overrides={"elementTfuel": temps})


if __name__ == "__main__":
    unittest.main()
