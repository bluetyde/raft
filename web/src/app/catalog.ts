/**
 * The libraries the app ships with. Vite bundles every file of each folder as a URL (dev and build),
 * and a LibraryReader fetches them by manifest-relative path.
 */

import type { LibraryReader } from "../library/platform";

// Paths are relative to this file. Add a library folder here to ship it.
const FILES = import.meta.glob(
  ["../../../schema/vectors/synthetic-core/**/*", "../../../libraries/triga-jsi-242/**/*"],
  { query: "?url", import: "default", eager: true },
) as Record<string, string>;

export interface CatalogEntry {
  /** Folder name, for example "triga-jsi-242". */
  name: string;
  /** Manifest-relative path -> URL. */
  files: Map<string, string>;
}

/** Group globbed file URLs by library folder (the folder that holds manifest.json). */
export function buildCatalog(files: Record<string, string>): CatalogEntry[] {
  const roots = Object.keys(files)
    .filter((p) => p.endsWith("/manifest.json"))
    .map((p) => p.slice(0, -"manifest.json".length));
  return roots
    .map((root) => {
      const map = new Map<string, string>();
      for (const [p, url] of Object.entries(files)) if (p.startsWith(root)) map.set(p.slice(root.length), url);
      return { name: root.split("/").filter(Boolean).at(-1)!, files: map };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export const CATALOG = buildCatalog(FILES);

export function catalogReader(entry: CatalogEntry, fetchFn: (url: string) => Promise<Response> = fetch): LibraryReader {
  return {
    async read(relPath: string): Promise<Uint8Array | null> {
      const url = entry.files.get(relPath);
      if (url === undefined) return null;
      const res = await fetchFn(url);
      return res.ok ? new Uint8Array(await res.arrayBuffer()) : null;
    },
  };
}

/** Every file of a library as bytes, keyed by manifest-relative path (the runtime's `files` source). New buffers each call, so they can be transferred. */
export async function catalogFiles(
  entry: CatalogEntry,
  fetchFn: (url: string) => Promise<Response> = fetch,
): Promise<Record<string, ArrayBuffer>> {
  const out: Record<string, ArrayBuffer> = {};
  await Promise.all(
    [...entry.files].map(async ([path, url]) => {
      const res = await fetchFn(url);
      if (!res.ok) throw new Error(`could not fetch ${path} (${res.status})`);
      out[path] = await res.arrayBuffer();
    }),
  );
  return out;
}
