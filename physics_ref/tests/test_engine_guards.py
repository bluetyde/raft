"""Guards of the reference engine found by the whole-repo review: a zero interval, non-finite input, and a halt that must not look like progress."""
from __future__ import annotations

import math
import unittest
from pathlib import Path

from physics_ref import Engine, Library
from physics_ref.engine import InitError

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "vectors"
INIT = {"rods": {"safety": 0.0, "regulating": 0.0, "transient": 0.0}, "power": {"mode": "given", "value": 1.0}, "poisons": {"mode": "zero"}}


def engine(init=None, config=None):
    return Engine(Library(FIXTURES / "synthetic-core"), init=dict(init or INIT), seed=1, config=config)


class Guards(unittest.TestCase):
    def test_a_zero_negative_or_non_finite_interval_is_refused(self):
        for key in ("outerDt", "rtol", "hInit", "hMin", "eventTol"):
            for bad in (0.0, -1.0, math.nan, math.inf, "0.01", None, True):
                with self.subTest(key=key, bad=bad), self.assertRaises(InitError):
                    engine(config={key: bad})
        engine(config={"outerDt": 0.02})                                    # a valid change is accepted

    def test_a_non_finite_initial_state_is_refused(self):
        for init in ({**INIT, "power": {"mode": "given", "value": math.nan}}, {**INIT, "power": {"mode": "given", "value": math.inf}},
                     {**INIT, "power": {"mode": "given", "value": -1.0}}, {**INIT, "Tfuel": math.nan}, {**INIT, "Tcoolant": math.inf},
                     {**INIT, "poisons": {"mode": "given", "I": math.nan, "X": 0.0}}, {**INIT, "poisons": {"mode": "given", "I": 0.0, "X": -1.0}}):
            with self.subTest(init=init), self.assertRaises(InitError):
                engine(init)

    def test_a_reactivity_fault_that_is_not_a_finite_number_is_rejected_and_changes_nothing(self):
        e = engine()
        for bad in (math.nan, math.inf, "bad", None):
            e.submit({"type": "fault.reactivity", "deltaRho": bad})
            e.step()
            self.assertEqual(e.extra_rho, 0.0, bad)
            self.assertEqual(e.events[-1]["status"], "rejected", bad)
            self.assertEqual(e.events[-1]["reason"], "REJ_BAD_ARGUMENT", bad)
        e.submit({"type": "fault.reactivity", "deltaRho": 1.0e-4})
        e.step()
        self.assertEqual(e.extra_rho, 1.0e-4)

    def test_advance_returns_the_steps_taken_and_stops_when_halted(self):
        e = engine()
        self.assertEqual(e.advance(0.1), 10)
        self.assertEqual(e.step_index, 10)
        e.halted = "R_TABLE_REJECT_test"
        self.assertEqual(e.advance(5.0), 0)                                  # no progress, and it says so
        self.assertEqual(e.step_index, 10)

    def test_a_state_that_is_not_a_number_halts_the_engine_with_the_reason(self):
        e = engine()
        e._integrate = lambda t0, t1: setattr(e, "y", [math.nan] * len(e.y))
        e.step()
        self.assertEqual(e.halted, "R_NONFINITE_STATE")
        self.assertEqual(e.events[-1]["type"], "halt")
        self.assertEqual(e.validity()["status"], "outOfDomain")
        before = e.step_index
        self.assertEqual(e.advance(1.0), 0)
        self.assertEqual(e.step_index, before)


class Vectors(unittest.TestCase):
    def test_a_scenario_that_halts_is_an_error_not_a_shorter_vector(self):
        from physics_ref import vectors
        lib = Library(FIXTURES / "synthetic-core")
        sc = {"name": "halts", "description": "x", "init": dict(INIT), "seed": 1, "config": {}, "steps": 50, "sampleEvery": 10,
              "script": [{"step": 5, "cmd": {"type": "fault.reactivity", "deltaRho": 1.0e-4}}]}
        orig_step = Engine.step

        def halting_step(self):
            orig_step(self)
            if self.step_index == 7:
                self.halted = "R_TABLE_REJECT_test"
        Engine.step = halting_step
        try:
            with self.assertRaisesRegex(RuntimeError, "halted at step 7"):
                vectors.run_scenario(lib, sc)
        finally:
            Engine.step = orig_step

    def test_samples_carry_the_validity_reasons(self):
        from physics_ref import vectors
        e = engine()
        s = vectors.sample_from_engine(e)
        self.assertEqual(s["validityStatus"], e.validity()["status"])
        self.assertEqual(s["validityReasons"], e.validity()["reasons"])


if __name__ == "__main__":
    unittest.main()
