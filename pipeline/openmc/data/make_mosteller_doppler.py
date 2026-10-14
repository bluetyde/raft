"""Write pipeline/openmc/data/mosteller_doppler.json and MOSTELLER-DOPPLER-LICENSE from mit-crpg/benchmarks (MIT licence).

The source is doppler-defect/make_inputs.py of mit-crpg/benchmarks. Its top-level data names are read with the ast module and
ast.literal_eval, not retyped. The generator's OpenMC model code is not copied; the model is built in doppler_run.py.

Run from the repo root (needs gh, logged in):
    python pipeline/openmc/data/make_mosteller_doppler.py                 # fetch the source with gh
    python pipeline/openmc/data/make_mosteller_doppler.py path/to/make_inputs.py   # or read a local copy

Integer temperature keys (300, 600, 900) are written as strings, as JSON requires.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "mosteller_doppler.json"
LICENSE_OUT = HERE / "MOSTELLER-DOPPLER-LICENSE"
REPO = "mit-crpg/benchmarks"
SOURCE_PATH = "doppler-defect/make_inputs.py"
NAMES = ("enrichments", "fuel_or", "clad_ir", "clad_or", "pitch", "clad_density", "water_comp", "composition")


def gh(*args: str) -> str:
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=True, encoding="utf-8").stdout


def fetch_raw(path: str) -> str:
    return gh(f"repos/{REPO}/contents/{path}", "-H", "Accept: application/vnd.github.raw")


def head_sha() -> str:
    return gh(f"repos/{REPO}/commits/HEAD", "--jq", ".sha").strip()


def extract(text: str) -> dict:
    found: dict = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in NAMES:
                found[name] = ast.literal_eval(node.value)
    missing = [n for n in NAMES if n not in found]
    if missing:
        raise SystemExit(f"the source does not define {missing}")
    return found


def stringify_keys(obj):
    if isinstance(obj, dict):
        return {str(k): stringify_keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [stringify_keys(v) for v in obj]
    return obj


def main(argv: list[str]) -> None:
    text = Path(argv[1]).expanduser().read_text(encoding="utf-8") if len(argv) > 1 else fetch_raw(SOURCE_PATH)
    data = stringify_keys(extract(text))
    sha = head_sha()
    out = {
        "source": f"{REPO} {SOURCE_PATH} at commit {sha} (MIT licence, see MOSTELLER-DOPPLER-LICENSE)",
        "units": "atom/b-cm for all densities, cm for lengths",
        "notes": ("Values transcribed by ast.literal_eval from the generator's top-level names; not retyped. "
                  "Dimensions and densities keyed by temperature in K as strings. Enrichment keys are the str() of the "
                  "float. Zero densities (U234 at 0.711 wt %) are kept as in the source. The generator's cross-section path, "
                  "settings and XML writing are not used."),
        **{n: data[n] for n in NAMES},
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    LICENSE_OUT.write_text(gh(f"repos/{REPO}/contents/LICENSE", "-H", "Accept: application/vnd.github.raw").replace("\r\n", "\n"),
                           encoding="utf-8", newline="\n")
    counts = {s: len(c) for s, c in data["enrichments"].items()}
    print(f"wrote {OUT} (commit {sha}), contents per subset {counts}; wrote {LICENSE_OUT.name}")


if __name__ == "__main__":
    main(sys.argv)
