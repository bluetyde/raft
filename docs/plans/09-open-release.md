# Plan 09: Open release

Turning the project into something others can use and contribute to.
Milestone: M9. A few items (license, repo, CI) happen much earlier.

## Early (as soon as there's code)

- **Git repo:** private GitHub repo under `bluetyde`, like the other projects. It goes public at release.
- **License: MIT (provisional, 2026-09-25).** Matches OpenMC and is the easiest for labs and companies to adopt. Confirm before the first outside contribution.
  - Consequences: **no code may be copied from copyleft (GPL/AGPL) or unlicensed projects** (JSI simulator, TH462, openpointkinetics, PyRK, the mit-crpg TRIGA notebook).
    Write our own from the equations and papers, and cite them. Code under MIT, BSD or Apache-2.0 may be reused with its notice kept (list it in `THIRD_PARTY_NOTICES.md`, as Studio does).
  - Alternatives kept on file: **Apache-2.0** (same freedom plus an explicit patent grant; matches ARMI). **GPL-3.0** would allow reusing GPL code, but every derivative would have to stay GPL.
  - A `LICENSE` file (MIT) goes in when the git repo is created.
  - The license for **library data** is separate: libraries built from published benchmarks may inherit terms from their sources. Check what the ICSBEP handbook terms allow before shipping the TRIGA library publicly.
- **CI (GitHub Actions):** Python tests (physics-ref, pipeline without OpenMC runs), schema validation, TypeScript tests, golden-vector agreement, web build.
  OpenMC runs themselves stay local; CI checks against stored results.

## Release contents

- The web app, deployable as static files (any static host, or a local double-click launcher like OpenMC Studio).
- The TRIGA library (if data terms allow), the synthetic library, and the second reactor's library.
- Docs:
  - `README`: what it is, a screenshot/GIF, quick start
  - `docs/library-format.md`: the full spec
  - Library-authoring guide: from any transport code to a valid library
  - Physics notes: equations, assumptions, limits, and when point kinetics isn't appropriate
  - Validation report for each shipped library
- The pipeline, with a TRIGA example config.

## Before going public

- A check that every number in the shipped libraries has a source or is labelled computed or assumed.
- The disclaimer (educational use; not for operator training at a real facility or safety analysis).
- No personal paths or machine names in configs (`/root/nuclear_data` becomes an env var, as it already is on your machines).
- Contributing guide, code of conduct, issue templates.

## After release

- Announce where reactor physics people gather: the OpenMC Discourse forum, the ANS student section and NE departments (including UTK).
- Invite others to contribute libraries. The library format is the main thing that makes this an open modeller rather than one person's app.
