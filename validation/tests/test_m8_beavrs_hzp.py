"""Tests for validation/m8_beavrs_hzp.py on a planted reactivity model (the real runs are analysed once, by the script)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation import m8_beavrs_hzp as bv

SIGMA_PCM = 20.0
BW = 10.0                                     # planted boron worth, pcm/ppm
ITC_F = -3.0                                  # planted pcm/F


def cum_from_boron():
    """Cumulative bank worths that make the model's critical boron equal the measured one at every measured state (S3, S5, S6 interpolated)."""
    c = {s: -BW * (bv.CB[s][0] - 975.0) for s in bv.CB}
    c[3] = (c[2] + c[4]) / 2
    c[5] = c[4] + (c[7] - c[4]) / 3
    c[6] = c[4] + 2 * (c[7] - c[4]) / 3
    return c


def line(cid, spec, rho_pcm, drift=0.0, sigma=SIGMA_PCM):
    rho = rho_pcm / bv.PCM
    k = 1.0 / (1.0 - rho)
    n = spec["batches"]
    batches = [k + (0.001 if i % 2 else -0.001) + drift * i for i in range(n)]
    return {"case": cid, **spec, "k": k, "kStd": sigma / bv.PCM * k ** 2, "kBatches": batches}


def planted_runs(cum, r0=0.0, itc=ITC_F, drift=None, skip=()):
    out = []
    for cid, spec in bv.cases().items():
        if cid in skip:
            continue
        rho = r0 - cum[spec["state"]] - BW * (spec["boron"] - 975.0) + itc * (spec["temperature"] - bv.T_HZP) * 1.8
        out.append(line(cid, spec, rho, drift.get(cid, 0.0) if drift else 0.0))
    return out


def load(lines):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "runs.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return bv.load_runs(p)


class Cases(unittest.TestCase):
    def test_the_protocols_twenty_cases(self):
        c = bv.cases()
        self.assertEqual(len(c), 20)
        self.assertEqual({s: sum(1 for v in c.values() if v["series"] == s) for s in "WBKT"}, {"W": 8, "B": 4, "K": 4, "T": 4})
        self.assertEqual(c["W3"]["state"], 3)
        self.assertEqual(bv.banks_in(3), ["D", "C", "B"])
        self.assertEqual(c["B2"]["boron"], 810.0)
        self.assertEqual((c["K7a"]["boron"], c["K7b"]["boron"]), (408.0, 608.0))
        self.assertEqual(c["T2m"]["temperature"], bv.T_HZP - 30.0)
        self.assertEqual((c["T0p"]["particles"], c["T0p"]["batches"]), (100000, 800))
        self.assertEqual((c["W0"]["particles"], c["W0"]["batches"], c["W0"]["inactive"]), (60000, 300, 100))
        self.assertAlmostEqual(bv.total_worth()[0], 6042.0)


class Analysis(unittest.TestCase):
    def test_planted_values_come_back(self):
        cum = cum_from_boron()
        m = bv.analyse(load(planted_runs(cum, r0=120.0)))
        self.assertAlmostEqual(m["D"]["S0"]["bw"], BW, places=6)
        for s, e in m["A"]["states"].items():
            self.assertAlmostEqual(e["errorPpm"], 12.0, places=6)                      # 120 pcm / 10 pcm per ppm at every state
        self.assertTrue(m["A"]["aggregate"]["systematic"])                              # all five agree, no spread
        self.assertAlmostEqual(m["A"]["aggregate"]["meanErrorPcm"], 120.0, places=6)
        self.assertAlmostEqual(m["B"]["banks"]["D"]["worthPcm"], cum[1], places=6)
        self.assertAlmostEqual(m["B"]["total"]["worthPcm"], cum[7], places=6)
        self.assertAlmostEqual(m["C"][0]["itcPcmPerF"], ITC_F, places=6)
        self.assertAlmostEqual(m["C"][2]["difference"], ITC_F - (-8.01), places=6)
        self.assertEqual(m["E"]["unconverged"], [])
        self.assertTrue(any(i.startswith("2.") for i in m["decision"]["items"]))

    def test_labels_follow_z_and_a_failed_bank_is_named(self):
        cum = cum_from_boron()
        # the measured worths exactly: a bank worth of D that is 5 sigma off must fail, the others good
        measured = {0: 0.0}
        for i, b in enumerate(bv.BANKS):
            measured[i + 1] = measured[i] + bv.WORTH[b][0]
        measured[1] += 5 * (bv.WORTH["D"][1] ** 2 + 2 * SIGMA_PCM ** 2) ** 0.5
        for s in range(2, 8):
            measured[s] += measured[1] - bv.WORTH["D"][0]
        m = bv.analyse(load(planted_runs(measured)))
        self.assertEqual(m["B"]["banks"]["D"]["label"], "fails")
        self.assertEqual(m["B"]["banks"]["C"]["label"], "good")
        self.assertEqual(bv.label(1.0), "good")
        self.assertEqual(bv.label(-1.5), "plausible")
        self.assertEqual(bv.label(2.01), "fails")
        self.assertTrue(any(i.startswith("3.") and "D" in i for i in m["decision"]["items"]))

    def test_a_good_model_has_no_offset_and_item_one(self):
        cum = cum_from_boron()
        m = bv.analyse(load(planted_runs(cum, r0=0.0)))
        self.assertFalse(m["A"]["aggregate"]["systematic"])                             # mean 0
        self.assertTrue(all(e["label"] == "good" for e in m["A"]["states"].values()))
        self.assertTrue(any(i.startswith("1.") for i in m["decision"]["items"]))
        self.assertFalse(m["decision"]["libraryChanged"])

    def test_only_s4_and_s7_are_marked_sensitive_and_only_above_five_percent(self):
        cum = cum_from_boron()
        runs = planted_runs(cum, r0=0.0)
        m = bv.analyse(load(runs))
        self.assertFalse(m["D"]["sensitive"])
        self.assertFalse(m["A"]["states"][4]["sensitiveToConversion"])
        # a boron worth 10 % larger at S7 than at S0: the S7 pair of cases
        for r in runs:
            if r["case"] in ("K7a", "K7b"):
                rho = (1 - 1 / r["k"]) * bv.PCM
                spec = {k: r[k] for k in ("series", "state", "boron", "temperature", "particles", "batches", "inactive")}
                new = line(r["case"], spec, rho - (BW * 0.1) * (r["boron"] - 508.0))
                r.update(k=new["k"], kStd=new["kStd"], kBatches=new["kBatches"])
        m2 = bv.analyse(load(runs))
        self.assertTrue(m2["D"]["sensitive"])
        self.assertTrue(m2["A"]["states"][4]["sensitiveToConversion"])
        self.assertTrue(m2["A"]["states"][7]["sensitiveToConversion"])
        self.assertNotIn("sensitiveToConversion", m2["A"]["states"][0])

    def test_itc_failure_is_item_four(self):
        m = bv.analyse(load(planted_runs(cum_from_boron(), itc=-6.0)))
        self.assertEqual(m["C"][0]["label"], "fails")
        self.assertTrue(any(i.startswith("4.") for i in m["decision"]["items"]))

    def test_unconverged_and_missing_cases_are_not_computed_and_stay_out_of_decisions(self):
        cum = cum_from_boron()
        runs = load(planted_runs(cum, drift={"W3": 2e-5}, skip=("T2m", "K7a")))
        m = bv.analyse(runs)
        self.assertEqual(m["E"]["unconverged"], ["W3"])
        self.assertEqual(sorted(m["E"]["missing"]), ["K7a", "T2m"])
        self.assertFalse(m["B"]["banks"]["B"]["computed"])                              # W2 to W3
        self.assertFalse(m["B"]["banks"]["A"]["computed"])                              # W3 to W4
        self.assertTrue(m["B"]["banks"]["D"]["computed"])
        self.assertFalse(m["C"][2]["computed"])
        self.assertFalse(m["D"]["S7"]["computed"])                                      # the check on the boron worth is not computed, the conversion still is
        self.assertTrue(m["A"]["states"][7]["computed"])
        self.assertTrue(any(i.startswith("5.") and "W3" in i for i in m["decision"]["items"]))

    def test_too_few_critical_boron_states_leaves_the_decision_open(self):
        m = bv.analyse(load(planted_runs(cum_from_boron(), skip=("B1", "B2", "B4"))))
        self.assertFalse(m["A"]["aggregate"]["computed"])
        self.assertTrue(any(i.startswith("1/2.") for i in m["decision"]["items"]))


class Loader(unittest.TestCase):
    def test_anything_that_is_not_the_protocols_runs_is_refused(self):
        lines = planted_runs(cum_from_boron())
        with self.assertRaises(ValueError):
            load(lines + [lines[0]])                                                    # a case twice
        with self.assertRaises(ValueError):
            load([dict(lines[0], case="W9")])                                           # not a case
        with self.assertRaises(ValueError):
            load([dict(lines[0], particles=1000)])                                      # other settings
        with self.assertRaises(ValueError):
            load([dict(lines[0], boron=974.0)])
        with self.assertRaises(ValueError):
            load([dict(lines[0], kBatches=lines[0]["kBatches"][:-1])])                  # batch values missing


if __name__ == "__main__":
    unittest.main()
