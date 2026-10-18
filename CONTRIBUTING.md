# Contributing

RAFT is experimental and educational. Contributions are welcome where they make the model, its checks or its documentation more honest; they are not welcome where they would make a result look better than the evidence supports.

## Ground rules

1. **No claim without a check.** A library, lesson or number gets a status of `experimental` until a pre-written comparison says otherwise. Do not mark anything validated.
2. **Write the comparison before you run it.** Validation work here is done as a protocol (what will be run, what counts as agreement, what will not be tried after seeing the result), then run once, then reported with every result including the failures. See [docs/validation](docs/validation) for examples. If a later review finds a mistake, add an erratum to the results note; do not quietly change the report.
3. **Say where each number came from.** Library values are measured, computed, cited or assumed, and are labelled that way ([docs/library-format.md](docs/library-format.md) section 3).
4. **Do not add data you may not redistribute.** The measured data behind some comparisons is not in this repository on purpose ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). Do not add licensed, export-controlled or personal data. Do not describe any exported deck as run or not run in a particular proprietary code.
5. **Two engines agree.** The Python reference (`physics_ref/`) and the TypeScript engine (`web/src/sim/`) are checked against the same golden vectors. A change to one needs the matching change to the other and the vectors regenerated.

## Setting up

Node 24 or newer and Python 3.11 or newer.

```bash
cd web && npm ci
```

## Checks before you open a pull request

From the repository folder:

```bash
python scripts/premerge.py
```

That runs the Python tests, the web tests, the type check and the build, as CI does ([.github/workflows/premerge.yml](.github/workflows/premerge.yml)). The browser tests are separate (`cd web && npx playwright test -c src/app/e2e/playwright.config.ts`; CI runs them too). Tests that need measured data which is not distributed skip themselves; that is expected.

A new check should be shown to fail: break the code it guards on purpose, see the test go red, put the code back.

## Style

Match the surrounding code. Comments say why, not what. Files use Unix line endings. Keep a change to one concern per commit, with a message that says what and why.

## Reporting a problem

Use the issue templates. For a wrong number, say which library, which state and what you compared it with.

By contributing you agree your contribution is released under the MIT licence of this repository.
