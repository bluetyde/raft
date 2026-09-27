"""Content-addressed cache for expensive transport runs (TD-06; plan 02 section 4).

Three guarantees, each covered by pipeline/tests/test_run_cache.py:
1. Changing model content invalidates a run: a case's key is a hash of its full inputs (the generated XML, not its parameters),
   the digest of the nuclear-data files actually used, and the code versions.
2. Changing only extraction logic rebuilds derived results without re-running transport: derived results are keyed by the raw
   case key plus the extractor's name and version.
3. An interrupted run is never read as complete: a case counts only when its status says `completed` **and** its verifier passes
   (for OpenMC: the final statepoint exists and has every batch). A crash leaves `running` or `failed`, which is re-run.

The core is independent of OpenMC (inputs are bytes; running and verifying are callables). The OpenMC helpers at the bottom import
openmc lazily, so this module and its tests run anywhere.

Layout under the cache root (pipeline/cache/, gitignored):
  raw/<key>/status.json        {"state": pending|running|failed|completed, "attempts": n, "errors": [...], "updated": ...}
  raw/<key>/inputs/<name>      the hashed inputs, kept for provenance
  raw/<key>/...                whatever the run writes (statepoints)
  derived/<key>.<extractor>.<version>.json
  data_digests.json            memo of nuclear-data file hashes by (path, size, mtime)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / "pipeline" / "cache"
STATES = ("pending", "running", "failed", "completed")


class RunFailed(RuntimeError):
    """A case failed every allowed attempt; its status.json lists each cause."""


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def data_digest(files: Iterable[Path], root: Path = CACHE_ROOT) -> str:
    """Digest of the nuclear-data files a case uses: each file's name and content hash, in sorted order. File hashes are memoized
    by (absolute path, size, mtime_ns), so a changed file is re-hashed."""
    memo_path = root / "data_digests.json"
    memo = json.loads(memo_path.read_text(encoding="utf-8")) if memo_path.exists() else {}
    h = hashlib.sha256()
    changed = False
    for f in sorted({Path(p).resolve() for p in files}):
        st = f.stat()
        tag = f"{st.st_size}:{st.st_mtime_ns}"
        entry = memo.get(str(f))
        if entry is None or entry["tag"] != tag:
            entry = {"tag": tag, "sha256": sha256_file(f)}
            memo[str(f)] = entry
            changed = True
        h.update(f.name.encode() + b"\0" + entry["sha256"].encode() + b"\n")
    if changed:
        _write_atomic(memo_path, (json.dumps(memo, indent=1, sort_keys=True) + "\n").encode())
    return h.hexdigest()


def case_key(inputs: Mapping[str, bytes], data: str, versions: Mapping[str, str]) -> str:
    """Hash of every input (name and bytes, length-prefixed so boundaries can't shift), the data digest and the versions."""
    h = hashlib.sha256(b"vr-case-v1\n")
    for name in sorted(inputs):
        blob = inputs[name]
        h.update(f"{len(name)}:{name}:{len(blob)}:".encode())
        h.update(blob)
    h.update(b"data:" + data.encode() + b"\n")
    h.update(b"versions:" + json.dumps(dict(versions), sort_keys=True).encode())
    return h.hexdigest()


def read_status(case_dir: Path) -> dict:
    p = case_dir / "status.json"
    if not p.exists():
        return {"state": "pending", "attempts": 0, "errors": []}
    st = json.loads(p.read_text(encoding="utf-8"))
    if st.get("state") not in STATES:
        raise ValueError(f"{p}: unknown state {st.get('state')!r}")
    return st


def _write_status(case_dir: Path, st: dict) -> None:
    st = dict(st, updated=_now())
    _write_atomic(case_dir / "status.json", (json.dumps(st, indent=1) + "\n").encode())


def is_complete(case_dir: Path, verify: Callable[[Path], bool]) -> bool:
    return read_status(case_dir)["state"] == "completed" and verify(case_dir)


def run_case(inputs: Mapping[str, bytes], data: str, versions: Mapping[str, str], run: Callable[[Path], None],
             verify: Callable[[Path], bool], root: Path = CACHE_ROOT, max_attempts: int = 2) -> tuple[str, Path]:
    """Return (key, case dir) of a completed case, reusing a verified completed one or running it (up to `max_attempts` more
    times). `run(case_dir)` does the work in case_dir; `verify(case_dir)` checks the outputs are whole."""
    key = case_key(inputs, data, versions)
    d = root / "raw" / key
    st = read_status(d)
    if st["state"] == "completed":
        if verify(d):
            return key, d
        st["errors"].append(f"{_now()} completed but failed verification on reuse; re-running")
    for name, blob in inputs.items():
        _write_atomic(d / "inputs" / name, blob)
    last: BaseException | None = None
    for _ in range(max_attempts):
        st["attempts"] += 1
        st["state"] = "running"
        _write_status(d, st)
        try:
            run(d)
        except Exception as e:  # recorded in status.json and re-raised after the last attempt, never swallowed
            st["errors"].append(f"{_now()} attempt {st['attempts']}: {type(e).__name__}: {e}")
            st["state"] = "failed"
            _write_status(d, st)
            last = e
            continue
        if verify(d):
            st["state"] = "completed"
            _write_status(d, st)
            return key, d
        st["errors"].append(f"{_now()} attempt {st['attempts']}: run returned but outputs failed verification")
        st["state"] = "failed"
        _write_status(d, st)
        last = None
    raise RunFailed(f"case {key[:12]} failed {max_attempts} attempt(s); see {d / 'status.json'}") from last


def derived(key: str, extractor: str, version: str, extract: Callable[[Path], dict], verify: Callable[[Path], bool],
            root: Path = CACHE_ROOT) -> dict:
    """Extraction product of a completed raw case, cached by (raw key, extractor, version). A new extractor version re-extracts
    from the same raw outputs; nothing is re-run. Refuses a raw case that isn't complete."""
    d = root / "raw" / key
    if not is_complete(d, verify):
        raise RunFailed(f"raw case {key[:12]} is not complete; refusing to extract")
    p = root / "derived" / f"{key}.{extractor}.{version}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    out = extract(d)
    _write_atomic(p, (json.dumps(out, indent=1, sort_keys=True) + "\n").encode())
    return out


# --- OpenMC helpers (import openmc lazily) ---------------------------------------------------------------------------------

def openmc_inputs(model, workdir: Path) -> dict[str, bytes]:
    """The generated XML of `model` (geometry, materials, settings, tallies), plus the content of any FileSource it reads, since
    settings.xml holds only that file's path.

    OpenMC numbers cells, surfaces and materials from global counters, so the same model built twice in one process gets different
    IDs and therefore a different key (a missed reuse, never a false one). Builders call openmc.reset_auto_ids() first."""
    import openmc
    workdir.mkdir(parents=True, exist_ok=True)
    model.export_to_xml(workdir)
    out = {f.name: f.read_bytes() for f in sorted(workdir.glob("*.xml"))}
    srcs = model.settings.source if isinstance(model.settings.source, list) else [model.settings.source]
    for s in srcs:
        if isinstance(s, openmc.FileSource):
            out["source-file.sha256"] = sha256_file(Path(s.path)).encode()
    return out


def openmc_data_files(model) -> list[Path]:
    """The HDF5 files of every nuclide and thermal-scattering table the model's materials use (from cross_sections.xml)."""
    import openmc.data
    lib = openmc.data.DataLibrary.from_xml()
    by_name = {name: Path(entry["path"]) for entry in lib.libraries for name in entry["materials"]}
    xs = Path(os.environ["OPENMC_CROSS_SECTIONS"])
    files = [xs]
    for m in model.materials:
        for nuc in m.get_nuclides():
            files.append(by_name[nuc])
        for sab in m._sab:                     # (table name, fraction); OpenMC has no public accessor in 0.15
            files.append(by_name[sab[0]])
    return files


def openmc_versions() -> dict[str, str]:
    import numpy
    import openmc
    return {"openmc": openmc.__version__, "numpy": numpy.__version__, "cache": "1"}


def openmc_verify(batches: int) -> Callable[[Path], bool]:
    """A verifier: the final statepoint exists and reports every batch."""
    def verify(case_dir: Path) -> bool:
        import openmc
        sp = case_dir / f"statepoint.{batches}.h5"
        if not sp.exists():
            return False
        with openmc.StatePoint(sp) as p:
            return p.current_batch == batches
    return verify


def openmc_run(model) -> Callable[[Path], None]:
    def run(case_dir: Path) -> None:
        model.run(cwd=case_dir, output=False)
    return run


def run_openmc_case(model, root: Path = CACHE_ROOT) -> tuple[str, Path]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        inputs = openmc_inputs(model, Path(tmp))
    return run_case(inputs, data_digest(openmc_data_files(model), root), openmc_versions(), openmc_run(model),
                    openmc_verify(model.settings.batches), root)
