"""Tests for validation/doppler_defect.py on planted k values built from the reference (the real results are analysed once, by the script)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation import doppler_defect as dd

REF = json.loads(dd.REFERENCE.read_text(encoding="utf-8"))
SIGMA_K = 0.0002


def planted_rows(dc_of=None, drop=(), shape=None):
    """Rows for every reference case: the HZP k is the reference kHZP; the HFP k gives the model's Doppler coefficient dc_of(id, subset, dc_ref).
    kBatches alternate k -/+ 0.001 (equal window means), plus shape(id, state, batch index) if given."""
    rows = []
    n = dd.EXPECTED["batches"]
    for case in REF["cases"]:
        cid, sub = case["id"], case["subset"]
        e7 = case["endfb7"]
        dc_model = dc_of(cid, sub, e7["dc"]) if dc_of else e7["dc"]
        k_hzp = e7["kHZP"]
        k_hfp = 1.0 / (1.0 / k_hzp - dc_model * dd.DELTA_T / dd.PCM)
        for state, k in (("hzp", k_hzp), ("hfp", k_hfp)):
            if (cid, state) in drop:
                continue
            kb = [k + (0.001 if i % 2 else -0.001) + (shape(cid, state, i) if shape else 0.0) for i in range(n)]
            rows.append({"case": cid, "state": state, "fuelK": dd.FUEL_K[state], "subset": sub, "content": case["content"],
                         "particles": 20000, "batches": n, "inactive": 100, "seed": dd.SEED[state],
                         "k": k, "kStd": SIGMA_K, "kBatches": kb, "openmc": "0.15.3", "crossSections": "/root/nuclear_data/endfb-viii.0-hdf5/cross_sections.xml",
                         "wallS": 0.0, "cpuS": 0.0,
                         "loadBefore": 0.0, "loadAfter": 0.0})
    return rows


def write(rows):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "runs.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return dd.load_runs(p, REF)


def analyse(rows):
    return dd.analyse(write(rows), REF)


class Reference(unittest.TestCase):
    def test_the_sixteen_cases_and_their_coefficients_recompute(self):
        cases = REF["cases"]
        self.assertEqual(len(cases), 16)
        self.assertEqual({s: sum(1 for c in cases if c["subset"] == s) for s in dd.SUBSETS}, {"uo2": 7, "reactor-mox": 5, "weapons-mox": 4})
        for c in cases:
            e = c["endfb7"]
            dc = (1 / e["kHZP"] - 1 / e["kHFP"]) * dd.PCM / dd.DELTA_T
            self.assertLess(abs(dc - e["dc"]), 0.02, c["id"])


class Analysis(unittest.TestCase):
    def test_a_model_equal_to_the_reference_has_no_bias(self):
        m = analyse(planted_rows())
        self.assertEqual(m["summary"]["computed"], 16)
        for cid, e in m["A"]["cases"].items():
            self.assertTrue(e["computed"], cid)
            self.assertEqual(e["label"], "good", cid)
            self.assertLess(abs(e["relative"]), 1e-9, cid)
        for sub, e in m["C"].items():
            self.assertFalse(e["systematicDeficit"], sub)
            self.assertFalse(e["systematicExcess"], sub)
        items = m["decision"]["items"]
        self.assertTrue(any(i.startswith("1.") for i in items))
        self.assertTrue(items[-1].startswith("6."))

    def test_the_planted_coefficient_is_recovered_with_its_sigma(self):
        target = -3.0
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: target))
        for case in REF["cases"]:
            e = m["A"]["cases"][case["id"]]
            self.assertAlmostEqual(e["dc"], target, delta=1e-9, msg=case["id"])
            kh = case["endfb7"]["kHZP"]
            kf = 1.0 / (1.0 / kh - target * dd.DELTA_T / dd.PCM)
            sig = ((SIGMA_K / kh ** 2) ** 2 + (SIGMA_K / kf ** 2) ** 2) ** 0.5 * dd.PCM / dd.DELTA_T
            self.assertAlmostEqual(e["sigmaDc"], sig, delta=1e-12, msg=case["id"])

    def test_a_planted_uo2_deficit_is_declared_for_uo2_only(self):
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: 0.85 * dc if sub == "uo2" else dc))
        self.assertTrue(m["C"]["uo2"]["systematicDeficit"])
        self.assertFalse(m["C"]["uo2"]["systematicExcess"])
        self.assertFalse(m["C"]["reactor-mox"]["systematicDeficit"])
        self.assertFalse(m["C"]["weapons-mox"]["systematicDeficit"])
        self.assertAlmostEqual(m["C"]["uo2"]["meanRelative"], 0.15, places=6)
        items = m["decision"]["items"]
        self.assertTrue(any(i.startswith("2.") and "uo2" in i for i in items))
        self.assertFalse(any(i.startswith("1.") for i in items))

    def test_a_planted_weapons_excess_is_declared(self):
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: 1.15 * dc if sub == "weapons-mox" else dc))
        self.assertTrue(m["C"]["weapons-mox"]["systematicExcess"])
        self.assertFalse(m["C"]["weapons-mox"]["systematicDeficit"])
        self.assertFalse(m["C"]["uo2"]["systematicExcess"])
        items = m["decision"]["items"]
        self.assertTrue(any(i.startswith("3.") and "weapons-mox" in i for i in items))

    def test_a_missing_case_is_not_computed_and_named(self):
        m = analyse(planted_rows(drop={("uo2-3.1", "hfp")}))
        self.assertFalse(m["A"]["cases"]["uo2-3.1"]["computed"])
        self.assertEqual(m["summary"]["computed"], 15)
        self.assertEqual(m["C"]["uo2"]["n"], 6)
        self.assertEqual(m["D"]["missing"], ["uo2-3.1/hfp"])
        items = m["decision"]["items"]
        self.assertTrue(any(i.startswith("5.") and "uo2-3.1/hfp" in i for i in items))
        self.assertTrue(any(i.startswith("1.") for i in items))

    def test_an_unconverged_row_makes_its_case_not_computed_and_is_named(self):
        def drift(cid, state, i):
            if cid == "uo2-1.6" and state == "hfp":
                return -0.0005 if i < 350 else 0.0005
            return 0.0
        m = analyse(planted_rows(shape=drift))
        self.assertFalse(m["A"]["cases"]["uo2-1.6"]["computed"])
        self.assertEqual(m["D"]["unconverged"], ["uo2-1.6/hfp"])
        self.assertFalse(m["D"]["rows"]["uo2-1.6/hfp"]["converged"])
        self.assertEqual(m["summary"]["computed"], 15)
        items = m["decision"]["items"]
        self.assertTrue(any(i.startswith("5.") and "uo2-1.6/hfp" in i for i in items))


class Labels(unittest.TestCase):
    def test_eleven_good_cases_without_a_pattern_is_a_mixed_outcome_not_item_one(self):
        off = {"uo2-0.711": 1.30, "uo2-1.6": 0.70, "reactor-mox-1.0": 1.30, "reactor-mox-2.0": 0.70, "weapons-mox-1.0": 1.30}
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: off.get(cid, 1.0) * dc))
        self.assertEqual(m["summary"]["goodOrPlausible"], 11)
        self.assertFalse(any(m["C"][s]["systematicDeficit"] or m["C"][s]["systematicExcess"] for s in m["C"]))
        items = m["decision"]["items"]
        self.assertFalse(any(i.startswith("1.") for i in items))
        four = [i for i in items if i.startswith("4.")]
        self.assertEqual(len(four), 1)
        for cid in off:
            self.assertIn(cid, four[0])

    def test_within_ten_percent_follows_the_relative_difference(self):
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: {"uo2-0.711": 0.85, "uo2-1.6": 0.95}.get(cid, 1.0) * dc))
        self.assertFalse(m["A"]["cases"]["uo2-0.711"]["within10"])
        self.assertTrue(m["A"]["cases"]["uo2-1.6"]["within10"])
        self.assertAlmostEqual(m["A"]["cases"]["uo2-0.711"]["relative"], 0.15, places=6)

    def test_the_k_offset_is_reported_wherever_the_hzp_row_exists(self):
        m = analyse(planted_rows(drop={("uo2-3.1", "hfp")}))
        e = m["B"]["cases"]["uo2-3.1"]
        self.assertTrue(e["computed"])
        self.assertAlmostEqual(e["offsetPcm"], 0.0, places=6)
        m2 = analyse(planted_rows(drop={("uo2-3.1", "hzp")}))
        self.assertFalse(m2["B"]["cases"]["uo2-3.1"]["computed"])

    def test_z_uses_the_error_of_the_reference_and_of_the_model(self):
        import math
        m = analyse(planted_rows(dc_of=lambda cid, sub, dc: dc + 0.3 if cid == "uo2-0.711" else dc))
        e = m["A"]["cases"]["uo2-0.711"]
        want = 0.3 / math.hypot(e["refSigma"], e["sigmaDc"])
        self.assertAlmostEqual(e["z"], want, places=9)
        self.assertGreater(e["refSigma"], 0.0)
        self.assertLess(abs(e["z"]), 0.3 / e["sigmaDc"])               # the reference error is part of the denominator

    def test_the_drift_check_looks_only_at_the_active_batches(self):
        # a large offset in the first 100 (inactive) batches is not a drift; the windows are batches 101-350 and 351-600
        m = analyse(planted_rows(shape=lambda cid, state, i: 0.05 if i < 100 else 0.0))
        self.assertEqual(m["D"]["unconverged"], [])
        self.assertEqual(m["summary"]["computed"], 16)
        m2 = analyse(planted_rows(shape=lambda cid, state, i: 0.01 if 100 <= i < 350 else 0.0))
        self.assertEqual(len(m2["D"]["unconverged"]), 32)

    def test_the_spread_is_the_range_of_the_three_reference_libraries(self):
        m = analyse(planted_rows())
        self.assertAlmostEqual(m["A"]["cases"]["uo2-0.711"]["spread"], 0.11, places=9)       # -4.07, -4.16, -4.18
        self.assertAlmostEqual(m["A"]["cases"]["weapons-mox-6.0"]["spread"], 0.11, places=9)  # V -2.57, VI -2.46, VII.0 -2.49

    def test_labels_follow_z_at_the_bands(self):
        self.assertEqual(dd.label(0.99), "good")
        self.assertEqual(dd.label(1.01), "plausible")
        self.assertEqual(dd.label(2.01), "fails")
        self.assertEqual(dd.label(-2.01), "fails")


class Refusals(unittest.TestCase):
    def test_load_runs_refuses_bad_rows(self):
        def mutate(f):
            rows = planted_rows()
            f(rows)
            return rows

        cases = {
            "unknown case": lambda rows: rows[0].update(case="uo2-9.9"),
            "duplicate": lambda rows: rows.append(dict(rows[0])),
            "wrong particles": lambda rows: rows[0].update(particles=10000),
            "wrong seed": lambda rows: rows[0].update(seed=2),
            "wrong fuelK": lambda rows: rows[1].update(fuelK=600),
            "unknown state": lambda rows: rows[0].update(state="warm"),
            "missing kBatches": lambda rows: rows[0].pop("kBatches"),
            "short kBatches": lambda rows: rows[0].update(kBatches=rows[0]["kBatches"][:599]),
            "another OpenMC version": lambda rows: rows[0].update(openmc="0.14.0"),
            "another cross-section library": lambda rows: rows[0].update(crossSections="/root/nuclear_data/endfb-vii.1-hdf5/cross_sections.xml"),
            "no cross-section library": lambda rows: rows[0].pop("crossSections"),
            "another subset": lambda rows: rows[0].update(subset="mox-weapons"),
            "another content": lambda rows: rows[0].update(content="9.99"),
        }
        for name, f in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                write(mutate(f))


class Runner(unittest.TestCase):
    def test_a_case_given_twice_in_one_call_is_refused(self):
        try:
            from pipeline.openmc import doppler_run as dr
        except ImportError:                      # the runner imports POSIX modules: it runs in WSL only
            self.skipTest("the runner imports POSIX modules")
        with self.assertRaises(SystemExit) as cm:
            dr.main(["--case", "uo2-3.1/hzp", "--case", "uo2-3.1/hzp", "--dry"])
        self.assertIn("more than once", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
