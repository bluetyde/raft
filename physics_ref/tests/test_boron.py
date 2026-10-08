"""Soluble boron (capability point-kinetics/boron-v1): the actuator, its reactivity, its commands, checkpoints. Standard library only."""
from __future__ import annotations

import unittest
from pathlib import Path

from physics_ref import Engine, Library
from physics_ref.engine import InitError
from physics_ref.vectors import near_critical_rods

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "vectors"


def make(lib=None, **init):
    lib = lib or Library(FIXTURES / "synthetic-core-boron")
    return lib, Engine(lib, init={"rods": near_critical_rods(lib, -0.0005), **init}, seed=1)


def run(e: Engine, seconds: float) -> None:
    e.advance(seconds)


class TestBoron(unittest.TestCase):
    def test_the_reference_concentration_adds_nothing(self):
        _, with_b = make()
        plain = Library(FIXTURES / "synthetic-core")
        without = Engine(plain, init={"rods": near_critical_rods(plain, -0.0005)}, seed=1)
        self.assertEqual(with_b.reactivity(0.0, with_b.y)["total"], without.reactivity(0.0, without.y)["total"])
        run(with_b, 5)
        run(without, 5)
        self.assertEqual(with_b.y[0], without.y[0])                         # identical power after 5 s: the extension changes nothing else

    def test_the_ramp_is_exactly_the_rate_and_stops_at_the_target(self):
        lib, e = make()
        self.assertEqual(lib.boron_max_rate, 0.5)
        e.submit({"type": "boron.set", "ppm": 990.0})
        run(e, 10.0)
        self.assertAlmostEqual(e.boron_value(e.t), 995.0, places=9)
        self.assertEqual(e.snapshot()["truth"]["boronTarget"], 990.0)
        run(e, 10.0)
        self.assertEqual(e.boron_value(e.t), 990.0)
        self.assertIsNone(e.snapshot()["truth"]["boronTarget"])
        run(e, 10.0)
        self.assertEqual(e.boron_value(e.t), 990.0)
        r = e.snapshot()["truth"]["reactivity"]
        self.assertAlmostEqual(r["boron"], 10 * 1.2e-4, places=12)         # 10 ppm of dilution at 12 pcm/ppm
        self.assertAlmostEqual(r["total"] - r["boron"] - r["fuel"] - r["coolant"] - r["xenon"] - r["rods"], r["reference"], places=12)   # the boron term is one more summand

    def test_a_new_target_in_mid_ramp_starts_from_the_current_value(self):
        _, e = make()
        e.submit({"type": "boron.set", "ppm": 900.0})
        run(e, 20.0)                                                        # 990 ppm now
        e.submit({"type": "boron.set", "ppm": 1000.0})                      # reverse
        run(e, 10.0)
        self.assertAlmostEqual(e.boron_value(e.t), 995.0, places=9)         # up 5 ppm in 10 s from 990
        e.submit({"type": "boron.set", "ppm": e.boron_value(e.t)})          # the current value: stop
        run(e, 10.0)
        self.assertAlmostEqual(e.boron_value(e.t), 995.0, places=9)

    def test_rejections(self):
        lib, e = make()
        for ppm in (2500.0, -1.0, "lots", None, True, float("inf")):
            e.submit({"type": "boron.set", "ppm": ppm})
        run(e, 0.1)
        reasons = [ev["reason"] for ev in e.events if ev["type"] == "command"]
        self.assertEqual(reasons, ["REJ_OUT_OF_RANGE", "REJ_OUT_OF_RANGE", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT", "REJ_BAD_ARGUMENT"])
        self.assertEqual(e.boron_value(e.t), 1000.0)                        # nothing moved
        with self.assertRaises(InitError):
            Engine(lib, init={"boron": 2500.0})
        plain = Library(FIXTURES / "synthetic-core")
        p = Engine(plain, seed=1)
        p.submit({"type": "boron.set", "ppm": 900.0})
        p.step()
        self.assertEqual([ev["reason"] for ev in p.events if ev["type"] == "command"], ["REJ_UNKNOWN_COMMAND"])
        with self.assertRaises(InitError):
            Engine(plain, init={"boron": 900.0})

    def test_an_interlock_can_block_the_command(self):
        lib = Library(FIXTURES / "synthetic-core-boron")
        lib.interlocks.append({"id": "no-boron-change", "when": {"signal": "truth.mode", "op": "eq", "value": "steady"},
                               "blocks": ["boron.set"], "reason": "test"})
        _, e = make(lib)
        e.submit({"type": "boron.set", "ppm": 900.0})
        e.step()
        self.assertEqual([ev["reason"] for ev in e.events if ev["type"] == "command"], ["REJ_INTERLOCK:no-boron-change"])

    def test_a_checkpoint_in_mid_ramp_resumes_the_same_run(self):
        lib, a = make()
        a.submit({"type": "boron.set", "ppm": 980.0})
        run(a, 7.5)
        b = Engine.restore(lib, a.checkpoint())
        run(a, 40.0)
        run(b, 40.0)
        self.assertEqual(a.y, b.y)
        self.assertEqual(a.boron_value(a.t), b.boron_value(b.t))
        self.assertEqual(a.boron_value(a.t), 980.0)
        # a session replays to the same state too
        c = Engine.replay(lib, a.session(), a.step_index)
        self.assertEqual(a.y, c.y)

    def test_a_trip_can_watch_the_concentration(self):
        lib = Library(FIXTURES / "synthetic-core-boron")
        lib.boron_max_rate = 5.0
        lib.trips.append({"id": "boron-low", "input": "truth.boron", "predicate": {"op": "lt", "value": 950.0}, "latching": True})
        _, e = make(lib)
        e.submit({"type": "boron.set", "ppm": 900.0})
        run(e, 12.0)
        self.assertIn("boron-low", e.latched)
        trip = next(ev for ev in e.events if ev["type"] == "trip" and ev["id"] == "boron-low")
        self.assertAlmostEqual(trip["t"], 10.0, delta=1e-6)                 # 50 ppm at 5 ppm/s; located inside the step, not at its end


if __name__ == "__main__":
    unittest.main()
