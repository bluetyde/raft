"""
Fetch, parse, and catalog the JSI TRIGA Mark II pulse database.

Source: Jožef Stefan Institute (JSI), Ljubljana, Slovenia
Website: https://trigapulse.ijs.si/
Authors: Ingrid Švajger, Luka Snoj (Reactor Physics Department)
Contact: ingrid.svajger@ijs.si

This script parses the pulse experiment table from trigapulse.ijs.si,
extracts all ~757 recorded reactor pulses (1991–2023), formats the metadata
into structured CSV and JSON datasets, and provides utilities to download
raw or processed pulse time-series traces for model validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_URL = "https://trigapulse.ijs.si/"


def clean_text(s: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    s = re.sub(r"<.*?>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&Zcaron;", "Z").replace("&zcaron;", "z")
    s = s.replace("&#961;", "rho")
    return " ".join(s.split()).strip()


def extract_href(cell_html: str) -> Optional[str]:
    """Extract href target from HTML, supporting non-standard formatting (e.g. a = href = ...)."""
    m = re.search(r"href\s*=\s*[\"']?([^\s\"'<>]+)", cell_html, re.IGNORECASE)
    return m.group(1) if m else None


def parse_float(val: Optional[str]) -> Optional[float]:
    """Parse string to float, returning None for missing or sentinel values."""
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("n.a.", "test", "-", "", "none", "null", "*"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(val: Optional[str]) -> Optional[int]:
    """Parse string to int, returning None for missing or invalid values."""
    if not val:
        return None
    cleaned = val.strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_html_table(html_content: str) -> List[Dict[str, Any]]:
    """Parse the raw HTML table into a list of structured pulse dictionaries."""
    raw_rows = html_content.split("<tr")[1:]
    pulses: List[Dict[str, Any]] = []

    # Skip index 0 (sub-headers row)
    for row in raw_rows[1:]:
        cells = re.findall(r"<td.*?>(.*?)(?=</td|<td|$)", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 11:
            continue

        pulse_id = parse_int(clean_text(cells[0]))
        if pulse_id is None:
            continue

        date_str = clean_text(cells[1])
        rho_dollars = parse_float(clean_text(cells[2]))
        rod_pos = parse_float(clean_text(cells[3]))
        pmax_mw = parse_float(clean_text(cells[4]))
        e_1000pts_mws = parse_float(clean_text(cells[5]))
        e_1pct_mws = parse_float(clean_text(cells[6]))
        e_tangent_mws = parse_float(clean_text(cells[7]))
        fwhm_s = parse_float(clean_text(cells[8]))
        t1_max_c = parse_float(clean_text(cells[9]))
        t2_max_c = parse_float(clean_text(cells[10]))

        raw_data_file = extract_href(cells[11]) if len(cells) > 11 else None
        processed_data_file = extract_href(cells[12]) if len(cells) > 12 else None
        power_chart_pdf = extract_href(cells[13]) if len(cells) > 13 else None
        temp_chart_pdf = extract_href(cells[14]) if len(cells) > 14 else None
        rod_table_pdf = extract_href(cells[15]) if len(cells) > 15 else None
        core_config = clean_text(cells[16]) if len(cells) > 16 else None
        core_config_pdf = extract_href(cells[16]) if len(cells) > 16 else None

        # Convert dollars to pcm (1 $ = 700 pcm as stated on trigapulse.ijs.si)
        rho_pcm = round(rho_dollars * 700.0, 3) if rho_dollars is not None else None

        record = {
            "pulse_id": pulse_id,
            "date": date_str,
            "rho_dollars": rho_dollars,
            "rho_pcm": rho_pcm,
            "rod_position": rod_pos,
            "peak_power_mw": pmax_mw,
            "energy_1000pts_mws": e_1000pts_mws,
            "energy_1pct_mws": e_1pct_mws,
            "energy_tangent_mws": e_tangent_mws,
            "fwhm_s": fwhm_s,
            "t1_max_c": t1_max_c,
            "t2_max_c": t2_max_c,
            "raw_data_file": raw_data_file,
            "processed_data_file": processed_data_file,
            "power_chart_pdf": power_chart_pdf,
            "temp_chart_pdf": temp_chart_pdf,
            "rod_table_pdf": rod_table_pdf,
            "core_config": core_config,
            "core_config_pdf": core_config_pdf,
        }
        pulses.append(record)

    return pulses


def export_csv(pulses: List[Dict[str, Any]], out_path: Path) -> None:
    """Export pulses to CSV with standard LF line endings."""
    if not pulses:
        return
    fieldnames = list(pulses[0].keys())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for p in pulses:
            writer.writerow(p)


def export_json(pulses: List[Dict[str, Any]], out_path: Path) -> None:
    """Export pulses to structured JSON with metadata."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": "JSI TRIGA Mark II Pulse Database",
        "source": "https://trigapulse.ijs.si/",
        "institution": "Jožef Stefan Institute, Reactor Physics Department, Ljubljana, Slovenia",
        "contacts": ["Ingrid Švajger (ingrid.svajger@ijs.si)", "Luka Snoj"],
        "citations": [
            "I. Švajger, L. Snoj, 'Evaluation of reactor pulse experiments', Nuclear Engineering and Technology, 55 (2023) 4404–4415",
            "I. Švajger, 'Analysis of the physical parameters of the reactor pulse', Master's Thesis, University of Ljubljana (2019)"
        ],
        "units": {
            "rho_dollars": "$ (reactivity normalized to beta_eff)",
            "rho_pcm": "pcm (1 $ = 700 pcm, beta_eff = 0.0070)",
            "peak_power_mw": "MW (peak thermal power)",
            "energy_mws": "MW·s (total energy released)",
            "fwhm_s": "s (full width at half maximum duration)",
            "temperature_c": "°C (thermocouple measurement in instrumented fuel elements T1 and T2)"
        },
        "count": len(pulses),
        "pulses": pulses,
    }
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def download_file(rel_url: str, dest_path: Path, timeout: float = 20.0) -> bool:
    """Download a file from trigapulse.ijs.si if not already present."""
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    full_url = BASE_URL + rel_url.lstrip("/")
    req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0 (VirtualReactor Benchmark Suite)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as out:
            out.write(resp.read())
        return True
    except Exception as err:
        print(f"Failed to download {full_url}: {err}", file=sys.stderr)
        if dest_path.exists():
            dest_path.unlink()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and parse JSI TRIGA pulse database.")
    parser.add_argument("--html-file", type=Path, help="Path to local cached HTML file (default: download from web)")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent, help="Output directory for data files")
    parser.add_argument("--download-traces", nargs="*", type=int, help="Optional list of pulse IDs to download trace files for")
    args = parser.parse_args()

    if args.html_file and args.html_file.exists():
        print(f"Reading HTML from {args.html_file}...")
        with open(args.html_file, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
    else:
        print(f"Fetching HTML from {BASE_URL}...")
        req = urllib.request.Request(BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

    pulses = parse_html_table(html)
    print(f"Parsed {len(pulses)} pulse experiments.")

    csv_path = args.out_dir / "pulses_summary.csv"
    json_path = args.out_dir / "pulses_summary.json"
    export_csv(pulses, csv_path)
    export_json(pulses, json_path)
    print(f"Wrote summary CSV to {csv_path}")
    print(f"Wrote summary JSON to {json_path}")

    if args.download_traces:
        traces_dir = args.out_dir / "traces"
        pulse_map = {p["pulse_id"]: p for p in pulses}
        for pid in args.download_traces:
            rec = pulse_map.get(pid)
            if not rec:
                print(f"Warning: Pulse ID {pid} not found in catalog.")
                continue
            proc_file = rec.get("processed_data_file")
            if proc_file:
                dest = traces_dir / proc_file
                print(f"Downloading processed trace for pulse {pid} ({proc_file})...")
                download_file(proc_file, dest)
            raw_file = rec.get("raw_data_file")
            if raw_file:
                dest = traces_dir / raw_file
                print(f"Downloading raw data for pulse {pid} ({raw_file})...")
                download_file(raw_file, dest)


if __name__ == "__main__":
    main()
