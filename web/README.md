# web/

Browser runtime: Vite + TypeScript, tested with Vitest. Node 24 (same on Windows and in the agent sandbox).

```
npm ci --ignore-scripts   # exact versions from package-lock.json
npm test                  # vitest run
npm run typecheck         # tsc --noEmit
npm run build             # typecheck + vite build -> dist/
npm run dev               # dev server on VR_PORT (default 5187)
```

Dependencies are pinned to exact versions and `package-lock.json` is committed (generated on Windows; it includes the Linux native bindings, so `npm ci` works in the sandbox too). Adding or upgrading a dependency is the dispatcher's decision, not a delegated task's.

The Python code under `pipeline/` and `physics_ref/` is the reference. TypeScript ports it and must agree with it on every shared fixture.

## Library validator design (A5-1)

Port of `pipeline/library/minischema.py` and `pipeline/library/validate.py` into `src/library/`.

- **Own minischema, not a JSON Schema library.** The schema uses a small keyword subset, and the Python checker rejects any keyword outside it. A general library would accept keywords Python ignores, and would differ in details (formats, `$ref` resolution, error paths). A line-for-line port of ~150 lines keeps both sides identical and dependency-free.
- **Injected file reader** (`src/library/platform.ts`, `LibraryReader`). The validator never touches `node:fs` or `fetch`; it asks the reader for a manifest-relative path and gets bytes or `null` (not a regular file). `src/library/node-reader.ts` is the Node implementation for tests and scripts; a fetch/File API reader comes with the loader. Path safety (`_safe_relpath`) is checked by the validator before the reader is called.
- **WebCrypto SHA-256** (`sha256Hex` in `platform.ts`): `crypto.subtle` exists in browsers and in Node, so no hashing dependency.
- **Schema imported from the repo** (`import schema from "../../../schema/library.schema.json"`): one source of truth; `vite.config.ts` allows `..`.

### Parity rules (where JavaScript and Python differ by default)

The Python side was pinned to what JavaScript can reproduce (commit "minischema/validate: pin semantics…"). The TypeScript side must match:

| Topic | Rule |
|---|---|
| `const` / `enum` | JSON equality: booleans never equal numbers; `1` equals `1.0`; arrays and objects compared deeply |
| `pattern` | `new RegExp(pattern, "u").test(v)`; Python maps a trailing `$` to `\Z` so both mean end of string |
| `minLength` | Code points (`[...v].length`), not UTF-16 units |
| `number` / `integer` | Finite numbers only; `integer` = `Number.isInteger`; booleans are never numbers |
| Manifest bytes | `new TextDecoder("utf-8", { fatal: true, ignoreBOM: true })`: invalid UTF-8 and a leading BOM are both `E_JSON` (Python's `json.loads` rejects a BOM) |
| `NaN` / `Infinity` tokens | `E_JSON` on both sides (`JSON.parse` rejects them; Python uses `parse_constant`) |
| Lookups by data keys | Never `obj[key]` on a parsed object for a key that comes from the data: a rod id `constructor` would find `Object.prototype.constructor`. Use `Object.hasOwn`, or build `Map`s |
| Float32 arrays | `DataView.getFloat32(offset + 4 * i, true)` (little-endian; offsets may be unaligned) |
| Sums | Explicit left-to-right loops (Python 3.12+ `sum()` is compensated; the validator's tolerances absorb the difference) |
| Issue order | Not part of the contract. Tests compare the multiset of `(code, path)`; messages may differ |
