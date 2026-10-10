"""Write pipeline/openmc/data/beavrs_core.json from a clone of mit-crpg/BEAVRS (MIT licence, see BEAVRS-LICENSE).

Run where OpenMC is installed (the BEAVRS builder imports it):
    python pipeline/openmc/data/make_beavrs_core.py ~/beavrs

The JSON is committed; nothing is imported from the clone when a library is exported. Template rows run from the
top of the core map (north) down; the sweep's mesh tallies are ordered (z, y, x) with x fastest and y up, so
template row r sits at y index 18 - r (checked 2026-10-07 with an asymmetric bank).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "beavrs_core.json"
LABEL = re.compile(r"^([A-Z])_+(\d+)$")
BANK_ORDER = ["A", "B", "C", "D", "SA", "SB", "SC", "SD", "SE"]


def label(name: str) -> str:
    m = LABEL.match(name)
    return f"{m.group(1)}{m.group(2)}" if m else ""


def build(clone: Path) -> dict:
    sys.path.insert(0, str(clone / "models" / "openmc"))
    import beavrs.constants as c
    from beavrs.core import Core

    # the position tables are plain class data once the instance builders are bypassed
    core = Core.__new__(Core)
    core._set_enrichment_positions()
    core._set_rcca_positions()

    assemblies = []
    for r, row in enumerate(Core.core_lattice_template):
        for col, name in enumerate(row):
            if not label(name):
                continue
            assemblies.append({
                "label": label(name), "col": col, "row": r, "x": col, "y": 18 - r,
                "enrichment": core.enr_positions[name],
                "bank": core.rcca_positions.get(name),
            })
    banks = {b: sorted(a["label"] for a in assemblies if a["bank"] == b) for b in BANK_ORDER}
    return {
        "source": "mit-crpg/BEAVRS (MIT licence, BEAVRS-LICENSE), models/openmc/beavrs/core.py and constants.py",
        "sourceHead": "1ccae04",
        "orientation": "col = lattice x index (west to east); row = template row (north to south); y = 18 - row, the mesh tally's y index (y up)",
        "latticePitchCm": c.latticePitch,
        "latticeSize": 19,
        "activeFuelBotCm": c.fuel_ActiveFuel_bot,
        "activeFuelTopCm": c.fuel_ActiveFuel_top,
        "pelletRadiusCm": c.pelletOR,
        "pinPitchCm": c.pinPitch,
        "fuelPinsPerAssembly": 264,
        "rcca": {"stepWidthCm": c.rcca_StepWidth, "stepsTotal": 228, "stepsBite": c.rcca_bank_steps_withdrawn_default["D"],
                 "banks": banks},
        "vesselCm": {"barrelIR": c.coreBarrelIR, "barrelOR": c.coreBarrelOR, "baffleWidth": c.baffleWidth,
                     "linerIR": c.linerIR, "rpvIR": c.rpvIR, "rpvOR": c.rpvOR},
        "assemblies": assemblies,
    }


if __name__ == "__main__":
    data = build(Path(sys.argv[1]).expanduser())
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(data['assemblies'])} assemblies, {sum(len(v) for v in data['rcca']['banks'].values())} RCCA")
