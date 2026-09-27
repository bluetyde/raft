import { describe, expect, it } from "vitest";
import { buildCatalog, CATALOG } from "./catalog";

describe("library catalog", () => {
  it("groups files by the folder that holds manifest.json, with manifest-relative paths", () => {
    const c = buildCatalog({
      "../../../libraries/a/manifest.json": "/u/a/m",
      "../../../libraries/a/arrays/x.f32": "/u/a/x",
      "../../../libraries/b/manifest.json": "/u/b/m",
    });
    expect(c.map((e) => e.name)).toEqual(["a", "b"]);
    expect([...c[0]!.files.entries()]).toEqual([
      ["manifest.json", "/u/a/m"],
      ["arrays/x.f32", "/u/a/x"],
    ]);
  });

  it("ships the synthetic core and triga-jsi-242, each with its arrays", () => {
    const names = CATALOG.map((e) => e.name);
    expect(names).toEqual(["synthetic-core", "triga-jsi-242"]);
    for (const e of CATALOG) {
      expect(e.files.has("manifest.json")).toBe(true);
      expect([...e.files.keys()].some((k) => k.startsWith("arrays/"))).toBe(true);
    }
  });
});
