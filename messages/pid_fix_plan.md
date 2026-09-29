# OpenJev PID & Telemetry Fix Plan

## 1. Telemetry and Data Paths (`web/src/views/copilot.ts`)
- **Fix Time variable (`t`)**: Update the `t` extraction from `truth.t` to `snapMsg.snapshot.t`. Since `dt` was evaluating to `<= 0`, the PID was silently returning `null` on every tick.
- **Fix Fuel Temperature**: Change `truth["temp.fuel"]` to `truth.fuelTemp`. The prompt is currently feeding a hardcoded 20 °C to Mica because it cannot find the property.

## 2. PID Execution Loop (`web/src/views/copilot.ts`)
- **Un-gate the 30Hz Loop**: Move the entire PID `.update()` block *above* the `if (this.inferenceInFlight) return;` guard. Currently, the PID only updates on the rare ticks where Mica isn't evaluating, completely breaking the 30Hz continuous control requirement.
- **Lifecycle Management**: Add `this.pid.disable()` inside the `disconnect()` method so the target power clears if the user disconnects and reconnects the copilot.

## 3. PID Setpoint and Math (`web/src/views/copilot.ts`)
- **Fix Setpoint Drift**: In `executeChoice`, wrap the target setting in a condition: `if (!this.pid.isEnabled()) { this.pid.setTarget(this.lastPower); }`. This prevents every subsequent "STOP" hypothesis from dragging the target power up or down alongside the actual power.
- **Revert Integral Reset**: Remove the uncommitted `Math.sign` error-crossing integral reset. Since we already have a hard clamp (`Math.min(10) / Math.max(-10)`) for anti-windup and a small `ki`, the reset destroys the steady-state error correction.
- **Enforce Rod Limits**: When outputting a bang-bang command (`"in"` or `"out"`), check `this.rodPositions["regulating"]`. If the rod is at `>= 0.99` and the PID commands `"out"`, override to `"stop"` (and similarly for `<= 0.01` and `"in"`).

## 4. Server Cleanup (`jev-server/server.py`)
- **Remove Unused Variable**: Delete the unused `prompt_for(...)` string generation inside `evaluate_mica`.
- **Startup Error Handling**: Add a `try/except` block in the `lifespan` function when loading `DirectJudge`. If the DLL or weights fail to load, catch the exception, log a severe warning, and let the server boot up anyway so clients can connect and see the error returned cleanly.

## 5. Regression Testing (`web/src/tests/copilot.test.ts`)
- **Create a Vitest Suite**: Add a test file specifically for the PID control loop in `copilot.ts`.
- **Mocking**: Mock the `RuntimeClient` to intercept `client.command` calls.
- **Snapshot Simulation**: Feed a series of mock `SnapshotMsg` objects (with valid `snapshot.t`, `indicated.log`, and `truth.rods`) into `JevCopilot.onSnapshot()`.
- **Assertions**: 
  - Assert that calling `executeChoice("...STOP...")` activates the PID.
  - Assert that a subsequent snapshot with a higher power correctly triggers a `rod.move` `"in"` command to the `regulating` rod.
  - Assert that the PID handles time progression correctly and respects the limits.
