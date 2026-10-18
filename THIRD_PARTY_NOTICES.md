# Third-party notices

The project is MIT-licensed (see `LICENSE`). Code reused from other projects is listed here with its license and notice.
Only permissively licensed code (MIT, BSD, Apache-2.0) may be reused; see `docs/plans/09-open-release.md`.

## Bundled into the web build

- **three.js** 0.186.1 (npm `three`), MIT License, "Copyright © 2010-2026 three.js authors". Used by `web/src/views/explorer/`;
  its full license text ships in `node_modules/three/LICENSE` and must accompany any distributed build.

Development-only dependencies (types, test runners, build tools) are not distributed and are listed in `web/package.json`.

## Data

- `web/src/views/explorer/styles.ts`: nine colour stops sampled from matplotlib's **viridis** colormap (Nathaniel J. Smith,
  Stéfan van der Walt and Eric Firing), released under the CC0 1.0 public-domain dedication. No attribution is required; it is
  given here for provenance.
- `schema/vectors/synthetic-core`: invented values, except the six delayed-neutron group abundances and decay constants,
  which are the standard U-235 thermal-fission group data found in reactor physics textbooks.

## Data transcribed from publications and reports (distributed in this repository)

Measured or computed values are facts, but a compilation can carry its own terms. Each entry below says what is in the repository, where it came from and what is known about its terms. Where the terms are not stated by the source, that is said, and nothing here is a claim that permission was given.

- **Mosteller Doppler-defect benchmark** (R. D. Mosteller, *An Expanded Benchmark Suite for Doppler-Coefficient Calculations*, Los Alamos National Laboratory report LA-UR-07-0922, Tables II to IV; cleared "Approved for public release; distribution is unlimited"): the three result columns for the 16 cases, transcribed into `validation/data/mosteller-doppler/reference.json`; the benchmark's inputs come from `mit-crpg/benchmarks` (MIT licence, notice in `pipeline/openmc/data/MOSTELLER-DOPPLER-LICENSE`) and are summarised in `pipeline/openmc/data/mosteller_doppler.json`. The report states no further licence for the tables.
- **Švajger et al. 2024** (*Nuclear Engineering and Technology* 56, 1165–1203, doi:10.1016/j.net.2023.11.021): fuel compositions (Table 1), a reactivity series (Table 2) and the fuel mass per element (Table 10), transcribed into `pipeline/openmc/data/jsi_standard_fuel.json` and `validation/data/triga-jsi/parameters.json`. The journal publishes it as open access; the licence terms were not checked against the article's own licence statement when the data were transcribed, and should be before release.
- **Vavtar and Snoj 2021** (EPJ Web of Conferences 247, 08006, CC BY 4.0): eight points of the prompt fuel temperature coefficient read by eye from its Fig. 1, and the heat-capacity formula (eq. 1.8), in `validation/data/triga-jsi/parameters.json`. CC BY 4.0 allows this with attribution, given here; the points are digitised and approximate, not the authors' data.
- **TRIGA core descriptions** (the Ravnik reactor description and a Kansas State University safety analysis report, named in `pipeline/openmc/data/jsi_core_geometry.json`): grouped dimensions and component descriptions. Dimensions are facts; the sources state no reuse terms.
- **Core loading maps** (`pipeline/openmc/data/jsi_core_occupancy.json`): which fuel element sits in which grid position, for cores 242 and 246 (extracted from the core maps of the JSI pulse database, trigapulse.ijs.si, by `pipeline/openmc/core_maps.py`) and for cores 133 and 134 (read by eye from Figures 3 and 4 of Mele, Ravnik and Trkov, *Nuclear Technology* 105 (1994) 37-51). **These are derived from sources whose redistribution permission is not confirmed**, in contrast to the larger data sets listed below, which are not distributed. They are kept because the libraries cannot be rebuilt without them. If the authors object, they will be removed and the libraries marked as not reproducible from this repository.

## Installed separately (not distributed here)

- **OpenMC** 0.15 (MIT License) and an **ENDF/B-VIII.0** HDF5 cross-section library (evaluated nuclear data of the US National Nuclear Data Center), used by `pipeline/` to build libraries. Neither is included; the libraries in `libraries/` are their results.
- **Mica-v0.1-4B** (Hugging Face `sky7350/Mica-v0.1-4B`, a fine-tune of Qwen3.5-4B; Apache-2.0 according to its model card, with LICENSE and NOTICE files in its repository) and its llama.cpp runtime, used by the optional local server in `jev-server/`. About 4.7 GB; not included. Read the licence and NOTICE files that come with it, and those of the runtime libraries it ships (including NVIDIA CUDA runtime DLLs), before redistributing any of it.
- The Python packages of `jev-server/requirements.txt` (FastAPI, uvicorn, websockets, PyTorch, transformers, accelerate, sentencepiece) are installed with pip and keep their own licences.

## Measured data and benchmark values

Three measured data sets are **not distributed with this repository** (they are in `.gitignore`; permission to redistribute them has not been confirmed and is not expected soon). The validation code and tests that read them skip when the folders are absent; the results in `docs/validation/` were produced from them and quote the numbers they used. Facts such as measured values are quoted for comparison; documents are not reproduced.

- **BEAVRS** (Benchmark for Evaluation And Validation of Reactor Simulations, MIT Computational Reactor Physics Group, `mit-crpg/BEAVRS`, MIT License): the cycle 1 hot zero power values quoted in `docs/validation/m8-beavrs-hzp-*.md` and the model generator used to run the transport cases. The generator is not copied into this repository; when a data file derived from it is added, its MIT notice goes beside it.
- **JSI TRIGA pulse database** (trigapulse.ijs.si; I. Švajger and L. Snoj): kept locally in `validation/data/jsi-pulses/`, **not in the repository**. The dataset's own README names the authors as the contact for redistribution and licensing; permission has not been requested or confirmed.
- **JSI steady-state power ascension** (IAEA research reactor database, Slovenia protocols, "typical real data" of 2013): kept locally in `validation/data/jsi-steady-power/`, **not in the repository**. The source carries no licence statement.
- **TRIGA Mark II core 134 benchmark** (I. Mele, M. Ravnik, A. Trkov, *Nuclear Technology* 105 (1994) 37-51): tables transcribed into `validation/data/jsi-core134/`, kept locally, **not in the repository**; the paper itself is not here either.

