"""The nine held-out path cases of docs/validation/m8-rod-interaction-protocol.md (fourteenth protocol), against the protocol's own table."""
from __future__ import annotations

import unittest

from pipeline.openmc import beavrs_cases as bc

REF = {"A": 228, "B": 228, "C": 228, "D": 213, "SA": 228, "SB": 228, "SC": 228, "SD": 228, "SE": 228}
# rod positions in steps withdrawn, transcribed from the protocol's table (the banks not named stay at REF)
PROTOCOL = {
    "P-S3": {"D": 0, "C": 0, "B": 0},
    "P-S5": {"D": 0, "C": 0, "B": 0, "A": 0, "SE": 0},
    "P-S6": {"D": 0, "C": 0, "B": 0, "A": 0, "SE": 0, "SD": 0},
    "P-C-76": {"D": 0, "C": 76},
    "P-B-76": {"D": 0, "C": 0, "B": 76},
    "P-A-76": {"D": 0, "C": 0, "B": 0, "A": 76},
    "P-SE-76": {"D": 0, "C": 0, "B": 0, "A": 0, "SE": 76},
    "P-SD-76": {"D": 0, "C": 0, "B": 0, "A": 0, "SE": 0, "SD": 76},
    "P-SC-76": {"D": 0, "C": 0, "B": 0, "A": 0, "SE": 0, "SD": 0, "SC": 76},
}


class PathCases(unittest.TestCase):
    def test_the_nine_cases_are_the_protocols(self):
        cases = bc.path_cases()
        self.assertEqual(list(cases), list(PROTOCOL))
        for cid, moved in PROTOCOL.items():
            self.assertEqual(cases[cid]["steps"], {**REF, **moved}, cid)

    def test_they_are_apart_from_the_fit_and_use_the_sweeps_settings(self):
        self.assertFalse(set(bc.path_cases()) & set(bc.sweep_cases()))          # the 45-case plan, and the exporter's check of it, are unchanged
        self.assertEqual(len(bc.sweep_cases()), 45)
        ref = bc.sweep_cases()["REF"]
        for cid, c in bc.path_cases().items():
            self.assertEqual((c["boron"], c["tFuel"], c["tWater"], c["ifp"]), (975.0, None, None, False), cid)
            for k in ("particles", "batches", "inactive"):
                self.assertEqual(c[k], ref[k], cid)
            self.assertEqual(c["role"], "path")

    def test_each_part_way_case_has_the_earlier_banks_in_and_the_later_ones_at_reference(self):
        order = bc.INSERT_ORDER
        for cid, c in bc.path_cases().items():
            if not cid.endswith("-76"):
                continue
            bank = cid[2:-3]
            i = order.index(bank)
            for b in order[:i]:
                self.assertEqual(c["steps"][b], 0, (cid, b))
            self.assertEqual(c["steps"][bank], 76)
            for b in order[i + 1:]:
                self.assertEqual(c["steps"][b], REF[b], (cid, b))
            self.assertEqual((c["steps"]["SA"], c["steps"]["SB"]), (228, 228))


if __name__ == "__main__":
    unittest.main()
