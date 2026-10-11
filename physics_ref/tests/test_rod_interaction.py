"""Rod interaction (capability point-kinetics/rod-interaction-v1): a correction added to the sum of the single-rod reactivities, a function of that sum.

The fixture's planted correction is minus 10 % of the sum, clamped beyond +0.03 (pipeline/library/synthetic.py), so the right answer is a formula written out here.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from physics_ref import Engine, Library
from physics_ref.engine import IC0, IP

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "vectors"
S_MAX = 0.03          # the table's last point; beyond it the correction clamps
SHADOW = 0.1


def planted_correction(s: float) -> float:
    return -SHADOW * min(s, S_MAX) if s >= -0.01 else -SHADOW * -0.01


def make(rods, name="synthetic-core-rod-interaction"):
    lib = Library(FIXTURES / name)
    return lib, Engine(lib, init={"rods": rods, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)


def rod_sum(lib, rods):
    s = 0.0
    for r in lib.rods:
        s += r.worth(rods[r.id])
    return s


class TestRodInteraction(unittest.TestCase):
    def test_the_correction_is_the_planted_function_of_the_summed_reactivity(self):
        for rods in ({"safety": 0.3, "regulating": 0.7, "transient": 0.5}, {"safety": 0.1, "regulating": 0.1, "transient": 0.1},
                     {"safety": 0.9, "regulating": 0.9, "transient": 0.9}, {"safety": 0.5, "regulating": 0.5, "transient": 0.5}):
            lib, e = make(rods)
            s = rod_sum(lib, rods)
            r = e.reactivity(0.0, e.y)
            self.assertAlmostEqual(r["rodInteraction"], planted_correction(s), places=12, msg=str(rods))
            self.assertAlmostEqual(r["total"], r["reference"] + r["calibration"] + r["fault"] + r["rods"] + r["fuel"] + r["coolant"] + r["xenon"] + r["rodInteraction"], places=12)
            self.assertAlmostEqual(r["rods"], s, places=12)

    def test_the_end_of_the_axis_clamps(self):
        rods = {"safety": 1.0, "regulating": 1.0, "transient": 1.0}      # the sum is +0.0525, beyond the last point at 0.03
        lib, e = make(rods)
        self.assertGreater(rod_sum(lib, rods), S_MAX)
        self.assertAlmostEqual(e.reactivity(0.0, e.y)["rodInteraction"], -SHADOW * S_MAX, places=12)

    def test_every_rod_at_its_reference_adds_nothing(self):
        lib, e = make({"safety": 0.0, "regulating": 0.0, "transient": 0.0})
        r = e.reactivity(0.0, e.y)
        self.assertEqual(r["rodInteraction"], 0.0)
        plain = Library(FIXTURES / "synthetic-core")
        e0 = Engine(plain, init={"rods": {"safety": 0.0, "regulating": 0.0, "transient": 0.0}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertEqual(r["total"], e0.reactivity(0.0, e0.y)["total"])

    def test_a_library_without_the_capability_has_no_field(self):
        plain = Library(FIXTURES / "synthetic-core")
        e = Engine(plain, init={"rods": {"safety": 0.3, "regulating": 0.3, "transient": 0.3}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}, seed=1)
        self.assertFalse(plain.has_rod_interaction)
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
        rods = {"safety": 1.0, "regulating": 1.0, "transient": 1.0}
        lib, e = make(rods)
        lib.rod_interaction.out_of_range = "reject"
        e.step()
        self.assertEqual(e.halted, "R_TABLE_REJECT_rodInteraction")
        lib2, e2 = make({"safety": 0.1, "regulating": 0.1, "transient": 0.1})
        lib2.rod_interaction.out_of_range = "reject"
        e2.step()
        self.assertIsNone(e2.halted)                                      # inside the axis: no halt


if __name__ == "__main__":
    unittest.main()
