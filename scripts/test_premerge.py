"""Tests for scripts/premerge.py using stub stages only.

These tests MUST NEVER run real stages to avoid recursing unittest runs.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.premerge import (
    Result,
    Stage,
    default_stages,
    main,
    run_stages,
)


def _passing_stubs() -> list[Stage]:
    return [
        Stage("python", [sys.executable, "-c", "pass"], "."),
        Stage("web-test", [sys.executable, "-c", "pass"], "."),
        Stage("web-typecheck", [sys.executable, "-c", "pass"], "."),
        Stage("web-build", [sys.executable, "-c", "pass"], "."),
    ]


class TestPremerge(unittest.TestCase):
    def test_all_stubs_pass(self):
        """a. all stubs pass -> run_stages gives 4 results with returncode 0, main returns 0."""
        stubs = _passing_stubs()
        results = run_stages(stubs, REPO_ROOT)
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertEqual(r.returncode, 0)
            self.assertIsNone(r.reason)
            self.assertGreaterEqual(r.seconds, 0.0)

        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main([], stages_factory=lambda _: _passing_stubs())
        self.assertEqual(exit_code, 0)

    def test_one_stub_fails_in_middle(self):
        """b. one stub fails in the middle (raise SystemExit(3)) -> that result has 3, later stages still ran, main returns 1."""
        stubs = [
            Stage("python", [sys.executable, "-c", "pass"], "."),
            Stage("web-test", [sys.executable, "-c", "raise SystemExit(3)"], "."),
            Stage("web-typecheck", [sys.executable, "-c", "pass"], "."),
            Stage("web-build", [sys.executable, "-c", "pass"], "."),
        ]
        results = run_stages(stubs, REPO_ROOT)
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0].returncode, 0)
        self.assertEqual(results[1].returncode, 3)
        self.assertEqual(results[2].returncode, 0)
        self.assertEqual(results[3].returncode, 0)

        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main([], stages_factory=lambda _: [
                Stage("python", [sys.executable, "-c", "pass"], "."),
                Stage("web-test", [sys.executable, "-c", "raise SystemExit(3)"], "."),
                Stage("web-typecheck", [sys.executable, "-c", "pass"], "."),
                Stage("web-build", [sys.executable, "-c", "pass"], "."),
            ])
        self.assertEqual(exit_code, 1)

    def test_missing_executable(self):
        """c. a stage whose executable doesn't exist -> returncode 127 with reason 'command not found', main returns 1."""
        stage = Stage("bad-cmd", ["nonexistent_command_xyz_12345"], ".")
        results = run_stages([stage], REPO_ROOT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 127)
        self.assertEqual(results[0].reason, "command not found")

        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main([], stages_factory=lambda _: [Stage("bad-cmd", ["nonexistent_command_xyz_12345"], ".")])
        self.assertEqual(exit_code, 1)

    def test_default_stages(self):
        """d. default_stages has exactly the four names in order, with cwd '.' or 'web'."""
        stages = default_stages(REPO_ROOT)
        names = [s.name for s in stages]
        self.assertEqual(names, ["python", "web-test", "web-typecheck", "web-build"])
        cwds = [s.cwd for s in stages]
        self.assertEqual(cwds, [".", "web", "web", "web"])
        for s in stages:
            self.assertIn(s.cwd, (".", "web"))

    def test_skip_python_and_skip_web_exit_2(self):
        """e. --skip-python --skip-web -> exit 2."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main(["--skip-python", "--skip-web"], stages_factory=lambda _: _passing_stubs())
        self.assertEqual(cm.exception.code, 2)

    def test_only_web_build(self):
        """f. --only web-build selects exactly that stage."""
        stubs = [
            Stage("python", [sys.executable, "-c", "raise SystemExit(10)"], "."),
            Stage("web-test", [sys.executable, "-c", "raise SystemExit(11)"], "."),
            Stage("web-typecheck", [sys.executable, "-c", "raise SystemExit(12)"], "."),
            Stage("web-build", [sys.executable, "-c", "pass"], "."),
        ]
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            exit_code = main(["--only", "web-build"], stages_factory=lambda _: stubs)
        self.assertEqual(exit_code, 0)
        output = out_buf.getvalue()
        self.assertIn("web-build", output)
        self.assertNotIn("python", output)
        self.assertNotIn("web-test", output)
        self.assertNotIn("web-typecheck", output)

    def test_npm_not_found(self):
        """If npm is not found, stage fails with returncode 127 and reason 'npm not found'."""
        stage = Stage("web-test", [None, "test"], "web")
        results = run_stages([stage], REPO_ROOT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 127)
        self.assertEqual(results[0].reason, "npm not found")

        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main([], stages_factory=lambda _: [Stage("web-test", [None, "test"], "web")])
        self.assertEqual(exit_code, 1)

    def test_skip_flags(self):
        """Test --skip-python and --skip-web individually."""
        stubs = [
            Stage("python", [sys.executable, "-c", "raise SystemExit(10)"], "."),
            Stage("web-test", [sys.executable, "-c", "pass"], "."),
            Stage("web-typecheck", [sys.executable, "-c", "pass"], "."),
            Stage("web-build", [sys.executable, "-c", "pass"], "."),
        ]
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            self.assertEqual(main(["--skip-python"], stages_factory=lambda _: stubs), 0)
        out = out_buf.getvalue()
        self.assertNotIn("python", out)
        self.assertIn("web-test", out)

        stubs_web_failing = [
            Stage("python", [sys.executable, "-c", "pass"], "."),
            Stage("web-test", [sys.executable, "-c", "raise SystemExit(10)"], "."),
            Stage("web-typecheck", [sys.executable, "-c", "raise SystemExit(10)"], "."),
            Stage("web-build", [sys.executable, "-c", "raise SystemExit(10)"], "."),
        ]
        out_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf):
            self.assertEqual(main(["--skip-web"], stages_factory=lambda _: stubs_web_failing), 0)
        out = out_buf.getvalue()
        self.assertIn("python", out)
        self.assertNotIn("web-test", out)


if __name__ == "__main__":
    unittest.main()
