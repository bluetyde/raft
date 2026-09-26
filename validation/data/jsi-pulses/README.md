# JSI TRIGA Mark II Pulse Experiment Database

This directory contains the experimental pulse dataset from the **Jožef Stefan Institute (JSI) TRIGA Mark II research reactor** in Ljubljana, Slovenia.

- **Primary Source**: [https://trigapulse.ijs.si/](https://trigapulse.ijs.si/)
- **Authors**: Ingrid Švajger and Luka Snoj (Reactor Physics Department, Jožef Stefan Institute)
- **Contact for Data Redistribution & Licensing**: `ingrid.svajger@ijs.si`

---

## Citations

When using this dataset for model validation, please cite the original publications:

1. **Journal Article**:
   > I. Švajger, L. Snoj, *"Evaluation of reactor pulse experiments"*, **Nuclear Engineering and Technology**, Vol. 55, Issue 12, pp. 4404–4415 (2023).  
   > DOI: [10.1016/j.net.2023.08.016](https://doi.org/10.1016/j.net.2023.08.016)

2. **Master's Thesis**:
   > I. Švajger, *"Analysis of the physical parameters of the reactor pulse"*, Master's Thesis, University of Ljubljana, Faculty of Mathematics and Physics (2019).  
   > URL: [https://repozitorij.uni-lj.si/IzpisGradiva.php?id=109204](https://repozitorij.uni-lj.si/IzpisGradiva.php?id=109204)

3. **Facility & Reaction Rate Experiments**:
   > Ž. Štancar, L. Snoj, L. Barbot, *"Reaction Rate Distribution Experiments at the Slovenian JSI TRIGA Mark II Research Reactor"*, EPJ Web of Conferences 225, 04018 (2020).

---

## Dataset Overview

The database records **757 pulse experiments** conducted between **November 4, 1991 and December 21, 2023** spanning 31 core configurations (Core 135 through Core 253).

A pulse experiment is initiated by pneumatic ejection of the transient control rod with the safety and compensating/shim rods withdrawn. Rapid positive reactivity insertion ($1.05\text{–}4.60\$$) drives the reactor prompt critical. The pulse is self-terminated by the prompt negative fuel temperature coefficient of the $\text{U-ZrH}_{1.6}$ fuel before the control rod trip completes insertion.

### Files Included

| File | Description |
|---|---|
| [`pulses_summary.csv`](pulses_summary.csv) | Full tabular dataset of all 757 pulses in CSV format. |
| [`pulses_summary.json`](pulses_summary.json) | Full dataset in JSON format including schema, metadata, units, and citation information. |
| [`fetch_jsi_pulses.py`](fetch_jsi_pulses.py) | Python utility to scrape, verify, and download traces from `https://trigapulse.ijs.si/`. |
| `traces/` | Optional local directory for high-frequency time-series files (git-ignored due to file size). |

---

## Data Fields and Conventions

All physical quantities in `pulses_summary.csv` and `pulses_summary.json` use the following definitions:

| Field Name | Type | Unit | Description |
|---|---|---|---|
| `pulse_id` | `int` | — | Sequence number of the pulse experiment ($1\dots 760$). |
| `date` | `string` | DD.MM.YYYY | Date on which the experiment was performed. |
| `rho_dollars` | `float` | $\$$ | Inserted reactivity in dollars ($\Delta k / (\beta_{\text{eff}} k)$). |
| `rho_pcm` | `float` | $\text{pcm}$ | Inserted reactivity in pcm, using the benchmark conversion $1\$ = 700\text{ pcm}$ ($\beta_{\text{eff}} = 0.0070$). |
| `rod_position` | `float` | steps | Transient rod withdrawal position (drive encoder units). |
| `peak_power_mw` | `float` | $\text{MW}$ | Peak thermal power ($P_{\text{max}}$) achieved during the pulse. |
| `energy_1000pts_mws` | `float` | $\text{MW}\cdot\text{s}$ | Released energy integrated over $\pm 1000$ points around the peak. |
| `energy_1pct_mws` | `float` | $\text{MW}\cdot\text{s}$ | Released energy integrated between $1\%$ power thresholds. |
| `energy_tangent_mws`| `float` | $\text{MW}\cdot\text{s}$ | Released energy integrated between tangents at $1/10$ of peak power. |
| `fwhm_s` | `float` | $\text{s}$ | Full width at half maximum of the power pulse. |
| `t1_max_c` | `float` | $^\circ\text{C}$ | Maximum fuel temperature recorded by instrumented fuel element sensor 1. |
| `t2_max_c` | `float` | $^\circ\text{C}$ | Maximum fuel temperature recorded by instrumented fuel element sensor 2. |
| `raw_data_file` | `string` | — | Relative filename of raw digital acquisition data (`.bin` or `.ASC`). |
| `processed_data_file` | `string` | — | Relative filename of calibrated high-rate time series (`RawDataProcessed*.txt`). |
| `power_chart_pdf` | `string` | — | Facility power plot document (`*moc.pdf`). |
| `temp_chart_pdf` | `string` | — | Facility fuel temperature plot document (`*tem.pdf`). |
| `rod_table_pdf` | `string` | — | Control rod worth calibration table document (`s*.pdf`). |
| `core_config` | `string` | — | Core loading designation (e.g. `135`, `253`). |
| `core_config_pdf` | `string` | — | Diagram of fuel and control element positions for the core loading. |

---

## Physical Validation Reference

According to the Nordheim–Fuchs adiabatic pulse model:

1. **Peak Power Scaling**:
   $$P_{\text{max}} \approx \frac{(\rho_0 - \beta)^2}{2 \alpha_f \Lambda} \cdot C_{\text{core}}$$
   For inserted reactivity $\rho_0 > \beta$, peak power is proportional to $(\rho_{\$} - 1)^2$.

2. **Total Released Energy**:
   $$E_{\text{total}} \approx \frac{2 (\rho_0 - \beta)}{\alpha_f}$$
   Energy release scales linearly with prompt inserted reactivity $(\rho_{\$} - 1)$.

3. **Pulse Width (FWHM)**:
   $$\text{FWHM} \approx \frac{3.52 \Lambda}{\rho_0 - \beta}$$
   Pulse duration varies inversely with prompt reactivity $(\rho_{\$} - 1)$.

These relationships form Level 5 of the validation hierarchy in [`docs/plans/07-validation.md`](../../docs/plans/07-validation.md).
