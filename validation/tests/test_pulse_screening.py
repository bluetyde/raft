"""
Tests for deterministic JSI pulse database screening.

Verifies:
- Partition into kept and excluded pulses (kept + excluded == 757, disjoint).
- Missing-value normalization (0.0 converted to None, loader objects not mutated).
- Physical consistency exclusions (subprompt high power, missing reactivity/power).
- Robust outlier detection with MAD and MAD == 0 fallback.
- Per-core summaries and deterministic JSON report generation.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from validation.pulse_loader import DEFAULT_CSV_PATH, PulseRecord, load_pulse_summary
from validation.pulse_screening import (
    DEFAULT_REPORT_PATH,
    MAD_FALLBACK,
    MIN_GROUP_SIZE,
    SCREEN_VERSION,
    SUBPROMPT_MAX_MW,
    Z_LIMIT,
    screen_pulses,
    write_report,
)

DOCUMENTED_REASONS = {
    "group_outlier",
    "missing_peak_power",
    "missing_reactivity",
    "subprompt_high_power",
}


class TestPulseScreening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_records = load_pulse_summary(DEFAULT_CSV_PATH)
        cls.result = screen_pulses(cls.raw_records)

    def test_totals_and_partition(self):
        """Total kept + excluded must equal 757, and no pulse id appears in both."""
        kept = self.result.kept
        excluded = self.result.excluded

        self.assertEqual(len(self.raw_records), 757)
        self.assertEqual(len(kept) + len(excluded), 757)

        kept_ids = {p.pulse_id for p in kept}
        excluded_ids = {pid for pid, _ in excluded}

        self.assertEqual(len(kept_ids), len(kept), "Duplicate IDs in kept list")
        self.assertEqual(len(excluded_ids), len(excluded), "Duplicate IDs in excluded list")

        intersection = kept_ids.intersection(excluded_ids)
        self.assertEqual(intersection, set(), f"Pulse IDs in both kept and excluded: {intersection}")

        all_ids = {p.pulse_id for p in self.raw_records}
        self.assertEqual(kept_ids.union(excluded_ids), all_ids)

    def test_missing_value_normalization(self):
        """No kept record has fwhm_s == 0.0 or any energy field equal to 0.0."""
        for p in self.result.kept:
            self.assertNotEqual(p.fwhm_s, 0.0, f"Pulse {p.pulse_id} has fwhm_s == 0.0")
            self.assertNotEqual(
                p.energy_1000pts_mws, 0.0, f"Pulse {p.pulse_id} has energy_1000pts_mws == 0.0"
            )
            self.assertNotEqual(
                p.energy_1pct_mws, 0.0, f"Pulse {p.pulse_id} has energy_1pct_mws == 0.0"
            )
            self.assertNotEqual(
                p.energy_tangent_mws, 0.0, f"Pulse {p.pulse_id} has energy_tangent_mws == 0.0"
            )

        # Check normalization counts
        norm = self.result.normalized
        self.assertEqual(norm["fwhm_s"], 323)
        self.assertEqual(norm["energy_1000pts_mws"], 60)
        self.assertEqual(norm["energy_1pct_mws"], 65)
        self.assertEqual(norm["energy_tangent_mws"], 65)

        # Verify loader objects were not mutated
        raw_zero_fwhm = sum(1 for p in self.raw_records if p.fwhm_s == 0.0)
        self.assertEqual(raw_zero_fwhm, 323, "Original loader records must not be mutated")

    def test_core_140_subprompt_and_single_group(self):
        """
        Core-140 pulses below prompt critical with high power are excluded with subprompt_high_power.
        Pulse 19 ($1.07, 695.5 MW) is alone in its group, so it must not get group_outlier.
        """
        excluded_dict = dict(self.result.excluded)

        # Pulses in core 140 with rho < 1.0 and peak_power > 10.0 MW
        subprompt_high = [
            p
            for p in self.raw_records
            if p.core_config == "140"
            and p.rho_dollars is not None
            and p.rho_dollars < 1.0
            and p.peak_power_mw is not None
            and p.peak_power_mw > SUBPROMPT_MAX_MW
        ]
        self.assertGreater(len(subprompt_high), 0)
        for p in subprompt_high:
            self.assertIn(p.pulse_id, excluded_dict)
            self.assertIn("subprompt_high_power", excluded_dict[p.pulse_id])

        # Pulse 23 specifically ($0.37 / 167.2 MW in core 140)
        self.assertIn(23, excluded_dict)
        self.assertIn("subprompt_high_power", excluded_dict[23])

        # Pulse 27 ($0.765 / 3.8 MW in core 140) has peak_power <= 10.0 MW, so not subprompt_high_power
        if 27 in excluded_dict:
            self.assertNotIn("subprompt_high_power", excluded_dict[27])

        # Pulse 19 ($1.07, 695.5 MW): alone in its group, must NOT get group_outlier
        p19_reasons = excluded_dict.get(19, [])
        self.assertNotIn("group_outlier", p19_reasons)

        # Core 140 group for pulse 19 has size 1 (< 3)
        c140_p19_group = [
            p
            for p in self.raw_records
            if p.core_config == "140"
            and p.rho_dollars is not None
            and round(p.rho_dollars, 2) == round(1.07, 2)
        ]
        self.assertEqual(len(c140_p19_group), 1)

    def test_synthetic_group_outlier(self):
        """
        Synthetic group test:
        - Powers [10, 11, 12, 500] MW: 500 MW gets group_outlier; others don't.
        - Group of two is never tested.
        """
        base = self.raw_records[0]

        p1 = dataclasses.replace(
            base, pulse_id=1001, core_config="999", rho_dollars=1.50, peak_power_mw=10.0
        )
        p2 = dataclasses.replace(
            base, pulse_id=1002, core_config="999", rho_dollars=1.50, peak_power_mw=11.0
        )
        p3 = dataclasses.replace(
            base, pulse_id=1003, core_config="999", rho_dollars=1.50, peak_power_mw=12.0
        )
        p4 = dataclasses.replace(
            base, pulse_id=1004, core_config="999", rho_dollars=1.50, peak_power_mw=500.0
        )

        res = screen_pulses([p1, p2, p3, p4])
        ex_dict = dict(res.excluded)

        self.assertIn(1004, ex_dict)
        self.assertIn("group_outlier", ex_dict[1004])

        self.assertNotIn(1001, ex_dict)
        self.assertNotIn(1002, ex_dict)
        self.assertNotIn(1003, ex_dict)

        kept_ids = {p.pulse_id for p in res.kept}
        self.assertEqual(kept_ids, {1001, 1002, 1003})

        # Group of two: [10, 500] -> neither flagged (group size < 3)
        res_two = screen_pulses([p1, p4])
        self.assertEqual(len(res_two.excluded), 0)
        self.assertEqual(len(res_two.kept), 2)

    def test_mad_zero_fallback(self):
        """
        MAD == 0 fallback:
        - Powers [10, 10, 10, 25] -> 25 flagged (|log10(25) - 1.0| = 0.398 > 0.3).
        - Powers [10, 10, 10, 15] -> none flagged (|log10(15) - 1.0| = 0.176 <= 0.3).
        """
        base = self.raw_records[0]

        # Case 1: [10, 10, 10, 25]
        pulses_flag = [
            dataclasses.replace(
                base, pulse_id=2001, core_config="998", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=2002, core_config="998", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=2003, core_config="998", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=2004, core_config="998", rho_dollars=1.60, peak_power_mw=25.0
            ),
        ]
        res_flag = screen_pulses(pulses_flag)
        ex_flag = dict(res_flag.excluded)
        self.assertIn(2004, ex_flag)
        self.assertIn("group_outlier", ex_flag[2004])
        self.assertEqual({p.pulse_id for p in res_flag.kept}, {2001, 2002, 2003})

        # Case 2: [10, 10, 10, 15]
        pulses_noflag = [
            dataclasses.replace(
                base, pulse_id=3001, core_config="997", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=3002, core_config="997", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=3003, core_config="997", rho_dollars=1.60, peak_power_mw=10.0
            ),
            dataclasses.replace(
                base, pulse_id=3004, core_config="997", rho_dollars=1.60, peak_power_mw=15.0
            ),
        ]
        res_noflag = screen_pulses(pulses_noflag)
        self.assertEqual(len(res_noflag.excluded), 0)
        self.assertEqual(len(res_noflag.kept), 4)

    def test_determinism(self):
        """Writing report twice gives identical bytes, and committed report matches fresh run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "report1.json"
            p2 = Path(tmpdir) / "report2.json"

            write_report(self.result, p1)
            write_report(self.result, p2)

            bytes1 = p1.read_bytes()
            bytes2 = p2.read_bytes()

            self.assertEqual(bytes1, bytes2)

            # Check committed report against freshly generated report
            self.assertTrue(DEFAULT_REPORT_PATH.exists(), "screening_report.json must exist")
            committed_bytes = DEFAULT_REPORT_PATH.read_bytes()
            self.assertEqual(committed_bytes, bytes1)

    def test_exclusion_reasons_valid(self):
        """Every exclusion reason is one of the four documented strings, and reasons are sorted."""
        for pid, reasons in self.result.excluded:
            self.assertEqual(reasons, sorted(reasons), f"Reasons for pulse {pid} not sorted")
            for r in reasons:
                self.assertIn(r, DOCUMENTED_REASONS, f"Unexpected reason '{r}' for pulse {pid}")

        for reason in self.result.reason_counts:
            self.assertIn(reason, DOCUMENTED_REASONS)

    def test_per_core_summary(self):
        """Core summaries must be sorted numerically, cover all cores, and match kept/excluded counts."""
        cores = self.result.cores
        self.assertEqual(len(cores), 31)

        # Check numeric sorting
        config_ints = [int(c["core_config"]) for c in cores]
        self.assertEqual(config_ints, sorted(config_ints))

        # Check total consistency
        total_kept = sum(c["kept"] for c in cores)
        total_excluded = sum(c["excluded"] for c in cores)
        total_pulses = sum(c["total"] for c in cores)

        self.assertEqual(total_kept, len(self.result.kept))
        self.assertEqual(total_excluded, len(self.result.excluded))
        self.assertEqual(total_pulses, 757)

        # Core 151 has all pulses excluded
        c151 = next(c for c in cores if c["core_config"] == "151")
        self.assertEqual(c151["total"], 11)
        self.assertEqual(c151["kept"], 0)
        self.assertEqual(c151["excluded"], 11)
        self.assertIsNone(c151["min_rho_dollars"])
        self.assertIsNone(c151["max_rho_dollars"])
        self.assertIsNone(c151["min_peak_power_mw"])
        self.assertIsNone(c151["max_peak_power_mw"])
        self.assertEqual(c151["count_fwhm"], 0)
        self.assertEqual(c151["count_t1_max_c"], 0)
        self.assertIsNotNone(c151["first_date"])
        self.assertIsNotNone(c151["last_date"])


if __name__ == "__main__":
    unittest.main()
