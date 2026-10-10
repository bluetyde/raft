"""The transcribed BEAVRS core layout (pipeline/openmc/data/beavrs_core.json) against the benchmark's own counts."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "openmc" / "data"
CORE = json.loads((DATA / "beavrs_core.json").read_text(encoding="utf-8"))
BY_LABEL = {a["label"]: a for a in CORE["assemblies"]}


class BeavrsCore(unittest.TestCase):
    def test_counts_match_the_benchmark(self):
        self.assertEqual(len(CORE["assemblies"]), 193)
        self.assertEqual(len(BY_LABEL), 193)
        counts = {b: len(v) for b, v in CORE["rcca"]["banks"].items()}
        self.assertEqual(counts, {"A": 4, "B": 8, "C": 8, "D": 5, "SA": 8, "SB": 8, "SC": 4, "SD": 4, "SE": 4})
        self.assertEqual(sum(counts.values()), 53)
        self.assertEqual(sum(1 for a in CORE["assemblies"] if a["bank"]), 53)

    def test_positions_are_unique_and_inside_the_lattice(self):
        seen = {(a["x"], a["y"]) for a in CORE["assemblies"]}
        self.assertEqual(len(seen), 193)
        for a in CORE["assemblies"]:
            self.assertTrue(0 <= a["x"] < 19 and 0 <= a["y"] < 19)
            self.assertEqual(a["y"], 18 - a["row"])
            self.assertEqual(a["x"], a["col"])

    def test_orientation_is_pinned_by_asymmetric_banks(self):
        # bank D has 5 assemblies and the core map is not symmetric under reflection for banks SD/SC, so a flipped y or a
        # transposed index would move these
        self.assertEqual((BY_LABEL["H8"]["x"], BY_LABEL["H8"]["y"], BY_LABEL["H8"]["bank"]), (9, 9, "D"))
        self.assertEqual((BY_LABEL["L3"]["x"], BY_LABEL["L3"]["y"], BY_LABEL["L3"]["bank"]), (6, 14, "SD"))
        self.assertEqual((BY_LABEL["N11"]["x"], BY_LABEL["N11"]["y"], BY_LABEL["N11"]["bank"]), (4, 6, "SD"))
        self.assertEqual((BY_LABEL["C11"]["x"], BY_LABEL["C11"]["y"], BY_LABEL["C11"]["bank"]), (14, 6, "SC"))
        self.assertEqual(sorted(CORE["rcca"]["banks"]["SC"]), ["C11", "E3", "L13", "N5"])

    def test_dimensions_and_licence(self):
        self.assertAlmostEqual(CORE["latticePitchCm"], 21.50364)
        self.assertAlmostEqual(CORE["activeFuelTopCm"] - CORE["activeFuelBotCm"], 365.76, places=3)
        self.assertAlmostEqual(CORE["rcca"]["stepWidthCm"] * CORE["rcca"]["stepsTotal"], 360.68, places=2)
        self.assertEqual(CORE["rcca"]["stepsBite"], 213)
        self.assertIn("Massachusetts Institute of Technology", (DATA / "BEAVRS-LICENSE").read_text(encoding="utf-8")[:200])


if __name__ == "__main__":
    unittest.main()
