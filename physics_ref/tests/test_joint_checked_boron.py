"""A checked state may carry a boron window (library format section 13): it then covers only states whose boron concentration lies inside it."""
from __future__ import annotations

import unittest
from pathlib import Path

from physics_ref import Engine, Library

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "vectors"
RODS = {"safety": 0.5, "regulating": 0.5, "transient": 0.0}      # two rods away from their references: a joint state


def engine(boron, windows, rods=RODS):
    lib = Library(FIXTURES / "synthetic-core-boron")
    lib.domain["jointChecked"] = [dict({"rods": dict(RODS), "maxShapeErr": 0.0, "rhoErr": 0.0}, **w) for w in windows]
    init = {"rods": dict(rods), "boron": boron, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}
    return Engine(lib, init=init, seed=1)


def reasons(e):
    return e.validity()["reasons"]


class JointCheckedBoron(unittest.TestCase):
    def test_a_state_with_no_window_covers_any_boron(self):
        for boron in (900.0, 1000.0, 1100.0):
            self.assertNotIn("R_JOINT_UNCHECKED", reasons(engine(boron, [{}])), boron)

    def test_a_window_covers_only_its_boron_and_its_ends_are_inside(self):
        w = [{"boron": [990.0, 1010.0]}]
        self.assertNotIn("R_JOINT_UNCHECKED", reasons(engine(1000.0, w)))
        self.assertNotIn("R_JOINT_UNCHECKED", reasons(engine(990.0, w)))
        self.assertNotIn("R_JOINT_UNCHECKED", reasons(engine(1010.0, w)))
        self.assertIn("R_JOINT_UNCHECKED", reasons(engine(989.9, w)))
        self.assertIn("R_JOINT_UNCHECKED", reasons(engine(1010.1, w)))

    def test_another_entry_for_the_same_rods_at_another_boron_covers_that_boron(self):
        w = [{"boron": [990.0, 1010.0]}, {"boron": [880.0, 900.0]}]
        self.assertNotIn("R_JOINT_UNCHECKED", reasons(engine(890.0, w)))
        self.assertIn("R_JOINT_UNCHECKED", reasons(engine(950.0, w)))

    def test_the_window_does_not_make_other_rod_positions_covered(self):
        w = [{"boron": [990.0, 1010.0]}]
        other = {"safety": 0.9, "regulating": 0.1, "transient": 0.0}
        self.assertIn("R_JOINT_UNCHECKED", reasons(engine(1000.0, w, other)))

    def test_a_library_without_boron_ignores_a_window_it_cannot_carry(self):
        lib = Library(FIXTURES / "synthetic-core")
        lib.domain["jointChecked"] = [{"rods": dict(RODS), "boron": [990.0, 1010.0], "maxShapeErr": 0.0, "rhoErr": 0.0}]
        e = Engine(lib, init={"rods": dict(RODS), "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertNotIn("R_JOINT_UNCHECKED", reasons(e))        # the validator refuses such a library; the engine does not invent a boron


if __name__ == "__main__":
    unittest.main()
