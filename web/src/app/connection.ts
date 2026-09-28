/**
 * How a window reaches the runtime (docs/m6-instructor-design.md, D2a).
 * With SharedWorker, every window of one session shares one worker: the worker's name is the session id in the URL.
 * Without SharedWorker (some mobile browsers), the window gets its own dedicated worker, with the role "full".
 */

import { RuntimeClient } from "../runtime/client";
import { ROLES, type Role } from "../runtime/protocol";

export interface WindowParams {
  /** The session id: windows with the same id share one simulation. */
  session: string;
  role: Role;
  /** True when the URL had no session id and this window made one. */
  fresh: boolean;
}

export interface Connection {
  client: RuntimeClient;
  shared: boolean;
  role: Role;
  session: string;
}

/** Read `?session=<id>&role=<role>` from a URL. A missing session id gets a new random one. */
export function windowParams(search: string, random: () => string = () => crypto.randomUUID().slice(0, 8)): WindowParams {
  const q = new URLSearchParams(search);
  const r = q.get("role");
  const role: Role = r !== null && (ROLES as readonly string[]).includes(r) ? (r as Role) : "full";
  const given = q.get("session");
  const valid = given !== null && /^[A-Za-z0-9_-]{1,40}$/.test(given);
  return { session: valid ? given : random(), role, fresh: !valid };
}

/** The URL of another window of the same session, with a role. */
export function windowUrl(base: string, session: string, role: Role): string {
  const u = new URL(base);
  u.search = new URLSearchParams({ session, role }).toString();
  u.hash = "";
  return u.toString();
}

export function connect(params: WindowParams, clientId: string): Connection {
  if (typeof SharedWorker !== "undefined") {
    const sw = new SharedWorker(new URL("../runtime/shared-worker.ts", import.meta.url), {
      type: "module",
      name: `vr-session-${params.session}`,
    });
    const client = new RuntimeClient(sw.port, clientId);
    sw.onerror = () => {
      client.disconnected = true;
    };
    window.addEventListener("pagehide", () => client.detach());
    return { client, shared: true, role: params.role, session: params.session };
  }
  const w = new Worker(new URL("../runtime/worker.ts", import.meta.url), { type: "module" });
  return { client: new RuntimeClient(w, clientId), shared: false, role: "full", session: params.session };
}
