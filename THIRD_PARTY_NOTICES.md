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
