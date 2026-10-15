"""Rod shadowing (capability point-kinetics/rod-interaction-v2): each rod's worth is scaled by 1 + g(R), R the summed reactivity of the other rods.

The fixture's planted g is minus 2 R on the axis -0.01 to 0.03, held at the end values beyond (pipeline/library/synthetic.py), so the right answer is a formula written out here.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from physics_ref import Engine, Library
from physics_ref.engine import IC0, IP

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "vectors"
R_LO, R_HI = -0.01, 0.03
SLOPE = 2.0


def planted_g(r: float) -> float:
    return -SLOPE * min(max(r, R_LO), R_HI)


def make(rods, name="synthetic-core-rod-shadowing"):
    lib = Library(FIXTURES / name)
    return lib, Engine(lib, init={"rods": rods, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)


def worths(lib, rods):
    return {r.id: r.worth(rods[r.id]) for r in lib.rods}


def planted_correction(lib, rods):
    w = worths(lib, rods)
    s = sum(w.values())
    return sum(wi * planted_g(s - wi) for wi in w.values())


class TestRodShadowing(unittest.TestCase):
    def test_the_correction_is_the_planted_function_of_the_others(self):
        for rods in ({"safety": 0.3, "regulating": 0.7, "transient": 0.5}, {"safety": 0.1, "regulating": 0.1, "transient": 0.1},
                     {"safety": 0.9, "regulating": 0.9, "transient": 0.9}, {"safety": 0.5, "regulating": 0.5, "transient": 0.5},
                     {"safety": 1.0, "regulating": 0.2, "transient": 0.0}):
            lib, e = make(rods)
            r = e.reactivity(0.0, e.y)
            self.assertAlmostEqual(r["rodInteraction"], planted_correction(lib, rods), places=12, msg=str(rods))
            self.assertAlmostEqual(r["total"], r["reference"] + r["calibration"] + r["fault"] + r["rods"] + r["fuel"] + r["coolant"] + r["xenon"] + r["rodInteraction"], places=12)
            self.assertAlmostEqual(r["rods"], sum(worths(lib, rods).values()), places=12)

    def test_it_depends_on_which_rod_moves_not_only_on_the_sum(self):
        # two states with (nearly) the same summed worth but different rods: the single-axis table of rod-interaction-v1 cannot tell them apart, this one does
        lib, e1 = make({"safety": 0.8, "regulating": 0.2, "transient": 0.2})
        _, e2 = make({"safety": 0.2, "regulating": 0.8, "transient": 0.2})
        w1, w2 = worths(lib, {"safety": 0.8, "regulating": 0.2, "transient": 0.2}), worths(lib, {"safety": 0.2, "regulating": 0.8, "transient": 0.2})
        self.assertNotAlmostEqual(sum(w1.values()), sum(w2.values()), places=3)           # not equal sums here; the formula test above is the check on values
        self.assertNotEqual(e1.reactivity(0.0, e1.y)["rodInteraction"], e2.reactivity(0.0, e2.y)["rodInteraction"])

    def test_the_end_of_the_axis_clamps(self):
        rods = {"safety": 1.0, "regulating": 1.0, "transient": 1.0}
        lib, e = make(rods)
        w = worths(lib, rods)
        s = sum(w.values())
        self.assertTrue(any(s - wi > R_HI for wi in w.values()))                 # at least one rod sees the others beyond the last point
        self.assertAlmostEqual(e.reactivity(0.0, e.y)["rodInteraction"], planted_correction(lib, rods), places=12)

    def test_every_rod_at_its_reference_adds_nothing(self):
        lib, e = make({"safety": 0.0, "regulating": 0.0, "transient": 0.0})
        r = e.reactivity(0.0, e.y)
        self.assertEqual(r["rodInteraction"], 0.0)
        plain = Library(FIXTURES / "synthetic-core")
        e0 = Engine(plain, init={"rods": {"safety": 0.0, "regulating": 0.0, "transient": 0.0}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertEqual(r["total"], e0.reactivity(0.0, e0.y)["total"])

    def test_one_rod_alone_is_not_shadowed(self):
        rods = {"safety": 0.6, "regulating": 0.0, "transient": 0.0}
        lib, e = make(rods)
        w = worths(lib, rods)
        self.assertEqual([v for k, v in w.items() if k != "safety"], [0.0, 0.0])
        self.assertAlmostEqual(e.reactivity(0.0, e.y)["rodInteraction"], 0.0, places=15)         # R = 0, g(0) = 0

    def test_a_library_without_the_capability_has_no_field(self):
        plain = Library(FIXTURES / "synthetic-core")
        e = Engine(plain, init={"rods": {"safety": 0.3, "regulating": 0.3, "transient": 0.3}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertFalse(plain.has_rod_shadow)
        self.assertNotIn("rodInteraction", e.reactivity(0.0, e.y))

    def test_the_derivative_uses_the_same_total(self):
        rods = {"safety": 0.7, "regulating": 0.6, "transient": 0.55}
        lib, e = make(rods)
        rho = e.reactivity(0.0, e.y)["total"]
        d = e.rhs(0.0, list(e.y))
        want = (rho - lib.beta_total) / lib.gen_time * e.y[IP] + lib.ext_source
        for k in range(6):
            want += lib.lam[k] * e.y[IC0 + k]
        self.assertAlmostEqual(d[IP] / want, 1.0, places=9)

    def test_a_reject_table_halts_the_run_beyond_its_axis(self):
        lib, e = make({"safety": 1.0, "regulating": 1.0, "transient": 1.0})
        lib.rod_shadow.out_of_range = "reject"
        e.step()
        self.assertEqual(e.halted, "R_TABLE_REJECT_rodInteraction")
        lib2, e2 = make({"safety": 0.1, "regulating": 0.1, "transient": 0.1})
        lib2.rod_shadow.out_of_range = "reject"
        e2.step()
        self.assertIsNone(e2.halted)


class TestRodShadowingValidity(unittest.TestCase):
    def test_surroundings_beyond_the_axis_are_out_of_domain(self):
        lib, e = make({"safety": 1.0, "regulating": 1.0, "transient": 1.0})
        w = worths(lib, {"safety": 1.0, "regulating": 1.0, "transient": 1.0})
        self.assertTrue(any(sum(w.values()) - wi > R_HI for wi in w.values()))
        v = e.validity()
        self.assertEqual(v["status"], "outOfDomain")
        self.assertIn("R_DOMAIN_ROD_INTERACTION", v["reasons"])
        _, e2 = make({"safety": 0.5, "regulating": 0.5, "transient": 0.5})
        self.assertNotIn("R_DOMAIN_ROD_INTERACTION", e2.validity()["reasons"])

    def test_a_rod_at_its_reference_is_not_checked_against_the_axis(self):
        # safety and transient out (their worths sum to 0.0385, beyond the axis end at 0.03); regulating stays at its reference, where its worth is 0 and its term is 0.
        # Only the regulating rod "sees" 0.0385, so nothing is out of the domain.
        rods = {"safety": 1.0, "regulating": 0.0, "transient": 1.0}
        lib, e = make(rods)
        w = worths(lib, rods)
        self.assertGreater(sum(w.values()), R_HI)
        self.assertTrue(all(sum(w.values()) - wi <= R_HI for wi in w.values() if wi != 0.0))
        self.assertNotIn("R_DOMAIN_ROD_INTERACTION", e.validity()["reasons"])
        lib.rod_shadow.out_of_range = "reject"
        e.step()
        self.assertIsNone(e.halted)

    def test_one_rod_away_with_a_nonzero_correction_needs_a_joint_check(self):
        # safety and regulating out: R of each is the other's worth, g is not 0
        rods = {"safety": 0.5, "regulating": 0.5, "transient": 0.0}
        lib, e = make(rods)
        self.assertNotEqual(e.reactivity(0.0, e.y)["rodInteraction"], 0.0)
        self.assertIn("R_JOINT_UNCHECKED", e.validity()["reasons"])
        lib.domain["jointChecked"] = [{"rods": rods, "maxShapeErr": 0.0, "rhoErr": 0.0}]
        self.assertNotIn("R_JOINT_UNCHECKED", e.validity()["reasons"])
        plain = Library(FIXTURES / "synthetic-core")
        e3 = Engine(plain, init={"rods": {"safety": 0.5, "regulating": 0.0, "transient": 0.0}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertNotIn("R_JOINT_UNCHECKED", e3.validity()["reasons"])


if __name__ == "__main__":
    unittest.main()
