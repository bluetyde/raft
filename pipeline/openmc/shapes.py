"""Power-shape tally for the library's `shapes` section (docs/library-format.md section 10; plan 02 section 5).

Basis "fission" (fission rate, one basis per library), per fuel region x axial bin: every fuel element and every fuel follower,
each named by its grid position in core_model (cell.name == position label, e.g. "C3"). The tallied bins span the active fuel height
(-19.05 .. +19.05 cm) in AXIAL_BINS equal bins, and a second tally counts each region's total fission. A fuel follower's fuel moves
with its rod and can hang below the core (never above it); regular fuel never leaves the active height. So `extract` adds one bin
below the core, [follower_bottom(), -19.05], holding each region's total minus its binned fission (zero for regular elements), and
normalizes over the total: every shape is a fraction of all fuel fission (library-format section 10). The tallies are unchanged, so
cached runs are re-extracted, not re-run.

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


def follower_bottom() -> float:
    """Lowest point follower fuel reaches (fully inserted rod): the absorber's bottom (-HALF_FUEL) minus the follower fuel length,
    which core_model makes equal to the absorber length (ffcr_layers)."""
    geo = json.loads((core_model.DATA / "jsi_core_geometry.json").read_text(encoding="utf-8"))
    length = geo["controlRods"]["fueledFollower"]["absorber"]["lengthIn"] * core_model.IN
    return -core_model.HALF_FUEL - length


def library_edges(n: int = AXIAL_BINS) -> list[float]:
    """Axial edges of the exported shape: the below-core bin, then the tallied bins."""
    return [follower_bottom()] + axial_edges(n)


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
        tmean = tot.mean.reshape(len(labels))
        tstd = tot.std_dev.reshape(len(labels))
    values = np.concatenate([mean, std, tmean[:, None], tstd[:, None]], axis=1)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError(f"{statepoint}: non-finite or negative shape tallies")
    below = tmean - mean.sum(axis=1)                 # fission outside the tallied height: follower fuel below the core
    tol = 1e-9 * np.maximum(tmean, 1e-300)
    if np.any(below < -tol):
        raise ValueError(f"{statepoint}: a region's binned fission exceeds its total ({below.min():.3e})")
    below = np.where(np.abs(below) <= tol, 0.0, below)
    followers = {core_model.ROD_AT[r] for r in ("K", "V", "R")}
    stray = [l for l, b in zip(labels, below) if b > 0 and l not in followers]
    if stray:
        raise ValueError(f"{statepoint}: fission outside the active height in regular elements {stray}")
    full = np.concatenate([below[:, None], mean], axis=1)
    total = float(tmean.sum())
    frac = full / total
    # the below-core bin's uncertainty: the total's (it is the larger, correlated part); flagged approximate in the library notes
    below_std = np.where(below > 0, tstd, 0.0)
    full_std = np.concatenate([below_std[:, None], std], axis=1)
    rel = np.divide(full_std, full, out=np.full_like(full_std, np.inf), where=full > 0)
    return {"basis": "fission", "normalization": "fraction-of-total-power", "elements": labels,
            "axialEdgesCm": library_edges(n_axial), "base": frac.tolist(), "baseUnc": rel.tolist(),
            "belowCoreFraction": float(below.sum() / total), "maxRelUnc": float(rel[np.isfinite(rel)].max()),
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
          f"median rel. unc {rep['medianRelUnc']:.3f}, max {rep['maxRelUnc']:.3f}; below core {rep['belowCoreFraction']:.4f}; "
          f"{rep['seconds']:.0f} s")
    if a.out:
        a.out.write_bytes((json.dumps(rep) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
