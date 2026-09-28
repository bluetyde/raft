import type { RuntimeClient } from "../runtime/client";
import type { FromWorker } from "../runtime/protocol";

export class JevCopilot {
  private ws: WebSocket | null = null;
  private client: RuntimeClient;
  private role: "operator" | "instructor";
  private enabled: boolean = false;
  /** Track the last choice so we only act when the decision changes. */
  private lastChoice: string | null = null;

  constructor(client: RuntimeClient, role: "operator" | "instructor") {
    this.client = client;
    this.role = role;
  }

  public toggle(): void {
    if (this.enabled) {
      this.disconnect();
    } else {
      this.connect();
    }
  }

  private connect(): void {
    this.ws = new WebSocket(`ws://localhost:8000/ws/${this.role}`);
    this.ws.onopen = () => {
      console.log(`[JevCopilot] Connected as ${this.role}`);
      this.enabled = true;
    };
    this.ws.onmessage = (event) => {
      this.handleMessage(event.data);
    };
    this.ws.onclose = () => {
      console.log("[JevCopilot] Disconnected");
      this.enabled = false;
      this.ws = null;
      this.lastChoice = null;
    };
    this.ws.onerror = (err) => {
      console.error("[JevCopilot] WebSocket error:", err);
      this.enabled = false;
      this.ws = null;
    };
  }

  private disconnect(): void {
    if (this.ws) {
      this.ws.close();
    }
  }

  public onSnapshot(snapMsg: Extract<FromWorker, { kind: "snapshot" }>, scenarioState?: any): void {
    if (!this.enabled || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const s = snapMsg.snapshot;
    let premise = "";
    let hypotheses: string[] = [];

    if (this.role === "operator") {
      const power = s.indicated?.["power"] ?? 0;
      const period = s.indicated?.["period"] ?? 0;
      const fuelTemp = s.indicated?.["temp.fuel"] ?? 0;

      // Describe the startup state explicitly so the model doesn't call a dead reactor "stable"
      const isShutdown = power < 1e-6;
      const powerDesc = isShutdown
        ? "The reactor is shutdown (power is essentially zero)."
        : `Power is ${power.toExponential(3)} W.`;
      const periodDesc = isShutdown ? "" : ` Period is ${period.toFixed(2)} seconds.`;
      const tempDesc = `Fuel Temperature is ${fuelTemp.toFixed(1)} K.`;

      premise = `ROLE: Nuclear Reactor Operator. GOAL: Bring the reactor to operating power, maintain safe power levels, and avoid SCRAMs. CURRENT STATE: ${powerDesc}${periodDesc} ${tempDesc}`;

      hypotheses = [
        "The reactor is shutdown or power is near zero. I must pull the regulating rod UP to start it.",
        "Power is rising safely. I will STOP the control rods and monitor.",
        "Power is rising too fast or the period is dangerously short. I will push the regulating rod DOWN.",
        "The reactor is out of control. I will trigger a manual SCRAM immediately.",
      ];
    } else {
      // Instructor
      const power = s.indicated?.["power"] ?? 0;
      const scenarioText = scenarioState ? JSON.stringify(scenarioState) : "No active scenario.";
      premise = `ROLE: Simulation Instructor. GOAL: Provide a challenging but solvable scenario for the operator. CURRENT STATE: ${scenarioText}. Power is ${power.toExponential(3)} W.`;

      hypotheses = [
        "The operator is busy. I will wait and observe.",
        "I will trigger an instrument drift fault to confuse the operator.",
        "I will jam a control rod (stuck) to see how they react.",
        "The scenario is complete. I will end the simulation."
      ];
    }

    this.ws.send(JSON.stringify({ premise, hypotheses }));
  }

  private handleMessage(data: string): void {
    try {
      const msg = JSON.parse(data);
      if (msg.error) {
        console.error("[JevCopilot] Server error:", msg.error);
        return;
      }
      const choice = msg.choice;
      if (!choice) return;

      // Only act when the decision changes — avoids hammering the engine
      // with the same rod command every tick when nothing has changed.
      if (choice === this.lastChoice) return;
      this.lastChoice = choice;

      console.log(`[JevCopilot] AI chose: ${choice}`);
      this.executeChoice(choice);
    } catch (err) {
      console.error("[JevCopilot] JSON decode error:", err);
    }
  }

  private executeChoice(choice: string): void {
    if (this.role === "operator") {
      // Rod IDs in the engine: "regulating", "transient", "safety", "shim"
      if (choice.includes("pull the regulating rod UP")) {
        this.client.command({ type: "rod.move", rod: "regulating", direction: "out" });
      } else if (choice.includes("push the regulating rod DOWN")) {
        this.client.command({ type: "rod.move", rod: "regulating", direction: "in" });
      } else if (choice.includes("STOP")) {
        this.client.command({ type: "rod.move", rod: "regulating", direction: "stop" });
      } else if (choice.includes("manual SCRAM")) {
        this.client.command({ type: "trip.manual" });
      }
    } else {
      // Instructor choices
      if (choice.includes("jam a control rod")) {
        this.client.command({ type: "fault.rod", rod: "transient", kind: "stuck" });
      }
    }
  }
}

export function createCopilotButton(copilot: JevCopilot): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.textContent = "Connect AI Copilot";
  btn.style.cssText = "margin-left: 10px; padding: 4px 8px; font-weight: bold; cursor: pointer;";
  btn.onclick = () => {
    copilot.toggle();
    btn.textContent = btn.textContent === "Connect AI Copilot" ? "Disconnect AI Copilot" : "Connect AI Copilot";
  };
  return btn;
}
