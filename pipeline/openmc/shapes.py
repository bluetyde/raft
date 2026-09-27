"""Power-shape tally for the library's `shapes` section (docs/library-format.md section 10; plan 02 section 5).

Basis "fission" (fission rate, one basis per library), per fuel region x axial bin: every fuel element and every fuel follower,
each named by its grid position in core_model (cell.name == position label, e.g. "C3"). Axial bins span the active fuel height
(-19.05 .. +19.05 cm) in AXIAL_BINS equal bins. A fuel follower's fuel moves with its rod, so part of it can sit outside the
binned height; that fraction is reported (`outsideFraction`) and the shape is normalized over the binned regions.

Run in the openmc-vr env (WSL):  python -m pipeline.openmc.shapes --core 242 --burnup 23.675 [--quick] [--out shape.json]
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
import time
from pathlib import Path

from pipeline.openmc import core_model

AXIAL_BINS = 15


def axial_edges(n: int = AXIAL_BINS) -> list[float]:
    h = core_model.HALF_FUEL
    return [-h + 2 * h * i / n for i in range(n + 1)]


def fuel_cells(model) -> dict[str, object]:
    """{position label: fuel cell}, from the names core_model gives fuel cells."""
    out = {}
    for c in model.geometry.get_all_cells().values():
        if c.fill is not None and getattr(c.fill, "name", "") == "U-ZrH1.6" and c.name:
            if c.name in out:
                raise ValueError(f"two fuel cells named {c.name}")
            out[c.name] = c
    if not out:
        raise ValueError("no named fuel cells; core_model must name fuel cells by position")
    return out


def add_shape_tallies(model, n_axial: int = AXIAL_BINS) -> list[str]:
    import openmc
    cells = fuel_cells(model)
    labels = sorted(cells, key=lambda s: (s[0], int(s[1:])))
    mesh = openmc.RegularMesh()
    mesh.lower_left, mesh.upper_right, mesh.dimension = (-100.0, -100.0, -core_model.HALF_FUEL), \
        (100.0, 100.0, core_model.HALF_FUEL), (1, 1, n_axial)
    cf = openmc.CellFilter([cells[l] for l in labels])
    t = openmc.Tally(name="shape")
    t.filters = [cf, openmc.MeshFilter(mesh)]
    t.scores = ["fission"]
    total = openmc.Tally(name="shape-total")
    total.filters = [cf]
    total.scores = ["fission"]
    model.tallies = openmc.Tallies(list(model.tallies) + [t, total])
    return labels


def extract(statepoint: Path, labels: list[str], n_axial: int = AXIAL_BINS) -> dict:
    import numpy as np
    import openmc
    with openmc.StatePoint(statepoint) as sp:
        t, tot = sp.get_tally(name="shape"), sp.get_tally(name="shape-total")
        mean = t.mean.reshape(len(labels), n_axial)
        std = t.std_dev.reshape(len(labels), n_axial)
        total = float(tot.mean.sum())
    binned = float(mean.sum())
    frac = mean / binned
    rel = np.divide(std, mean, out=np.full_like(std, np.inf), where=mean > 0)
    return {"basis": "fission", "normalization": "fraction-of-total-power (over binned regions)", "elements": labels,
            "axialEdgesCm": axial_edges(n_axial), "base": frac.tolist(), "baseUnc": rel.tolist(),
            "outsideFraction": 1.0 - binned / total, "maxRelUnc": float(rel[np.isfinite(rel)].max()),
            "medianRelUnc": float(np.median(rel[np.isfinite(rel)]))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--core", default="242")
    ap.add_argument("--rods", default="T=0,K=499,V=200,R=500")
    ap.add_argument("--burnup", type=float, default=None)
    ap.add_argument("--particles", type=int, default=20000)
    ap.add_argument("--batches", type=int, default=150)
    ap.add_argument("--inactive", type=int, default=50)
    ap.add_argument("--quick", action="store_true", help="testing only: 4000 x 60 (20 inactive)")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.quick:
        a.particles, a.batches, a.inactive = 4000, 60, 20
    import openmc
    openmc.reset_auto_ids()
    rods = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.rods.split(",")}
    ov = {} if a.burnup is None else {"burnup": a.burnup}
    model = core_model.build(a.core, rods, a.particles, a.batches, a.inactive, overrides=ov)
    labels = add_shape_tallies(model)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        sp = model.run(cwd=tmp, output=False)
        with openmc.StatePoint(sp) as p:
            k = p.keff
        rep = extract(Path(sp), labels)
    rep.update(core=a.core, rods=rods, burnup=a.burnup, k=k.nominal_value, kStd=k.std_dev, particles=a.particles,
               batches=a.batches, inactive=a.inactive, seconds=time.time() - t0)
    print(f"core {a.core} rods {rods}: k = {k.nominal_value:.5f} +- {k.std_dev:.5f}; {len(labels)} regions x {AXIAL_BINS} bins; "
          f"median rel. unc {rep['medianRelUnc']:.3f}, max {rep['maxRelUnc']:.3f}; outside {rep['outsideFraction']:.4f}; "
          f"{rep['seconds']:.0f} s")
    if a.out:
        a.out.write_bytes((json.dumps(rep) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
