"""validation.m2_rod_curves.add_point (M2 Codex review 2026-09-28, finding 13): records from another model state are refused."""
from __future__ import annotations

import unittest

from validation import m2_rod_curves as rc

B = 23.675258421961058


def rec(**over):
    p = {"core": "242", "rods": {"T": 450.0, "K": 499.0, "V": 200.0, "R": 500.0}, "overrides": {"burnup": B},
         "prompt": False, "k": 0.99, "kStd": 7e-4}
    p.update(over)
    return p


class AddPointTests(unittest.TestCase):
    def setUp(self):
        self.pts = {"242": {}, "246": {}}

    def test_accepts_a_matching_record_and_an_identical_duplicate(self):
        rc.add_point(self.pts, rec(), B)
        rc.add_point(self.pts, rec(), B)
        self.assertEqual(len(self.pts["242"]), 1)

    def test_refuses_fresh_fuel_prompt_or_other_overrides(self):
        for bad in (rec(overrides={}), rec(prompt=True), rec(overrides={"burnup": B, "tfuel": 600.0})):
            with self.assertRaises(ValueError):
                rc.add_point(self.pts, bad, B)

    def test_refuses_other_rods_off_reference(self):
        with self.assertRaises(ValueError):
            rc.add_point(self.pts, rec(rods={"T": 450.0, "K": 600.0, "V": 200.0, "R": 500.0}), B)

    def test_refuses_conflicting_duplicate(self):
        rc.add_point(self.pts, rec(), B)
        with self.assertRaises(ValueError):
            rc.add_point(self.pts, rec(k=0.98), B)


if __name__ == "__main__":
    unittest.main()
