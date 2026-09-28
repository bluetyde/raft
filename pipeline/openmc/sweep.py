"""M2 library sweep: every state the per-core library needs, run through the TD-06 cache (pipeline/runs/cache.py).

One case = one OpenMC run of the full core at one state, tallying k, the power shape (shapes.py) and, for the reference state,
beta_eff and Lambda (IFP). Families (plan 02 section 3, separable form):
  reference     the measured critical rods, 294 K
  rod-worth     one rod at a time over its grid, others at the reference
  fuel-temp     fuel temperature grid, rods at the reference
  coolant-temp  water temperature grid, rods at the reference
  holdout       fixed pseudo-random joint states between grid points (tests the separable approximation; plan 07)

Every fuel region has the calibrated uniform burnup B246 (docs/validation/m2-burnup-results.md), for both cores.

Resumable: a completed case is reused, an interrupted one re-run; stopping loses at most the case that was running. Progress goes
to stdout and to <cache>/sweep.log. Run in the openmc-vr env (WSL) from the repo root:
  python -m pipeline.openmc.sweep --core 242 --core 246 [--dry-run] [--quick]
Then:  python -m pipeline.openmc.sweep --core 242 --core 246 --summary   (writes pipeline/openmc/results/sweep_<core>.json)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from pipeline.openmc import core_model, shapes
from pipeline.runs import cache

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "pipeline" / "openmc" / "results"
QUICK_CACHE = REPO_ROOT / "pipeline" / "cache" / "quick"           # never mixed with production results
B246 = 23.675258421961058                                           # m2_burnup_report.json
REFERENCE_RODS = {"242": {"T": 0.0, "K": 499.0, "V": 200.0, "R": 500.0},     # s242 header (400 W)
                  "246": {"T": 0.0, "K": 536.6, "V": 200.0, "R": 535.0}}     # pungercic2024 section 2.3.1
ROD_GRID = {"T": [150, 300, 450, 600, 750, 900],
            "K": [200, 300, 400, 500, 600, 700, 800, 900],
            "V": [300, 400, 500, 600, 700, 800, 900],
            "R": [200, 300, 400, 500, 600, 700, 800, 900]}
TFUEL_GRID = [400.0, 500.0, 600.0, 800.0]
TCOOL_GRID = [313.15, 333.15]
HOLDOUT_N, HOLDOUT_SEED = 6, 20260927
STANDARD = {"particles": 20000, "batches": 150, "inactive": 50}
QUICK = {"particles": 4000, "batches": 60, "inactive": 20}


def plan(core: str) -> list[dict]:
    ref = REFERENCE_RODS[core]
    cases = [{"family": "reference", "rods": dict(ref), "tfuel": None, "tcool": None, "kinetics": True}]
    for rod, grid in ROD_GRID.items():
        for s in grid:
            if float(s) != ref[rod]:
                cases.append({"family": "rod-worth", "rod": rod, "rods": dict(ref, **{rod: float(s)}), "tfuel": None, "tcool": None,
                              "kinetics": False})
    for t in TFUEL_GRID:
        cases.append({"family": "fuel-temp", "rods": dict(ref), "tfuel": t, "tcool": None, "kinetics": False})
    for t in TCOOL_GRID:
        cases.append({"family": "coolant-temp", "rods": dict(ref), "tfuel": None, "tcool": t, "kinetics": False})
    rng = random.Random(f"{HOLDOUT_SEED}-{core}")
    for _ in range(HOLDOUT_N):
        rods = {"T": float(rng.randrange(0, 901, 5)), "K": float(rng.randrange(200, 901, 5)),
                "V": float(rng.randrange(200, 901, 5)), "R": float(rng.randrange(200, 901, 5))}
        cases.append({"family": "holdout", "rods": rods, "tfuel": round(rng.uniform(294.0, 600.0), 1), "tcool": None,
                      "kinetics": False})
    for c in cases:
        c["core"] = core
        c["name"] = describe(c)
    return cases


def describe(c: dict) -> str:
    rods = ",".join(f"{k}={v:g}" for k, v in c["rods"].items())
    extra = "".join(f" {k}={c[k]:g}" for k in ("tfuel", "tcool") if c[k] is not None)
    return f"{c['core']} {c['family']} {rods}{extra}"


def build_case(c: dict, stats: dict):
    import openmc
    openmc.reset_auto_ids()                                          # stable IDs, so the same case always gets the same key
    ov = {"burnup": B246}
    for k in ("tfuel", "tcool"):
        if c[k] is not None:
            ov[k] = c[k]
    model = core_model.build(c["core"], c["rods"], stats["particles"], stats["batches"], stats["inactive"],
                             kinetics=c["kinetics"], overrides=ov)
    labels = shapes.add_shape_tallies(model)
    return model, labels


def extract_fn(labels: list[str], batches: int):
    def extract(case_dir: Path) -> dict:
        import openmc
        sp = case_dir / f"statepoint.{batches}.h5"
        out = shapes.extract(sp, labels)
        with openmc.StatePoint(sp) as p:
            out["k"], out["kStd"] = p.keff.nominal_value, p.keff.std_dev
            try:
                kin = p.get_kinetics_parameters()
            except LookupError:
                kin = None
            if kin is not None and kin.beta_effective is not None:
                g = kin.beta_effective
                out["betaGroups"] = [x.nominal_value for x in g]
                out["betaGroupsStd"] = [x.std_dev for x in g]
                out["lambdaS"] = kin.generation_time.nominal_value
                out["lambdaStdS"] = kin.generation_time.std_dev
        return out
    return extract


def log(root: Path, msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "sweep.log").open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def sample(cases: list[dict]) -> list[dict]:
    """Testing only: the first case of each (core, family)."""
    seen, out = set(), []
    for c in cases:
        if (c["core"], c["family"]) not in seen:
            seen.add((c["core"], c["family"]))
            out.append(c)
    return out


def run(cores: list[str], stats: dict, root: Path, only_sample: bool = False) -> int:
    cases = [c for core in cores for c in plan(core)]
    if only_sample:
        cases = sample(cases)
    log(root, f"sweep start: {len(cases)} cases, {stats}, cache {root}")
    failed, times = [], []
    for i, c in enumerate(cases, 1):
        t0 = time.time()
        model, _ = build_case(c, stats)
        try:
            key, _ = cache.run_openmc_case(model, root)
        except cache.RunFailed as e:
            failed.append(c["name"])
            log(root, f"[{i}/{len(cases)}] FAILED {c['name']}: {e}")
            continue
        dt = time.time() - t0
        reused = dt < 20.0
        if not reused:
            times.append(dt)
        eta = "" if not times else f", about {(len(cases) - i) * sum(times) / len(times) / 3600:.1f} h left"
        log(root, f"[{i}/{len(cases)}] {'reused' if reused else f'{dt / 60:.1f} min'} {c['name']} ({key[:10]}){eta}")
    log(root, f"sweep end: {len(cases) - len(failed)} completed, {len(failed)} failed" + (f": {failed}" if failed else ""))
    return 1 if failed else 0


SUMMARY_EXTRACTOR = ("sweep-summary", "2")        # 2: shapes include the below-core bin (shapes.extract)


def summary(cores: list[str], stats: dict, root: Path, out_dir: Path, only_sample: bool = False) -> int:
    import os
    import tempfile
    out_dir.mkdir(parents=True, exist_ok=True)
    missing_total = 0
    for core in cores:
        rows, missing, digests = [], 0, set()
        for c in (sample(plan(core)) if only_sample else plan(core)):
            model, labels = build_case(c, stats)
            with tempfile.TemporaryDirectory() as tmp:
                inputs = cache.openmc_inputs(model, Path(tmp))
            digest = cache.data_digest(cache.openmc_data_files(model), root)
            key = cache.case_key(inputs, digest, cache.openmc_versions())
            verify = cache.openmc_verify(stats["batches"])
            if not cache.is_complete(root / "raw" / key, verify):
                print(f"not complete: {c['name']}", file=sys.stderr)
                missing += 1
                continue
            d = cache.derived(key, *SUMMARY_EXTRACTOR, extract_fn(labels, stats["batches"]), verify, root)
            rows.append(dict(c, key=key, dataDigest=digest, **d))
            digests.add(digest)
        missing_total += missing
        rep = {"core": core, "burnup": B246, "stats": stats, "openmc": cache.openmc_versions(),
               "nuclearData": {"crossSections": os.environ.get("OPENMC_CROSS_SECTIONS", ""),
                               "note": "each case's dataDigest hashes the data files it used (pipeline/runs/cache.py)"},
               "extractor": list(SUMMARY_EXTRACTOR), "cases": rows, "complete": missing == 0}
        p = out_dir / f"sweep_{core}.json"
        p.write_bytes((json.dumps(rep, allow_nan=True) + "\n").encode("utf-8"))
        print(f"core {core}: {len(rows)} cases, {missing} missing -> {p}")
    return 1 if missing_total else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--core", action="append", choices=sorted(REFERENCE_RODS), required=True)
    ap.add_argument("--dry-run", action="store_true", help="list the cases and exit")
    ap.add_argument("--quick", action="store_true", help="testing only: low statistics, separate cache (pipeline/cache/quick)")
    ap.add_argument("--summary", action="store_true", help="extract completed cases to pipeline/openmc/results/")
    ap.add_argument("--sample", action="store_true", help="testing only: one case per family; requires --quick")
    a = ap.parse_args(argv)
    if a.sample and not a.quick:
        ap.error("--sample is for testing and needs --quick")
    stats, root = (QUICK, QUICK_CACHE) if a.quick else (STANDARD, cache.CACHE_ROOT)
    if a.dry_run:
        for core in a.core:
            for c in plan(core):
                print(c["name"])
        print(f"{sum(len(plan(c)) for c in a.core)} cases, {stats}")
        return 0
    if a.summary:
        return summary(a.core, stats, root, RESULTS if not a.quick else root / "results", a.sample)
    return run(a.core, stats, root, a.sample)


if __name__ == "__main__":
    raise SystemExit(main())
