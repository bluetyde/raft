"""The transcribed Mosteller Doppler data (pipeline/openmc/data/mosteller_doppler.json) and the 32 cases built from it."""
from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from pipeline.openmc import doppler_cases as dc

DATA_DIR = Path(__file__).resolve().parents[1] / "openmc" / "data"
DATA = json.loads((DATA_DIR / "mosteller_doppler.json").read_text(encoding="utf-8"))
REFERENCE = json.loads((Path(__file__).resolve().parents[2] / "validation" / "data" / "mosteller-doppler" / "reference.json")
                       .read_text(encoding="utf-8"))
CASES = dc.cases()


class DopplerCases(unittest.TestCase):
    def test_there_are_32_cases_16_pairs_and_the_settings_are_fixed(self):
        self.assertEqual(len(CASES), 32)
        pairs = {(v["case"], v["state"]) for v in CASES.values()}
        self.assertEqual(len(pairs), 32)
        by_case = Counter(v["case"] for v in CASES.values())
        self.assertEqual(len(by_case), 16)
        self.assertTrue(all(n == 2 for n in by_case.values()))
        for cid, v in CASES.items():
            self.assertEqual(cid, f"{v['case']}/{v['state']}")
            self.assertEqual((v["particles"], v["batches"], v["inactive"]), (20000, 600, 100))

    def test_counts_per_subset_seeds_and_fuel_temperatures(self):
        per_subset = Counter(v["subset"] for v in CASES.values() if v["state"] == "hzp")
        self.assertEqual(per_subset, {"uo2": 7, "reactor-mox": 5, "weapons-mox": 4})
        for v in CASES.values():
            if v["state"] == "hzp":
                self.assertEqual((v["seed"], v["fuelK"]), (1, 600))
            else:
                self.assertEqual((v["seed"], v["fuelK"]), (2, 900))

    def test_data_has_densities_and_dimensions_at_both_temperatures(self):
        for dim in ("fuel_or", "clad_ir", "clad_or", "pitch"):
            self.assertEqual(set(DATA[dim]), {"300", "600", "900"}, dim)
        self.assertIn("600", DATA["clad_density"])
        self.assertIn("600", DATA["water_comp"])
        for subset, comp in DATA["composition"].items():
            n = len(comp["nuclides"])
            for content in DATA["enrichments"][subset]:
                for T in ("600", "900"):
                    values = comp["densities"][T][str(content)]
                    self.assertEqual(len(values), n, f"{subset} {content} {T} K")

    def test_licence_notice_is_present(self):
        text = (DATA_DIR / "MOSTELLER-DOPPLER-LICENSE").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", text)

    def test_case_ids_match_the_validation_reference(self):
        ref_ids = {row["id"] for row in REFERENCE["cases"]}
        self.assertEqual(len(ref_ids), 16)
        self.assertEqual({v["case"] for v in CASES.values()}, ref_ids)

    def test_first_nuclide_is_oxygen_at_a_plausible_density(self):
        for subset, comp in DATA["composition"].items():
            self.assertEqual(comp["nuclides"][0], "O16")
            for content in DATA["enrichments"][subset]:
                o16 = comp["densities"]["600"][str(content)][0]
                self.assertTrue(0.04 < o16 < 0.05, f"{subset} {content}: O16 {o16}")


if __name__ == "__main__":
    unittest.main()
