"""
Deterministic screening for the JSI TRIGA Mark II experimental pulse database.

Normalizes missing values, flags physically inconsistent and outlying pulses
with explicit reasons, and summarizes each core configuration.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from validation.pulse_loader import DEFAULT_CSV_PATH, PulseRecord, load_pulse_summary

SCREEN_VERSION: int = 1

# Below prompt critical, a step from low power can't produce a prompt burst of more than a few MW.
# The 10 MW threshold is a deliberately generous screening assumption.
SUBPROMPT_MAX_MW: float = 10.0

Z_LIMIT: float = 3.5
MAD_FALLBACK: float = 0.3
MIN_GROUP_SIZE: int = 3

DEFAULT_REPORT_PATH = Path(__file__).parent / "data" / "jsi-pulses" / "screening_report.json"


@dataclass
class ScreenResult:
    kept: List[PulseRecord]
    excluded: List[Tuple[int, List[str]]]
    normalized: Dict[str, int]
    reason_counts: Dict[str, int]
    cores: List[Dict[str, Any]]


def normalize_records(records: List[PulseRecord]) -> Tuple[List[PulseRecord], Dict[str, int]]:
    """
    Return cleaned copies of records with missing-value normalization and normalization counts.

    - fwhm_s == 0.0 -> None
    - energy fields equal to 0.0 -> None
    Never mutates the input objects.
    """
    normalized_counts = {
        "energy_1000pts_mws": 0,
        "energy_1pct_mws": 0,
        "energy_tangent_mws": 0,
        "fwhm_s": 0,
    }
    cleaned: List[PulseRecord] = []
    for r in records:
        changes: Dict[str, Any] = {}
        if r.fwhm_s == 0.0:
            changes["fwhm_s"] = None
            normalized_counts["fwhm_s"] += 1
        if r.energy_1000pts_mws == 0.0:
            changes["energy_1000pts_mws"] = None
            normalized_counts["energy_1000pts_mws"] += 1
        if r.energy_1pct_mws == 0.0:
            changes["energy_1pct_mws"] = None
            normalized_counts["energy_1pct_mws"] += 1
        if r.energy_tangent_mws == 0.0:
            changes["energy_tangent_mws"] = None
            normalized_counts["energy_tangent_mws"] += 1

        if changes:
            cleaned.append(dataclasses.replace(r, **changes))
        else:
            cleaned.append(dataclasses.replace(r))
    return cleaned, normalized_counts


def _core_sort_key(c: Optional[str]) -> Tuple[int, Any]:
    if c is None:
        return (2, "")
    try:
        return (0, int(c))
    except ValueError:
        try:
            return (0, float(c))
        except ValueError:
            return (1, str(c))


def _compute_core_summaries(
    all_records: List[PulseRecord], kept_records: List[PulseRecord]
) -> List[Dict[str, Any]]:
    """
    Summarize each core configuration.

    Sorted numerically when numeric, else as text.
    """
    core_all: Dict[str, List[PulseRecord]] = {}
    for p in all_records:
        if p.core_config is not None:
            core_all.setdefault(p.core_config, []).append(p)

    core_kept: Dict[str, List[PulseRecord]] = {}
    for p in kept_records:
        if p.core_config is not None:
            core_kept.setdefault(p.core_config, []).append(p)

    sorted_cores = sorted(core_all.keys(), key=_core_sort_key)
    summaries: List[Dict[str, Any]] = []

    for core in sorted_cores:
        records_in_core = core_all[core]
        kept_in_core = core_kept.get(core, [])
        excluded_count = len(records_in_core) - len(kept_in_core)

        kept_rhos = [p.rho_dollars for p in kept_in_core if p.rho_dollars is not None]
        min_rho = min(kept_rhos) if kept_rhos else None
        max_rho = max(kept_rhos) if kept_rhos else None

        kept_peaks = [p.peak_power_mw for p in kept_in_core if p.peak_power_mw is not None]
        min_peak = min(kept_peaks) if kept_peaks else None
        max_peak = max(kept_peaks) if kept_peaks else None

        count_fwhm = sum(1 for p in kept_in_core if p.fwhm_s is not None)
        count_t1 = sum(1 for p in kept_in_core if p.t1_max_c is not None)

        dates = [p.date for p in records_in_core if p.date]
        if dates:
            sorted_dates = sorted(
                dates,
                key=lambda d: tuple(int(x) for x in d.split(".")[::-1])
                if len(d.split(".")) == 3 and all(x.isdigit() for x in d.split("."))
                else (0, 0, 0),
            )
            first_date = sorted_dates[0]
            last_date = sorted_dates[-1]
        else:
            first_date = None
            last_date = None

        summaries.append(
            {
                "core_config": core,
                "count_fwhm": count_fwhm,
                "count_t1_max_c": count_t1,
                "excluded": excluded_count,
                "first_date": first_date,
                "kept": len(kept_in_core),
                "last_date": last_date,
                "max_peak_power_mw": max_peak,
                "max_rho_dollars": max_rho,
                "min_peak_power_mw": min_peak,
                "min_rho_dollars": min_rho,
                "total": len(records_in_core),
            }
        )

    return summaries


def screen_pulses(records: List[PulseRecord]) -> ScreenResult:
    """
    Screen pulse records deterministically.

    Normalizes missing values, evaluates exclusion criteria, and computes core summaries.
    """
    cleaned_records, normalized = normalize_records(records)

    pulse_reasons: Dict[int, List[str]] = {p.pulse_id: [] for p in cleaned_records}

    # Reason 1: missing_reactivity
    for p in cleaned_records:
        if p.rho_dollars is None:
            pulse_reasons[p.pulse_id].append("missing_reactivity")

    # Reason 2: missing_peak_power
    for p in cleaned_records:
        if p.peak_power_mw is None or p.peak_power_mw <= 0:
            pulse_reasons[p.pulse_id].append("missing_peak_power")

    # Reason 3: subprompt_high_power
    for p in cleaned_records:
        if (
            p.rho_dollars is not None
            and p.rho_dollars < 1.0
            and p.peak_power_mw is not None
            and p.peak_power_mw > SUBPROMPT_MAX_MW
        ):
            pulse_reasons[p.pulse_id].append("subprompt_high_power")

    # Reason 4: group_outlier
    # Group by core_config and rho_dollars rounded to 2 decimals
    groups: Dict[Tuple[str, float], List[PulseRecord]] = {}
    for p in cleaned_records:
        if (
            p.core_config is not None
            and p.rho_dollars is not None
            and p.peak_power_mw is not None
            and p.peak_power_mw > 0
        ):
            key = (p.core_config, round(p.rho_dollars, 2))
            groups.setdefault(key, []).append(p)

    for (core, rounded_rho), members in groups.items():
        if len(members) < MIN_GROUP_SIZE:
            continue
        x = [math.log10(p.peak_power_mw) for p in members]
        m = statistics.median(x)
        mad = statistics.median([abs(val - m) for val in x])
        for p, val in zip(members, x):
            if mad > 0:
                score = 0.6745 * abs(val - m) / mad
                if score > Z_LIMIT:
                    pulse_reasons[p.pulse_id].append("group_outlier")
            else:
                diff = abs(val - m)
                if diff > MAD_FALLBACK:
                    pulse_reasons[p.pulse_id].append("group_outlier")

    kept: List[PulseRecord] = []
    excluded: List[Tuple[int, List[str]]] = []
    reason_counts: Dict[str, int] = {
        "group_outlier": 0,
        "missing_peak_power": 0,
        "missing_reactivity": 0,
        "subprompt_high_power": 0,
    }

    for p in cleaned_records:
        reasons = sorted(pulse_reasons[p.pulse_id])
        if reasons:
            excluded.append((p.pulse_id, reasons))
            for r in reasons:
                reason_counts[r] = reason_counts.get(r, 0) + 1
        else:
            kept.append(p)

    excluded.sort(key=lambda x: x[0])

    cores = _compute_core_summaries(cleaned_records, kept)

    return ScreenResult(
        kept=kept,
        excluded=excluded,
        normalized=normalized,
        reason_counts=reason_counts,
        cores=cores,
    )


def write_report(result: ScreenResult, path: Path | str) -> None:
    """
    Write screening report to JSON.

    Deterministic output with indent=1, sort_keys=True, allow_nan=False, LF line endings.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report_dict = {
        "cores": result.cores,
        "excluded": [
            {"pulseId": pid, "reasons": reasons}
            for pid, reasons in sorted(result.excluded, key=lambda x: x[0])
        ],
        "normalized": result.normalized,
        "reasonCounts": result.reason_counts,
        "screenVersion": SCREEN_VERSION,
        "thresholds": {
            "mad_fallback": MAD_FALLBACK,
            "min_group_size": MIN_GROUP_SIZE,
            "subprompt_max_mw": SUBPROMPT_MAX_MW,
            "z_limit": Z_LIMIT,
        },
        "totals": {
            "excluded": len(result.excluded),
            "kept": len(result.kept),
            "total": len(result.kept) + len(result.excluded),
        },
    }
    content = json.dumps(report_dict, indent=1, sort_keys=True, allow_nan=False) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic screening step for the JSI pulse database."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Output report path (default: {DEFAULT_REPORT_PATH})",
    )
    args = parser.parse_args()

    records = load_pulse_summary()
    result = screen_pulses(records)
    write_report(result, args.out)

    total = len(result.kept) + len(result.excluded)
    print(f"Total: {total}, Kept: {len(result.kept)}, Excluded: {len(result.excluded)}")
    print("Reason counts:")
    for reason, count in sorted(result.reason_counts.items()):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
