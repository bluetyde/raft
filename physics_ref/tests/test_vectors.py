"""Tests for reference engine golden vectors and generator.

Standard library only.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from physics_ref import ENGINE_VERSION, Library
from physics_ref import vectors

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "schema" / "engine-vectors"
SYNTHETIC_CORE = REPO_ROOT / "schema" / "vectors" / "synthetic-core"


class TestEngineVectors(unittest.TestCase):
    def test_committed_vectors_match_generator(self):
        """Committed engine vectors must match the generator exactly (reproducible golden vectors)."""
        with tempfile.TemporaryDirectory() as tmp:
            vectors.generate(Path(tmp))
            fresh = {p.relative_to(tmp).as_posix(): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
        committed = {p.relative_to(VECTORS_DIR).as_posix(): p.read_bytes() for p in VECTORS_DIR.rglob("*") if p.is_file()}
        self.assertEqual(sorted(fresh), sorted(committed))
        changed = [k for k in fresh if fresh[k] != committed[k]]
        self.assertEqual(changed, [], "regenerate with `python -m physics_ref.vectors` and review the diff")

    def test_vectors_are_valid_json_without_nonfinite(self):
        def _forbid_constant(c):
            raise ValueError(f"non-finite constant in JSON: {c}")

        files = sorted(VECTORS_DIR.glob("*.json"))
        self.assertEqual(len(files), 6)
        for p in files:
            with self.subTest(file=p.name):
                content = p.read_text(encoding="utf-8")
                doc = json.loads(content, parse_constant=_forbid_constant)
                self.assertIsInstance(doc, dict)

    def test_expected_behaviour_is_present(self):
        def load(name: str) -> dict:
            return json.loads((VECTORS_DIR / f"{name}.json").read_text(encoding="utf-8"))

        # pulse: max sampled power > 1e7 W and the last sample < max/100
        pulse = load("pulse")
        powers = [s["power"] for s in pulse["samples"]]
        max_p = max(powers)
        self.assertGreater(max_p, 1e7)
        self.assertLess(pulse["samples"][-1]["power"], max_p / 100)

        # scram: the command at step 260 has reason REJ_TRIPPED and all rods are 0 in the last sample
        scram = load("scram")
        cmd260 = next(ev for ev in scram["events"] if ev.get("type") == "command" and abs(ev.get("t", 0.0) - 2.6) < 1e-9)
        self.assertEqual(cmd260["reason"], "REJ_TRIPPED")
        self.assertEqual(scram["samples"][-1]["rods"], {"safety": 0.0, "regulating": 0.0, "transient": 0.0})

        # rejections: four reasons are REJ_INTERLOCK:fire-needs-pulse-mode, REJ_NOT_PULSE_CAPABLE, REJ_UNKNOWN_ROD, REJ_UNKNOWN_COMMAND,
        # and indicated.linear is null in the last sample
        rejections = load("rejections")
        cmd_events = [ev for ev in rejections["events"] if ev.get("type") == "command"]
        self.assertEqual(
            [ev["reason"] for ev in cmd_events[:4]],
            [
                "REJ_INTERLOCK:fire-needs-pulse-mode",
                "REJ_NOT_PULSE_CAPABLE",
                "REJ_UNKNOWN_ROD",
                "REJ_UNKNOWN_COMMAND",
            ],
        )
        self.assertIsNone(rejections["samples"][-1]["indicated"]["linear"])

        # period-trip: a trip event with id period-short exists and its time is not a multiple of outerDt (|t/dt − round(t/dt)| > 1e-3)
        period_trip = load("period-trip")
        trip_ev = next(ev for ev in period_trip["events"] if ev.get("type") == "trip" and ev.get("id") == "period-short")
        dt = period_trip["config"]["outerDt"]
        steps = trip_ev["t"] / dt
        self.assertGreater(abs(steps - round(steps)), 1e-3)

        # source-level: first and last sampled power agree within 1e-8 relative
        source_level = load("source-level")
        p_first = source_level["samples"][0]["power"]
        p_last = source_level["samples"][-1]["power"]
        self.assertLess(abs(p_last / p_first - 1.0), 1e-8)

    def test_pins_match_current_engine(self):
        lib = Library(SYNTHETIC_CORE)
        files = sorted(VECTORS_DIR.glob("*.json"))
        self.assertEqual(len(files), 6)
        for p in files:
            with self.subTest(file=p.name):
                doc = json.loads(p.read_text(encoding="utf-8"))
                self.assertEqual(doc["pins"]["engineVersion"], ENGINE_VERSION)
                self.assertEqual(doc["pins"]["libraryDigest"], lib.digest)


if __name__ == "__main__":
    unittest.main()
