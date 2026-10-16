"""The 7 held-out cases of docs/validation/m8-near-critical-protocol.md (sixteenth protocol), against the protocol's own table."""
from __future__ import annotations

import unittest

from pipeline.openmc import beavrs_cases as bc

REF = {"A": 228, "B": 228, "C": 228, "D": 213, "SA": 228, "SB": 228, "SC": 228, "SD": 228, "SE": 228}
# (rod positions in steps withdrawn, boron in ppm), transcribed from the protocol's table (the banks not named stay at REF)
PROTOCOL = {f"N-C-{c}": ({"D": 0, "C": c}, 900.0) for c in (0, 40, 80, 120, 140, 180, 228)}


class NearCases(unittest.TestCase):
    def test_the_seven_cases_are_the_protocols(self):
        cases = bc.near_cases()
        self.assertEqual(list(cases), list(PROTOCOL))
        for cid, (moved, boron) in PROTOCOL.items():
            self.assertEqual(cases[cid]["steps"], {**REF, **moved}, cid)
            self.assertEqual(cases[cid]["boron"], boron, cid)

    def test_they_are_apart_from_the_other_families_and_use_the_sweeps_settings(self):
        near = set(bc.near_cases())
        for other in (bc.sweep_cases(), bc.path_cases(), bc.shadow_cases()):
            self.assertFalse(near & set(other))
        self.assertEqual((len(bc.sweep_cases()), len(bc.path_cases()), len(bc.shadow_cases())), (45, 9, 13))
        ref = bc.sweep_cases()["REF"]
        for cid, c in bc.near_cases().items():
            self.assertEqual((c["tFuel"], c["tWater"], c["ifp"], c["role"]), (None, None, False, "near"), cid)
            for k in ("particles", "batches", "inactive"):
                self.assertEqual(c[k], ref[k], cid)

    def test_the_runner_takes_the_family(self):
        try:
            from pipeline.openmc import beavrs_sweep as sw
        except ImportError:                      # the runner needs POSIX `resource`: it runs in WSL only
            self.skipTest("the runner imports POSIX modules")
        self.assertEqual(sw.NEAR_RESULTS.name, "beavrs_near.jsonl")
        self.assertNotIn(sw.NEAR_RESULTS, (sw.PATH_RESULTS, sw.SHADOW_RESULTS))


if __name__ == "__main__":
    unittest.main()
