"""Tests for the OpenMC sweep exporter (pipeline.library.export_openmc)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

# If OPENMC_CROSS_SECTIONS is not configured in the environment,
# ensure openmc is not treated as available for test_run_cache integration tests.
if "OPENMC_CROSS_SECTIONS" not in os.environ:
    sys.modules["openmc"] = None

from pipeline.library.export_openmc import export, interp, isotonic, main, step_to_x
from pipeline.library.validate import validate_library
from pipeline.openmc import core_model
from pipeline.tests.fixtures_sweep import synthetic_summary


class TestExportOpenMC(unittest.TestCase):
    def test_a_both_cores_validate(self):
        """Both cores 242 and 246 export valid libraries passing validate_library."""
        for core in ("242", "246"):
            s = synthetic_summary(core)
            with tempfile.TemporaryDirectory() as t:
                out_dir = Path(t) / f"lib_{core}"
                rep = export(s, out_dir, created="2026-09-27")
                issues = validate_library(out_dir)
                self.assertEqual(issues, [], f"Validation issues on core {core}: {issues}")
                self.assertIn("rods", rep)
                self.assertIn("fuelTemp", rep)
                self.assertIn("coolantTemp", rep)
                self.assertIn("jointChecked", rep)

    def test_b_step_to_x(self):
        """step_to_x converts indicator steps to fraction withdrawn accurately."""
        self.assertEqual(step_to_x("K", 200), 1.0)
        self.assertEqual(step_to_x("K", 900), 0.0)
        self.assertEqual(step_to_x("K", 499), round(401.0 / 700.0, 12))
        self.assertEqual(step_to_x("shim", 200), 1.0)
        self.assertEqual(step_to_x("shim", 900), 0.0)
        self.assertEqual(step_to_x("shim", 499), round(401.0 / 700.0, 12))

        self.assertEqual(step_to_x("T", 0), 1.0)
        self.assertEqual(step_to_x("T", 900), 0.0)
        self.assertEqual(step_to_x("transient", 0), 1.0)
        self.assertEqual(step_to_x("transient", 900), 0.0)

        with self.assertRaises(ValueError):
            step_to_x("Z", 100)

    def test_c_worth_tables(self):
        """Worth tables are zero at reference x, non-decreasing, and match S-curves."""
        s = synthetic_summary("246")
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib"
            rep = export(s, out_dir, created="2026-09-27")
            m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            for rod in m["reactivity"]["rods"]:
                rid = rod["id"]
                worth = rod["worth"]
                ref_x = m["reference"]["rods"][rid]

                # Zero at reference x
                ref_idx = worth["x"].index(ref_x)
                self.assertEqual(worth["rho"][ref_idx], 0.0)

                # Monotonically non-decreasing
                for a, b in zip(worth["rho"], worth["rho"][1:]):
                    self.assertLessEqual(a, b)

                # Match S-curve points within 1e-9 for noise-free input
                # Total worths from fixtures_sweep
                wtot = {"transient": 0.030, "shim": 0.020, "safety": 0.025, "regulating": 0.006}[rid]
                w_ref = wtot * (ref_x - math.sin(2.0 * math.pi * ref_x) / (2.0 * math.pi))
                for x, rho in zip(worth["x"], worth["rho"]):
                    w_expected = wtot * (x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi)) - w_ref
                    self.assertAlmostEqual(rho, w_expected, delta=1e-9)

        # Non-monotone input test: inject a dip into one rod's worth cases
        s_dip = copy.deepcopy(s)
        # Find a transient rod worth case and inject a dip
        t_cases = [c for c in s_dip["cases"] if c.get("family") == "rod-worth" and c.get("rod") == "T"]
        # Reduce k for one of the cases to produce a non-monotonic raw point
        t_cases[2]["k"] -= 0.02
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib_dip"
            rep = export(s_dip, out_dir, created="2026-09-27")
            m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            t_rod = next(r for r in m["reactivity"]["rods"] if r["id"] == "transient")

            # Manifest worth table remains non-decreasing thanks to PAV
            for a, b in zip(t_rod["worth"]["rho"], t_rod["worth"]["rho"][1:]):
                self.assertLessEqual(a, b)

            # Report keeps the raw values which contain the dip
            t_rep_raw = rep["rods"]["transient"]["raw"]
            raw_rhos = [p["rho"] for p in t_rep_raw]
            has_dip = any(b < a for a, b in zip(raw_rhos, raw_rhos[1:]))
            self.assertTrue(has_dip, "Report should keep raw points with the dip")

    def test_d_isotonic_hand_example(self):
        """isotonic correctly fits the hand example [1, 3, 2, 4] with equal weights."""
        ys = [1.0, 3.0, 2.0, 4.0]
        res = isotonic([0, 1, 2, 3], ys, [1.0, 1.0, 1.0, 1.0])
        self.assertEqual(res, [1.0, 2.5, 2.5, 4.0])

        res_default = isotonic(ys)
        self.assertEqual(res_default, [1.0, 2.5, 2.5, 4.0])

    def test_e_calibration(self):
        """deltaRho in calibration equals -reference.rho.value."""
        s = synthetic_summary("242")
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib"
            export(s, out_dir, created="2026-09-27")
            m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            delta_rho = m["reference"]["calibration"]["deltaRho"]
            rho_val = m["reference"]["rho"]["value"]
            self.assertEqual(delta_rho, -rho_val)

    def test_f_joint_checked(self):
        """jointChecked has 6 entries; rhoErr < 1e-9 for noise=0, and rhoErr ≈ 1e-3 for noise=1e-3."""
        # Noise-free
        s0 = synthetic_summary("246", noise=0.0)
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib0"
            export(s0, out_dir, created="2026-09-27")
            m0 = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            jc0 = m0["domain"]["jointChecked"]
            self.assertEqual(len(jc0), 6)
            for entry in jc0:
                self.assertLess(entry["rhoErr"], 1e-9)

        # With noise = 1e-3
        s_noisy = synthetic_summary("246", noise=1e-3)
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib_noisy"
            export(s_noisy, out_dir, created="2026-09-27")
            m_noisy = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            jc_noisy = m_noisy["domain"]["jointChecked"]
            self.assertEqual(len(jc_noisy), 6)
            for entry in jc_noisy:
                self.assertAlmostEqual(entry["rhoErr"], 1e-3, places=5)

    def test_g_shapes(self):
        """Base shape sums to 1 within 1e-5; delta slices sum to 0 within 1e-5; reference slice is 0."""
        s = synthetic_summary("242")
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib"
            export(s, out_dir, created="2026-09-27")
            m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            E = len(m["shapes"]["bins"]["elements"])
            A = len(m["shapes"]["bins"]["axialEdgesCm"]) - 1
            n_bins = E * A

            # Check base
            base_bytes = (out_dir / "arrays" / "base.f32").read_bytes()
            base_vals = struct.unpack(f"<{n_bins}f", base_bytes)
            self.assertAlmostEqual(sum(base_vals), 1.0, delta=1e-5)

            # Check rod deltas
            for rid, rdelta in m["shapes"]["rodDeltas"].items():
                xs = rdelta["x"]
                ref_x = m["reference"]["rods"][rid]
                ref_idx = xs.index(ref_x)

                arr_file = m["arrays"][rdelta["array"]]["file"]
                data = (out_dir / arr_file).read_bytes()
                vals = struct.unpack(f"<{len(xs) * n_bins}f", data)

                for k in range(len(xs)):
                    sl = vals[k * n_bins: (k + 1) * n_bins]
                    self.assertAlmostEqual(sum(sl), 0.0, delta=1e-5)
                    if k == ref_idx:
                        self.assertEqual(max(abs(v) for v in sl), 0.0)

            # Check temp delta
            tdelta = m["shapes"]["tempDelta"]
            ts = tdelta["T"]
            ref_t = m["reference"]["Tfuel"]["value"]
            ref_idx = ts.index(ref_t)

            t_file = m["arrays"][tdelta["array"]]["file"]
            t_data = (out_dir / t_file).read_bytes()
            t_vals = struct.unpack(f"<{len(ts) * n_bins}f", t_data)

            for k in range(len(ts)):
                sl = t_vals[k * n_bins: (k + 1) * n_bins]
                self.assertAlmostEqual(sum(sl), 0.0, delta=1e-5)
                if k == ref_idx:
                    self.assertEqual(max(abs(v) for v in sl), 0.0)

    def test_h_geometry(self):
        """Every element has a primitive; follower primitives carry both element and rod."""
        s = synthetic_summary("242")
        with tempfile.TemporaryDirectory() as t:
            out_dir = Path(t) / "lib"
            export(s, out_dir, created="2026-09-27")
            m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            elements = set(m["shapes"]["bins"]["elements"])
            primitives = m["geometry"]["primitives"]
            covered = {p["element"] for p in primitives if "element" in p}
            self.assertEqual(elements - covered, set(), "All elements must have geometry primitives")

            # Check follower positions carry both element and rod
            follower_positions = {core_model.ROD_AT[r] for r in ("K", "V", "R")}
            for pos in follower_positions:
                follower_prim = [p for p in primitives if p.get("element") == pos and "rod" in p]
                self.assertTrue(len(follower_prim) >= 1, f"Follower {pos} must carry both element and rod")

    def test_i_refusals(self):
        """Invalid inputs raise ValueError with appropriate messages."""
        s_base = synthetic_summary("242")

        # Incomplete summary
        s = copy.deepcopy(s_base)
        s["complete"] = False
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export(s, t)

        # Missing family
        s = copy.deepcopy(s_base)
        s["cases"] = [c for c in s["cases"] if c["family"] != "holdout"]
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export(s, t)

        # Missing kinetics
        s = copy.deepcopy(s_base)
        ref_case = next(c for c in s["cases"] if c["family"] == "reference")
        ref_case["betaGroups"] = None
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export(s, t)

        # Differing elements
        s = copy.deepcopy(s_base)
        s["cases"][1]["elements"] = list(s["cases"][1]["elements"])[:-1]
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export(s, t)

        # Rod with fewer than 2 worth points
        s = copy.deepcopy(s_base)
        s["cases"] = [c for c in s["cases"] if not (c["family"] == "rod-worth" and c.get("rod") == "T")]
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                export(s, t)

    def test_j_determinism(self):
        """Two exports with same --created give byte-identical manifest and arrays."""
        s = synthetic_summary("246")
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            out1 = Path(t1) / "lib1"
            out2 = Path(t2) / "lib2"

            export(s, out1, created="2026-09-27")
            export(s, out2, created="2026-09-27")

            files1 = sorted([p.relative_to(out1) for p in out1.rglob("*") if p.is_file()])
            files2 = sorted([p.relative_to(out2) for p in out2.rglob("*") if p.is_file()])
            self.assertEqual(files1, files2)

            for rel_path in files1:
                bytes1 = (out1 / rel_path).read_bytes()
                bytes2 = (out2 / rel_path).read_bytes()
                h1 = hashlib.sha256(bytes1).hexdigest()
                h2 = hashlib.sha256(bytes2).hexdigest()
                self.assertEqual(h1, h2, f"Hash mismatch for {rel_path}")


if __name__ == "__main__":
    unittest.main()
