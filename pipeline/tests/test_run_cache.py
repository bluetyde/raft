"""TD-06 closure checks for pipeline/runs/cache.py: content changes invalidate, extraction changes don't re-run transport, an
interrupted run is never read as complete. Fake runs (no OpenMC) except the last class, which needs OpenMC and is skipped without it."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.runs import cache

INPUTS = {"geometry.xml": b"<geometry/>", "materials.xml": b"<materials><m d='6.0'/></materials>", "settings.xml": b"<s b='10'/>"}
VERSIONS = {"openmc": "0.15.3", "cache": "1"}


class FakeRun:
    """Writes out.txt; counts calls; can be told to crash (before writing) or to leave an incomplete output."""

    def __init__(self, crash: int = 0, incomplete: int = 0):
        self.calls, self.crash, self.incomplete = 0, crash, incomplete

    def __call__(self, d: Path) -> None:
        self.calls += 1
        if self.calls <= self.crash:
            raise RuntimeError("simulated crash")
        (d / "out.txt").write_text("partial" if self.calls <= self.crash + self.incomplete else "done", encoding="utf-8")


def verify(d: Path) -> bool:
    p = d / "out.txt"
    return p.exists() and p.read_text(encoding="utf-8") == "done"


class CaseKeyTests(unittest.TestCase):
    def test_model_content_change_changes_key(self):
        k0 = cache.case_key(INPUTS, "data0", VERSIONS)
        changed = dict(INPUTS, **{"materials.xml": b"<materials><m d='6.1'/></materials>"})
        self.assertNotEqual(k0, cache.case_key(changed, "data0", VERSIONS))

    def test_data_or_version_change_changes_key(self):
        k0 = cache.case_key(INPUTS, "data0", VERSIONS)
        self.assertNotEqual(k0, cache.case_key(INPUTS, "data1", VERSIONS))
        self.assertNotEqual(k0, cache.case_key(INPUTS, "data0", dict(VERSIONS, openmc="0.16.0")))

    def test_key_is_order_independent_and_boundary_safe(self):
        rev = dict(reversed(list(INPUTS.items())))
        self.assertEqual(cache.case_key(INPUTS, "d", VERSIONS), cache.case_key(rev, "d", VERSIONS))
        a = cache.case_key({"a": b"bc", "d": b""}, "d", VERSIONS)
        b = cache.case_key({"a": b"b", "cd": b""}, "d", VERSIONS)
        self.assertNotEqual(a, b)


class DataDigestTests(unittest.TestCase):
    def test_changed_file_content_changes_digest(self):
        with tempfile.TemporaryDirectory() as t:
            root, f = Path(t) / "cache", Path(t) / "U235.h5"
            f.write_bytes(b"xs-v1")
            d1 = cache.data_digest([f], root)
            self.assertEqual(d1, cache.data_digest([f], root))          # memoized, same answer
            f.write_bytes(b"xs-v2-longer")                               # size changes, so the memo tag changes
            self.assertNotEqual(d1, cache.data_digest([f], root))


class RunCaseTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_completed_case_is_reused_not_rerun(self):
        run = FakeRun()
        k1, _ = cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        k2, _ = cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        self.assertEqual((k1, run.calls), (k2, 1))

    def test_content_change_runs_a_new_case(self):
        run = FakeRun()
        k1, _ = cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        k2, _ = cache.run_case(dict(INPUTS, **{"settings.xml": b"<s b='11'/>"}), "d", VERSIONS, run, verify, self.root)
        self.assertNotEqual(k1, k2)
        self.assertEqual(run.calls, 2)

    def test_interrupted_run_is_not_complete_and_is_rerun(self):
        key = cache.case_key(INPUTS, "d", VERSIONS)
        d = self.root / "raw" / key
        d.mkdir(parents=True)
        # what a crash mid-run leaves: status "running" and partial output
        (d / "status.json").write_text(json.dumps({"state": "running", "attempts": 1, "errors": []}), encoding="utf-8")
        (d / "out.txt").write_text("partial", encoding="utf-8")
        self.assertFalse(cache.is_complete(d, verify))
        with self.assertRaises(cache.RunFailed):
            cache.derived(key, "k", "1", lambda _: {}, verify, self.root)
        run = FakeRun()
        cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        self.assertEqual(run.calls, 1)
        st = cache.read_status(d)
        self.assertEqual((st["state"], st["attempts"]), ("completed", 2))

    def test_completed_status_with_bad_outputs_is_rerun(self):
        run = FakeRun()
        key, d = cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        (d / "out.txt").unlink()                                          # e.g. a statepoint deleted by hand
        self.assertFalse(cache.is_complete(d, verify))
        cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        self.assertEqual(run.calls, 2)

    def test_crash_is_retried_and_recorded(self):
        run = FakeRun(crash=1)
        _, d = cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root)
        st = cache.read_status(d)
        self.assertEqual((st["state"], run.calls), ("completed", 2))
        self.assertIn("simulated crash", st["errors"][0])

    def test_run_that_returns_with_incomplete_output_is_not_complete(self):
        run = FakeRun(incomplete=5)
        with self.assertRaises(cache.RunFailed):
            cache.run_case(INPUTS, "d", VERSIONS, run, verify, self.root, max_attempts=2)
        d = self.root / "raw" / cache.case_key(INPUTS, "d", VERSIONS)
        self.assertEqual(cache.read_status(d)["state"], "failed")
        self.assertEqual(len(cache.read_status(d)["errors"]), 2)

    def test_repeated_crash_raises_with_the_cause(self):
        with self.assertRaises(cache.RunFailed) as ctx:
            cache.run_case(INPUTS, "d", VERSIONS, FakeRun(crash=9), verify, self.root, max_attempts=2)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)


class DerivedTests(unittest.TestCase):
    def test_extractor_change_reextracts_without_rerunning(self):
        with tempfile.TemporaryDirectory() as t:
            root, run, calls = Path(t), FakeRun(), []

            def ext(v):
                def f(d):
                    calls.append(v)
                    return {"v": v, "out": (d / "out.txt").read_text(encoding="utf-8")}
                return f

            key, _ = cache.run_case(INPUTS, "d", VERSIONS, run, verify, root)
            self.assertEqual(cache.derived(key, "shape", "1", ext(1), verify, root)["v"], 1)
            self.assertEqual(cache.derived(key, "shape", "1", ext(1), verify, root)["v"], 1)   # cached
            self.assertEqual(cache.derived(key, "shape", "2", ext(2), verify, root)["v"], 2)   # new version
            self.assertEqual(calls, [1, 2])
            self.assertEqual(run.calls, 1)                                                     # transport ran once


try:
    import openmc  # noqa: F401
    HAVE_OPENMC = True
except ImportError:
    HAVE_OPENMC = False


@unittest.skipUnless(HAVE_OPENMC, "needs OpenMC (the openmc-vr env)")
class OpenMCIntegrationTests(unittest.TestCase):
    """A bare U-235 sphere: the real inputs, data digest and statepoint verifier, end to end."""

    def model(self, density: float, batches: int = 6):
        import openmc
        openmc.reset_auto_ids()                                        # see cache.openmc_inputs
        m = openmc.Material()
        m.add_nuclide("U235", 1.0)
        m.set_density("g/cm3", density)
        s = openmc.Sphere(r=9.0, boundary_type="vacuum")
        model = openmc.model.Model(geometry=openmc.Geometry([openmc.Cell(fill=m, region=-s)]),
                                   materials=openmc.Materials([m]))
        st = model.settings
        st.run_mode, st.particles, st.batches, st.inactive, st.seed = "eigenvalue", 200, batches, 2, 1
        st.output = {"summary": False}
        return model

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            k1, d1 = cache.run_openmc_case(self.model(18.7), root)
            self.assertTrue(cache.is_complete(d1, cache.openmc_verify(6)))
            k1b, _ = cache.run_openmc_case(self.model(18.7), root)
            self.assertEqual(k1, k1b)
            k2, _ = cache.run_openmc_case(self.model(18.8), root)
            self.assertNotEqual(k1, k2)
            (d1 / "statepoint.6.h5").unlink()                            # an interrupted run has no final statepoint
            self.assertFalse(cache.is_complete(d1, cache.openmc_verify(6)))


if __name__ == "__main__":
    unittest.main()
