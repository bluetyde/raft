/**
 * LibraryReader implementations for the browser: fetch from a base URL, or a map of files
 * the main thread transferred (File API folder drop). Path safety is the validator's job.
 */

import type { LibraryReader } from "../library/platform";
import type { LibrarySource } from "./protocol";

type FetchLike = (url: string) => Promise<{ ok: boolean; status?: number; arrayBuffer(): Promise<ArrayBuffer> }>;

/** Reads `relPath` relative to `base` (which must end with "/"). A missing file (404 or 410) reads as null; any other failure (a 403, a 500, a rate limit) is an error that names the URL. */
export function fetchReader(base: string, fetchFn: FetchLike = (u) => fetch(u)): LibraryReader {
  const root = base.endsWith("/") ? base : base + "/";
  return {
    async read(relPath: string): Promise<Uint8Array | null> {
      const res = await fetchFn(root + relPath);
      if (!res.ok) {
        if (res.status === 404 || res.status === 410) return null;
        throw new Error(`${root + relPath}: HTTP ${res.status ?? "error"}`);
      }
      return new Uint8Array(await res.arrayBuffer());
    },
  };
}

/** Reads from a map of manifest-relative paths. Keys are looked up with Object.hasOwn (web/README parity rules). */
export function filesReader(files: Record<string, ArrayBuffer>): LibraryReader {
  return {
    async read(relPath: string): Promise<Uint8Array | null> {
      if (!Object.hasOwn(files, relPath)) return null;
      return new Uint8Array(files[relPath]!);
    },
  };
}

export function readerFor(source: LibrarySource, fetchFn?: FetchLike): LibraryReader {
  return source.kind === "url" ? fetchReader(source.base, fetchFn) : filesReader(source.files);
}
