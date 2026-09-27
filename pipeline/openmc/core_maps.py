"""Read which core position holds what from the JSI pulse-database core maps (242.pdf, 246.pdf).

Each position label (A1 ... F30) is printed just below its circle; the symbol inside the circle is a 4-digit fuel-element serial,
a control-rod letter (P = transient, V = safety, K = shim, R = regulating) or a channel code (CK central channel, OK irradiation
channel, PP pneumatic post, NI neutron source, TOK1/TOK2 triangular channels). A symbol is assigned to the nearest label below it
and counts only if that label is within MAX_DIST points: this drops the legend (which repeats the symbols) and the title block
(whose date year is also a 4-digit number). R13 ... R42 are storage-rack slots outside the core and are ignored.

Needs `pdftotext` (poppler; available in WSL Ubuntu).  Usage:  python -m pipeline.openmc.core_maps 242.pdf 246.pdf --out FILE
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MAX_DIST = 40.0          # points; symbols sit about 15-25 points above their label
SYMBOLS = {"K", "R", "P", "V", "CK", "OK", "PP", "NI", "TOK1", "TOK2"}


def words(pdf: Path) -> list[tuple[str, float, float]]:
    html = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    return [(m.group(5), (float(m.group(1)) + float(m.group(3))) / 2, (float(m.group(2)) + float(m.group(4))) / 2)
            for m in re.finditer(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)<', html)]


def occupancy(pdf: Path) -> dict:
    ws = words(pdf)
    labels = {w: (x, y) for w, x, y in ws if re.fullmatch(r"[A-F]\d{1,2}|R\d{1,2}", w)}
    occ: dict[str, list[str]] = {}
    for w, x, y in ws:
        if not (re.fullmatch(r"\d{4}", w) or w in SYMBOLS):
            continue
        cands = [(((lx - x) ** 2 + (ly - y) ** 2) ** 0.5, lab) for lab, (lx, ly) in labels.items() if ly > y - 2]
        if not cands:
            continue
        dist, lab = min(cands)
        if dist <= MAX_DIST and not lab.startswith("R"):
            occ.setdefault(lab, []).append(w)
    fuel = {lab: next(v for v in vs if re.fullmatch(r"\d{4}", v)) for lab, vs in occ.items() if any(re.fullmatch(r"\d{4}", v) for v in vs)}
    other = {lab: vs[0] for lab, vs in occ.items() if lab not in fuel}
    return {"fuel": dict(sorted(fuel.items())), "other": dict(sorted(other.items())), "fuelCount": len(fuel)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    out = {"source": "JSI TRIGA pulse database core maps (trigapulse.ijs.si); parsed by pipeline/openmc/core_maps.py",
           "cores": {p.stem: occupancy(p) for p in a.pdfs}}
    a.out.write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))
    for core, o in out["cores"].items():
        print(core, "fuel", o["fuelCount"], "other", o["other"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
