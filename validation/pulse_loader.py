"""
Pulse database loading and querying utilities for Virtual Reactor validation.

Provides a clean Python API for accessing, filtering, and analyzing experimental
pulse data from the JSI TRIGA Mark II research reactor database.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_CSV_PATH = Path(__file__).parent / "data" / "jsi-pulses" / "pulses_summary.csv"
DEFAULT_JSON_PATH = Path(__file__).parent / "data" / "jsi-pulses" / "pulses_summary.json"


@dataclass
class PulseRecord:
    pulse_id: int
    date: str
    rho_dollars: Optional[float]
    rho_pcm: Optional[float]
    rod_position: Optional[float]
    peak_power_mw: Optional[float]
    energy_1000pts_mws: Optional[float]
    energy_1pct_mws: Optional[float]
    energy_tangent_mws: Optional[float]
    fwhm_s: Optional[float]
    t1_max_c: Optional[float]
    t2_max_c: Optional[float]
    raw_data_file: Optional[str]
    processed_data_file: Optional[str]
    power_chart_pdf: Optional[str]
    temp_chart_pdf: Optional[str]
    rod_table_pdf: Optional[str]
    core_config: Optional[str]
    core_config_pdf: Optional[str]

    @property
    def is_prompt_critical(self) -> bool:
        """Return True if inserted reactivity exceeds 1 dollar (prompt critical)."""
        return self.rho_dollars is not None and self.rho_dollars > 1.0

    @property
    def prompt_reactivity_dollars(self) -> Optional[float]:
        """Return excess reactivity above prompt critical: rho - 1.0 ($)."""
        if self.rho_dollars is None:
            return None
        return self.rho_dollars - 1.0


def _parse_row(row: Dict[str, str]) -> PulseRecord:
    def _float_or_none(val: Optional[str]) -> Optional[float]:
        if not val or val.strip().lower() in ("", "none", "null"):
            return None
        try:
            return float(val)
        except ValueError:
            return None

    def _str_or_none(val: Optional[str]) -> Optional[str]:
        if not val or val.strip().lower() in ("", "none", "null"):
            return None
        return val.strip()

    return PulseRecord(
        pulse_id=int(row["pulse_id"]),
        date=row["date"].strip(),
        rho_dollars=_float_or_none(row.get("rho_dollars")),
        rho_pcm=_float_or_none(row.get("rho_pcm")),
        rod_position=_float_or_none(row.get("rod_position")),
        peak_power_mw=_float_or_none(row.get("peak_power_mw")),
        energy_1000pts_mws=_float_or_none(row.get("energy_1000pts_mws")),
        energy_1pct_mws=_float_or_none(row.get("energy_1pct_mws")),
        energy_tangent_mws=_float_or_none(row.get("energy_tangent_mws")),
        fwhm_s=_float_or_none(row.get("fwhm_s")),
        t1_max_c=_float_or_none(row.get("t1_max_c")),
        t2_max_c=_float_or_none(row.get("t2_max_c")),
        raw_data_file=_str_or_none(row.get("raw_data_file")),
        processed_data_file=_str_or_none(row.get("processed_data_file")),
        power_chart_pdf=_str_or_none(row.get("power_chart_pdf")),
        temp_chart_pdf=_str_or_none(row.get("temp_chart_pdf")),
        rod_table_pdf=_str_or_none(row.get("rod_table_pdf")),
        core_config=_str_or_none(row.get("core_config")),
        core_config_pdf=_str_or_none(row.get("core_config_pdf")),
    )


def load_pulse_summary(data_path: Optional[Path] = None) -> List[PulseRecord]:
    """
    Load all pulses from the CSV summary dataset.

    Args:
        data_path: Optional custom path to pulses_summary.csv. Defaults to package location.

    Returns:
        List of PulseRecord objects.
    """
    path = data_path or DEFAULT_CSV_PATH
    if not path.exists():
        raise FileNotFoundError(f"Pulse database not found at {path}")

    records: List[PulseRecord] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(_parse_row(row))
    return records


def filter_pulses(
    pulses: List[PulseRecord],
    *,
    core: Optional[str] = None,
    min_rho: Optional[float] = None,
    max_rho: Optional[float] = None,
    require_valid_pmax: bool = False,
    require_temperature: bool = False,
) -> List[PulseRecord]:
    """
    Filter pulse records by experimental criteria.

    Args:
        pulses: Input list of pulse records.
        core: Desired core configuration designation (e.g. '253').
        min_rho: Minimum inserted reactivity in dollars.
        max_rho: Maximum inserted reactivity in dollars.
        require_valid_pmax: If True, exclude pulses with missing or non-positive Pmax.
        require_temperature: If True, exclude pulses missing T1 or T2 temperature data.

    Returns:
        Filtered list of PulseRecord objects.
    """
    out: List[PulseRecord] = []
    for p in pulses:
        if core is not None and p.core_config != core:
            continue
        if min_rho is not None:
            if p.rho_dollars is None or p.rho_dollars < min_rho:
                continue
        if max_rho is not None:
            if p.rho_dollars is None or p.rho_dollars > max_rho:
                continue
        if require_valid_pmax:
            if p.peak_power_mw is None or p.peak_power_mw <= 0:
                continue
        if require_temperature:
            if p.t1_max_c is None and p.t2_max_c is None:
                continue
        out.append(p)
    return out


def extract_nordheim_fuchs_dataset(
    pulses: List[PulseRecord],
    min_prompt_dollars: float = 0.05,
) -> Dict[str, List[float]]:
    """
    Extract parallel arrays for Nordheim-Fuchs pulse comparison.

    Only prompt-critical pulses (rho - 1 >= min_prompt_dollars) with valid
    peak power and energy are included.

    Returns dictionary with keys:
        'pulse_id', 'rho_dollars', 'rho_prompt_dollars', 'peak_power_mw',
        'energy_mws', 'fwhm_s', 't1_max_c'
    """
    res: Dict[str, List[float]] = {
        "pulse_id": [],
        "rho_dollars": [],
        "rho_prompt_dollars": [],
        "peak_power_mw": [],
        "energy_mws": [],
        "fwhm_s": [],
        "t1_max_c": [],
    }

    for p in pulses:
        if p.rho_dollars is None or p.peak_power_mw is None:
            continue
        rho_p = p.rho_dollars - 1.0
        if rho_p < min_prompt_dollars or p.peak_power_mw <= 0:
            continue

        # Prefer 1000pts energy, fallback to 1% or tangent
        energy = p.energy_1000pts_mws or p.energy_1pct_mws or p.energy_tangent_mws
        if energy is None or energy <= 0:
            continue

        res["pulse_id"].append(float(p.pulse_id))
        res["rho_dollars"].append(p.rho_dollars)
        res["rho_prompt_dollars"].append(rho_p)
        res["peak_power_mw"].append(p.peak_power_mw)
        res["energy_mws"].append(energy)
        res["fwhm_s"].append(p.fwhm_s if p.fwhm_s is not None else 0.0)
        res["t1_max_c"].append(p.t1_max_c if p.t1_max_c is not None else 0.0)

    return res


def load_processed_trace(trace_file_path: Path) -> Dict[str, List[float]]:
    """
    Parse a high-frequency processed pulse time-series text file (RawDataProcessed*.txt).

    Returns:
        Dictionary with 'power_mw', 't1_c', 't2_c'.
    """
    if not trace_file_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_file_path}")

    power: List[float] = []
    t1: List[float] = []
    t2: List[float] = []

    with open(trace_file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Source") or line.startswith("---"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    power.append(float(parts[0]))
                    t1.append(float(parts[1]))
                    t2.append(float(parts[2]))
                except ValueError:
                    continue

    return {"power_mw": power, "t1_c": t1, "t2_c": t2}
