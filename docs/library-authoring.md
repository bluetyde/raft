# Writing a library

A library is a folder with `manifest.json` and, for shapes and large tables, binary arrays. [library-format.md](library-format.md) is the normative description; this page is the order to work in.

## 1. Start from a working one

Copy `schema/vectors/synthetic-core/` (a small test core) or a shipped library and change it. The synthetic core is a good base for a first attempt because everything in it is declared.

## 2. Decide the capabilities

`capabilities` lists what the library claims to model (for example `point-kinetics/lumped-thermal-v2`, `point-kinetics/boron-v1`, `point-kinetics/rod-interaction-v2`). Each capability requires its fields; the validator names what is missing. Claim only what you have values for.

## 3. Fill in the values and say where each came from

Every numeric field carries a `source`: `measured`, `computed`, `cited` or `assumed`, with a reference or a note and an uncertainty where there is one. Mark a guess as `assumed`. The app shows assumed values and the supported envelope in its warnings; hiding a guess as a measurement is the one thing the format is built to prevent.

## 4. Say where the library has been checked

`domain` lists the ranges and the jointly checked states. The app shows `unvalidated` outside them. Leave `jointChecked` empty if you have not compared the combination.

## 5. Validate

```bash
python -m pipeline.library.validate path/to/library
```

The validator returns coded issues (`E_...`) with the path of the field. The browser loader runs the same checks (`web/src/library/validate.ts`) and refuses a library that fails.

## 6. Try it

Add the folder to `web/src/app/catalog.ts` to list it in the app, or serve it as a URL source. Run a short session and watch the validity banner.

## 7. Compare with something

Write what you will compare and what counts as agreement before you run it ([CONTRIBUTING.md](../CONTRIBUTING.md), rule 2). The status stays `experimental` until that has been done and reviewed, and even then the supported envelope, not the status, is what to read.

For libraries built from OpenMC runs, `pipeline/library/export_openmc.py` and `export_beavrs.py` are the worked examples; `docs/m8-beavrs-exporter-plan.md` explains the reasoning.
