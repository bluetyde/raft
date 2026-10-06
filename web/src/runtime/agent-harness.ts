/**
 * Headless harness for the supervisor loop: a runtime on a fake host plus a scripted stand-in for the
 * Jev server. No browser, socket or model. Node only (tests); not bundled.
 *
 * The stand-in sees each decision_request and answers with `policy(request)`: a candidate intent
 * ("hold", "reduce", "scram", ...), null for no reply, or a full response object for malformed replies.
 */

import type { ValidityView } from "./envelope";
import type { DecisionRequest, DecisionResponse, SupervisionView } from "./protocol";
import type { Runtime } from "./runtime";
import { loadedRuntime, send, type FakeHost } from "./test-helpers";

export type Policy = (req: DecisionRequest, n: number) => string | DecisionResponse | null;

export interface AgentRig {
  host: FakeHost;
  rt: Runtime;
  requests: DecisionRequest[];
  /** The latest supervision state the runtime reported (what the panels show). */
  supervision(): SupervisionView | null;
  /** The latest validity view the runtime reported. */
  validity(): ValidityView | null;
  /** Run `ms` of wall time, answering requests as they arrive. */
  run(ms: number): Promise<void>;
  /** Commands the runtime's engine received from `clientId`, as [step, cmd]. */
  cmds(clientId: string): [number, Record<string, any>][];
  snap(): Record<string, any>;
}

export async function agentRig(policy: Policy, load: Parameters<typeof loadedRuntime>[1] = {}): Promise<AgentRig> {
  const { host, rt } = await loadedRuntime({}, load);
  const requests: DecisionRequest[] = [];
  let lastSupervision: SupervisionView | null = null;
  let lastValidity: ValidityView | null = null;
  let answered = 0;
  const rig: AgentRig = {
    host,
    rt,
    requests,
    supervision: () => host.last("supervision")?.state ?? lastSupervision,
    validity: () => host.last("validity")?.view ?? lastValidity,
    async run(ms) {
      for (let waited = 0; waited < ms; waited += 50) {
        host.advance(50);
        await rt.idle();
        for (const m of host.drain()) {
          if (m.kind === "supervision") lastSupervision = m.state;
          if (m.kind === "validity") lastValidity = m.view;
          if (m.kind !== "decision_request") continue;
          requests.push(m.request);
          const r = policy(m.request, answered++);
          if (r === null) continue;
          const response: DecisionResponse =
            typeof r === "string"
              ? {
                  protocolVersion: 1,
                  sessionId: m.request.sessionId,
                  temporalEpoch: m.request.temporalEpoch,
                  connectionId: m.request.connectionId,
                  requestId: m.request.requestId,
                  observationStep: m.request.observationStep,
                  status: "ok",
                  candidateId: r,
                }
              : r;
          await send(rt, { kind: "decision_response", response });
        }
      }
    },
    cmds: (clientId) => rt.engine!.commandLog.filter((c: any) => c.clientId === clientId).map((c: any) => [c.step, c.cmd]),
    snap: () => rt.engine!.snapshot(false),
  };
  return rig;
}

/** Start the clock at `rate` x real time and turn supervision on. */
export async function startSupervised(rig: AgentRig, rate = 1): Promise<void> {
  await send(rig.rt, { kind: "supervisor.enable" });
  await send(rig.rt, { kind: "time", rate, paused: false });
}
