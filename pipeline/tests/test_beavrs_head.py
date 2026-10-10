"""The runners import the BEAVRS model from a clone; the clone must be at the commit the protocols fix."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from pipeline.openmc import beavrs_cases as bc


def git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


class Head(unittest.TestCase):
    def test_the_commit_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q")
            git(d, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "x")
            head = subprocess.run(["git", "-C", d, "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(bc.check_beavrs_head(Path(d), expected=head), head)
            with self.assertRaises(RuntimeError):
                bc.check_beavrs_head(Path(d))                                  # another commit than the protocols' 1ccae04
            with self.assertRaises(RuntimeError):
                bc.check_beavrs_head(Path(d), expected="0000000")

    def test_the_protocols_commit_is_the_constant(self):
        self.assertEqual(bc.BEAVRS_HEAD, "1ccae04")
        self.assertIn("1ccae04", (Path(__file__).resolve().parents[2] / "docs" / "validation" / "m8-beavrs-hzp-protocol.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
