"""Download JSI pulse traces for chosen cores and keep only a window around each pulse.

The processed traces on trigapulse.ijs.si are 400,000 rows of text (~17 MB each): columns power [MW], T1 [°C], T2 [°C]
and an unused constant, sampled every 50 µs (20 s records). The interval isn't documented; it was determined on pulse 521:
the peak sits at sample 6252 (chart: t ≈ 0.31 s), and summing ±1000 samples around the peak reproduces the database's
E1000 = 6.2 MWs only with dt = 4.997e-5 s.

Each trace is reduced to [peak - 0.5 s, peak + 1.5 s] (40,000 samples) of power, T1 and T2 as little-endian float32,
written to validation/data/jsi-pulses/traces/<pulse_id>.f32 (gitignored), with an index JSON. The full text file is
deleted after reduction.

Usage (from the repo root):  python -m validation.fetch_trace_windows --cores 242 246 [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY = REPO_ROOT / "validation" / "data" / "jsi-pulses" / "pulses_summary.json"
OUT_DIR = REPO_ROOT / "validation" / "data" / "jsi-pulses" / "traces"
BASE_URL = "https://trigapulse.ijs.si/"
DT = 50e-6
PRE, POST = 10_000, 30_000   # samples: 0.5 s before, 1.5 s after the peak


def _fetch_text(name: str, timeout: float = 120.0) -> str:
    req = urllib.request.Request(BASE_URL + name, headers={"User-Agent": "virtual-reactor validation (research)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("ascii")


def reduce_trace(text: str) -> tuple[int, int, list[tuple[float, float, float]]]:
    """Return (peak index in the full record, window start index, window rows (P, T1, T2))."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
    if not rows:
        raise ValueError("empty trace")
    peak = 0
    for k in range(1, len(rows)):
        if rows[k][0] > rows[peak][0]:
            peak = k
    start = max(0, peak - PRE)
    return peak, start, rows[start:min(len(rows), peak + POST)]


def process(pulse: dict) -> dict:
    pid = pulse["pulse_id"]
    out = OUT_DIR / f"{pid}.f32"
    meta = OUT_DIR / f"{pid}.json"
    if out.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    try:
        text = _fetch_text(pulse["processed_data_file"])
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as e:
        return {"pulse_id": pid, "error": f"download failed: {e}"}
    try:
        peak, start, window = reduce_trace(text)
    except ValueError as e:
        return {"pulse_id": pid, "error": f"parse failed: {e}"}
    buf = bytearray()
    for p, t1, t2 in window:
        buf += struct.pack("<3f", p, t1, t2)
    out.write_bytes(bytes(buf))
    info = {"pulse_id": pid, "core": pulse["core_config"], "file": out.name, "dt": DT, "channels": ["P_MW", "T1_C", "T2_C"],
            "samples": len(window), "fullRecordSamples": len(text.splitlines()), "peakIndexFull": peak, "windowStart": start,
            "source": BASE_URL + pulse["processed_data_file"]}
    meta.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8", newline="\n")
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cores", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    pulses = [p for p in json.loads(SUMMARY.read_text(encoding="utf-8"))["pulses"]
              if str(p.get("core_config")) in args.cores and p.get("processed_data_file")]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = errors = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for info in ex.map(process, pulses):
            if "error" in info:
                errors += 1
                print(f"pulse {info['pulse_id']}: {info['error']}", file=sys.stderr)
            else:
                done += 1
            if (done + errors) % 20 == 0:
                print(f"{done + errors}/{len(pulses)} ({errors} errors)", flush=True)
    print(f"done: {done} windows, {errors} errors, in {OUT_DIR}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
