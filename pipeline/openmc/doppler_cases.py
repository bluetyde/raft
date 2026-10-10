"""The 32 Doppler-defect cases of docs/validation/doppler-defect-protocol.md (pure Python, no OpenMC import).

Each subset (uo2, reactor-mox, weapons-mox) and content (enrichment or PuO2 content, in the order of the generator's data) is
one pin cell at hot zero power (fuel at 600 K) and at hot full power (fuel at 900 K). The contents and the counts are read from
pipeline/openmc/data/mosteller_doppler.json, not typed here.

Case ids are "<subset>-<content>/<state>", for example "uo2-3.1/hzp" or "weapons-mox-2.0/hfp".
"""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "mosteller_doppler.json"
SUBSETS = ("uo2", "reactor-mox", "weapons-mox")
HZP_K = 600
HFP_K = 900
SETTINGS = {"particles": 20000, "batches": 600, "inactive": 100}
SEEDS = {"hzp": 1, "hfp": 2}
STATES = {"hzp": HZP_K, "hfp": HFP_K}


def cases() -> "OrderedDict[str, dict]":
    data = json.loads(DATA.read_text(encoding="utf-8"))
    out: "OrderedDict[str, dict]" = OrderedDict()
    for subset in SUBSETS:
        for content in data["enrichments"][subset]:
            case = f"{subset}-{content}"
            for state, fuel_k in STATES.items():
                out[f"{case}/{state}"] = {
                    "case": case,
                    "subset": subset,
                    "content": content,
                    "state": state,
                    "fuelK": fuel_k,
                    "seed": SEEDS[state],
                    "particles": SETTINGS["particles"],
                    "batches": SETTINGS["batches"],
                    "inactive": SETTINGS["inactive"],
                }
    return out
