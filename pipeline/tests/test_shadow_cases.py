"""The 13 held-out cases of docs/validation/m8-rod-shadowing-protocol.md (fifteenth protocol), against the protocol's own table."""
from __future__ import annotations

import unittest

from pipeline.openmc import beavrs_cases as bc

REF = {"A": 228, "B": 228, "C": 228, "D": 213, "SA": 228, "SB": 228, "SC": 228, "SD": 228, "SE": 228}
SEVEN = ["D", "C", "B", "A", "SE", "SD", "SC"]
# (rod positions in steps withdrawn, boron in ppm), transcribed from the protocol's table (the banks not named stay at REF)
PROTOCOL = {
    "L-C-0": ({b: 0 for b in SEVEN}, 860.0),
    "L-C-40": ({**{b: 0 for b in SEVEN}, "C": 40}, 860.0),
    "L-C-83": ({**{b: 0 for b in SEVEN}, "C": 83}, 860.0),
    "L-C-120": ({**{b: 0 for b in SEVEN}, "C": 120}, 860.0),
    "L-C-160": ({**{b: 0 for b in SEVEN}, "C": 160}, 860.0),
    "L-ARO-860": ({}, 860.0),
    "O-S3": ({"SC": 0, "SD": 0, "SE": 0}, 975.0),
    "O-S5": ({"SC": 0, "SD": 0, "SE": 0, "A": 0, "B": 0}, 975.0),
    "O-S6": ({"SC": 0, "SD": 0, "SE": 0, "A": 0, "B": 0, "C": 0}, 975.0),
    "O-D-76": ({"SC": 0, "SD": 0, "SE": 0, "A": 0, "B": 0, "C": 0, "D": 76}, 975.0),
    "X-5": ({"D": 0, "C": 0, "B": 0, "A": 0, "SA": 0}, 975.0),
    "X-6": ({"D": 0, "C": 0, "B": 0, "A": 0, "SA": 0, "SB": 0}, 975.0),
    "X-9": ({b: 0 for b in bc.BANKS}, 975.0),
}


class ShadowCases(unittest.TestCase):
    def test_the_thirteen_cases_are_the_protocols(self):
        cases = bc.shadow_cases()
        self.assertEqual(list(cases), list(PROTOCOL))
        for cid, (moved, boron) in PROTOCOL.items():
            self.assertEqual(cases[cid]["steps"], {**REF, **moved}, cid)
            self.assertEqual(cases[cid]["boron"], boron, cid)

    def test_they_are_apart_from_the_other_families_and_use_the_sweeps_settings(self):
        shadow = set(bc.shadow_cases())
        self.assertFalse(shadow & set(bc.sweep_cases()))
        self.assertFalse(shadow & set(bc.path_cases()))
        self.assertEqual((len(bc.sweep_cases()), len(bc.path_cases())), (45, 9))
        ref = bc.sweep_cases()["REF"]
        for cid, c in bc.shadow_cases().items():
            self.assertEqual((c["tFuel"], c["tWater"], c["ifp"], c["role"]), (None, None, False, "shadow"), cid)
            for k in ("particles", "batches", "inactive"):
                self.assertEqual(c[k], ref[k], cid)

    def test_the_lesson_position_is_the_drafts_critical_position(self):
        # the draft lesson's critical position is 0.362 of travel; 83 steps of 228 is 0.364
        self.assertAlmostEqual(83 / bc.STEPS_FULL, 0.362, delta=0.003)

    def test_the_runner_takes_the_family(self):
        try:
            from pipeline.openmc import beavrs_sweep as sw
        except ImportError:                      # the runner needs POSIX `resource`: it runs in WSL only
            self.skipTest("the runner imports POSIX modules")
        self.assertEqual(sw.SHADOW_RESULTS.name, "beavrs_shadow.jsonl")
        self.assertNotEqual(sw.SHADOW_RESULTS, sw.PATH_RESULTS)


if __name__ == "__main__":
    unittest.main()
