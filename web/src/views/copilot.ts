import type { RuntimeClient } from "../runtime/client";
import type { DecisionRequest } from "../runtime/protocol";

export class JevCopilot {
  private enabled = false;
  private ws: WebSocket | null = null;
  private client: RuntimeClient;
  private role: "operator" | "instructor";

  constructor(client: RuntimeClient, role: "operator" | "instructor") {
    this.client = client;
    this.role = role;
    
    // Listen for requests from the runtime supervisor
    this.client.on("decision_request", (msg) => {
      this.handleDecisionRequest(msg.request);
    });
  }

  public toggle(): void {
    if (this.enabled) {
      this.enabled = false;
      this.client.supervisorDisable();
      if (this.ws) {
        this.ws.close();
        this.ws = null;
      }
      console.log("[JevCopilot] Disconnected");
    } else {
      this.enabled = true;
      this.client.supervisorEnable();
      this.connectWs();
    }
  }

  public disconnect(): void {
    if (this.enabled) {
      this.toggle();
    }
  }

  private connectWs(): void {
    this.ws = new WebSocket("ws://localhost:8000/jev");
    this.ws.onopen = () => console.log("[JevCopilot] Connected");
    
    this.ws.onmessage = (ev) => {
      if (!this.enabled) return;
      try {
        const msg = JSON.parse(ev.data);
        if (msg.error) {
          console.error("[JevCopilot] Server error:", msg.error);
          return;
        }
        
        // Ensure this is a DecisionResponse
        if (msg.candidateId && msg.requestId) {
          this.client.decisionResponse(msg);
        }
      } catch (err) {
        console.error("[JevCopilot] JSON decode error:", err);
      }
    };
    
    this.ws.onclose = () => {
      if (this.enabled) {
        console.warn("[JevCopilot] WebSocket closed unexpectedly");
        this.enabled = false;
        this.client.supervisorDisable();
        this.ws = null;
        
        // Notify UI button to flip back?
        // Simple manual DOM sync is hard here without callback, 
        // but the runtime handles "supervisor.disable" and halts gracefully.
      }
    };
    
    this.ws.onerror = (err) => {
      console.error("[JevCopilot] WebSocket error:", err);
    };
  }

  private handleDecisionRequest(req: DecisionRequest): void {
    if (!this.enabled || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    
    // Send as JSON
    this.ws.send(JSON.stringify(req));
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
