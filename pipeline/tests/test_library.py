"""Tests for the library format: schema checker, validator, fixtures and generator.

Run from the repo root (standard library only):
    python -m unittest discover -s pipeline/tests -t .
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.library import synthetic
from pipeline.library.minischema import SchemaError, Validator, check_schema
from pipeline.library.validate import SCHEMA_PATH, _interp, _safe_relpath, validate_library

VECTORS = Path(__file__).resolve().parents[2] / "schema" / "vectors"


class TestMiniSchema(unittest.TestCase):
    def test_project_schema_uses_only_supported_keywords(self):
        check_schema(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

    def test_unsupported_keyword_is_rejected(self):
        with self.assertRaises(SchemaError):
            check_schema({"type": "object", "properties": {"a": {"oneOf": []}}})

    def test_basic_rules(self):
        v = Validator({"type": "object", "required": ["n"], "additionalProperties": False,
                       "properties": {"n": {"type": "number", "exclusiveMinimum": 0}}})
        self.assertEqual(v.errors({"n": 1}), [])
        self.assertTrue(v.errors({"n": 0}))
        self.assertTrue(v.errors({"n": True}))           # booleans aren't numbers
        self.assertTrue(v.errors({"n": float("nan")}))   # nor is NaN
        self.assertTrue(v.errors({}))
        self.assertTrue(v.errors({"n": 1, "extra": 2}))

    def test_any_of(self):
        v = Validator({"anyOf": [{"type": "null"}, {"type": "string"}]})
        self.assertEqual(v.errors(None), [])
        self.assertEqual(v.errors("x"), [])
        self.assertTrue(v.errors(3))

    def test_javascript_parity(self):
        # The TypeScript port must give the same results; these are the cases where plain Python differs.
        self.assertTrue(Validator({"const": 1}).errors(True))            # Python: True == 1
        self.assertTrue(Validator({"enum": [0, "a"]}).errors(False))     # Python: False == 0
        self.assertTrue(Validator({"const": True}).errors(1))
        self.assertEqual(Validator({"const": 1}).errors(1.0), [])       # JSON has one number type
        self.assertEqual(Validator({"enum": [[1, {"a": True}]]}).errors([1.0, {"a": True}]), [])
        self.assertTrue(Validator({"enum": [[1, {"a": True}]]}).errors([1, {"a": 1}]))
        v = Validator({"type": "string", "pattern": "^[a-z]+$"})
        self.assertEqual(v.errors("core"), [])
        self.assertTrue(v.errors("core\n"))                             # Python "$" matches before a final newline
        self.assertEqual(Validator({"type": "string", "pattern": "a\\$"}).errors("a$"), [])  # escaped "$" stays literal
        self.assertEqual(Validator({"type": "string", "minLength": 2}).errors("\U0001F600a"), [])
        self.assertTrue(Validator({"type": "string", "minLength": 2}).errors("\U0001F600"))  # one code point, two UTF-16 units


class TestHelpers(unittest.TestCase):
    def test_interp(self):
        self.assertEqual(_interp([0, 1], [0, 10], 0.5), 5)
        self.assertEqual(_interp([0, 1], [0, 10], 1), 10)
        self.assertIsNone(_interp([0, 1], [0, 10], 1.5))

    def test_safe_relpath(self):
        for ok in ("arrays/base.f32", "a.f32"):
            self.assertTrue(_safe_relpath(ok), ok)
        for bad in ("../a", "/abs", "C:/x", "a\\b", "arrays/../../x", "./a", "", "arrays/%2e%2e/%2e%2e/x.f32", "arrays/%2E%2E/x", "a%2fb", "a?x=1", "a#frag", "a\x00b", "a\nb"):
            self.assertFalse(_safe_relpath(bad), bad)


class TestFixtures(unittest.TestCase):
    def test_synthetic_core_is_valid(self):
        issues = validate_library(VECTORS / "synthetic-core")
        self.assertEqual(issues, [], "\n".join(f"{i.code} {i.path} {i.message}" for i in issues))

    def test_nonstandard_json_constants_are_rejected(self):
        # JavaScript's JSON.parse rejects NaN/Infinity; Python's json.loads accepts them by default.
        text = (VECTORS / "synthetic-core" / "manifest.json").read_text(encoding="utf-8")
        for token in ("NaN", "Infinity", "-Infinity"):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "manifest.json").write_text(
                    text.replace('"schemaVersion"', f'"x": {token}, "schemaVersion"', 1), encoding="utf-8")
                codes = [i.code for i in validate_library(tmp)]
                self.assertEqual(codes, ["E_JSON"], token)

    def test_every_invalid_fixture_fails_with_exactly_its_codes(self):
        cases = sorted(p for p in (VECTORS / "invalid").iterdir() if p.is_dir())
        self.assertGreaterEqual(len(cases), 30)
        for case in cases:
            with self.subTest(case=case.name):
                expected = set(json.loads((case / "expected.json").read_text(encoding="utf-8"))["codes"])
                got = {i.code for i in validate_library(case)}
                self.assertEqual(got, expected)

    def test_every_error_code_in_the_spec_has_a_fixture_or_is_listed_as_untested(self):
        spec = (Path(__file__).resolve().parents[2] / "docs" / "library-format.md").read_text(encoding="utf-8")
        spec_codes = {line.split("`")[1] for line in spec.splitlines() if line.startswith("| `E_")}
        covered = set()
        for case in (VECTORS / "invalid").iterdir():
            covered |= set(json.loads((case / "expected.json").read_text(encoding="utf-8"))["codes"])
        self.assertEqual(spec_codes - covered, set(), "error codes without an invalid fixture")
        self.assertEqual(covered - spec_codes, set(), "fixtures using codes the spec doesn't define")


class TestGenerator(unittest.TestCase):
    def test_committed_fixtures_match_the_generator(self):
        """Fixture changes must come from the generator, and be reviewed (TD-04)."""
        with tempfile.TemporaryDirectory() as tmp:
            synthetic.generate(Path(tmp))
            fresh = {p.relative_to(tmp).as_posix(): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
        committed = {p.relative_to(VECTORS).as_posix(): p.read_bytes() for p in VECTORS.rglob("*") if p.is_file()}
        self.assertEqual(sorted(fresh), sorted(committed))
        changed = [k for k in fresh if fresh[k] != committed[k]]
        self.assertEqual(changed, [], "regenerate with `python -m pipeline.library.synthetic` and review the diff")


class TestJointCheckedBoronWindow(unittest.TestCase):
    """domain.jointChecked[].boron (library format section 13): a [lo, hi] window, valid with the boron capability and lo <= hi."""

    def check(self, fixture, window):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "lib"
            shutil.copytree(VECTORS / fixture, folder)
            m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            m["domain"]["jointChecked"] = [{"rods": {"safety": 0.5, "regulating": 0.5, "transient": 0.0}, "boron": window, "maxShapeErr": 0.0, "rhoErr": 0.0}]
            (folder / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            return [i.code for i in validate_library(folder)]

    def test_a_window_with_equal_ends_is_valid_and_a_reversed_one_is_not(self):
        self.assertEqual(self.check("synthetic-core-boron", [1000.0, 1000.0]), [])
        self.assertEqual(self.check("synthetic-core-boron", [990.0, 1010.0]), [])
        self.assertEqual(self.check("synthetic-core-boron", [1010.0, 990.0]), ["E_SCHEMA"])

    def test_a_window_needs_the_boron_capability(self):
        self.assertEqual(self.check("synthetic-core", [990.0, 1010.0]), ["E_CAPABILITY_UNSUPPORTED"])


if __name__ == "__main__":
    unittest.main()
