"""Add the 1994 benchmark cores 133 and 134 to pipeline/openmc/data/jsi_core_occupancy.json.

Source: validation/data/jsi-core134/loading_map.json (Mele, Ravnik, Trkov, Nucl. Technol. 105 (1994), Fig. 3 and Fig. 4, read by eye). Positions
use the same labels and the same `other` codes as the entries parsed from the pulse database core maps: P transient rod, V safety, K shim, R
regulating, NI neutron source. The neutron source and the linear channel detector (outside the grid) are water in the model, as for 242 and 246.

Run from the repo root:  python -m pipeline.openmc.core134_occupancy
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OCC = REPO_ROOT / "pipeline" / "openmc" / "data" / "jsi_core_occupancy.json"
MAP = REPO_ROOT / "validation" / "data" / "jsi-core134" / "loading_map.json"
RODS = {"C4": "P", "C10": "V", "D1": "R", "D10": "K"}
NOTE = "cores 133 and 134: Mele, Ravnik, Trkov, Nucl. Technol. 105 (1994) Fig. 3 and Fig. 4 (validation/data/jsi-core134, pipeline/openmc/core134_occupancy.py)"


def entry(fuel: dict[str, str], source_at: str) -> dict:
    return {"fuel": dict(sorted(fuel.items())), "other": {**RODS, source_at: "NI"}, "fuelCount": len(fuel)}


def main() -> int:
    m = json.loads(MAP.read_text(encoding="utf-8"))
    inner = {pos: el for pos, el in m["fuel"].items() if pos[0] in "ABCD"}
    core134 = entry(m["fuel"], "E7")
    core133 = entry({**inner, **m["core133"]["eRing"]}, "E12")
    assert core134["fuelCount"] == 45 and core133["fuelCount"] == 40, (core134["fuelCount"], core133["fuelCount"])
    d = json.loads(OCC.read_text(encoding="utf-8"))
    d["cores"]["133"], d["cores"]["134"] = core133, core134
    if NOTE not in d["source"]:
        d["source"] = d["source"] + "; " + NOTE
    OCC.write_bytes((json.dumps(d, indent=1) + "\n").encode("utf-8"))
    print("cores in the file:", sorted(d["cores"]), "fuel counts 133/134:", core133["fuelCount"], core134["fuelCount"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
