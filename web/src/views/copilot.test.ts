import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JevCopilot } from './copilot';
import type { RuntimeClient } from '../runtime/client';

describe('JevCopilot PID Loop', () => {
  let copilot: JevCopilot;
  let mockClient: any;

  beforeEach(() => {
    mockClient = {
      command: vi.fn(),
      disconnect: vi.fn(),
    };
    // Initialize copilot with the mocked client and role 'operator'
    copilot = new JevCopilot(mockClient as unknown as RuntimeClient, 'operator');
    (copilot as any).enabled = true;
    (copilot as any).ws = { readyState: 1, send: vi.fn() } as any; // mock websocket OPEN
  });

  it('activates PID on STOP choice and commands rod on next tick', () => {
    // 1. Send first snapshot to set lastPower
    copilot.onSnapshot({
      kind: 'snapshot',
      snapshot: {
        t: 1.0,
        truth: { power: 50000, period: 20, fuelTemp: 300, rods: { regulating: { position: 0.5, moving: null } } }
      }
    } as any);

    // 2. Trigger the choice that engages PID
    // Private method access workaround
    (copilot as any).executeChoice("Power is rising safely. I will STOP the control rods and monitor until stable.");

    expect((copilot as any).pid.isEnabled()).toBe(true);

    // 3. Send next snapshot with higher power (first tick establishes dt)
    copilot.onSnapshot({
      kind: 'snapshot',
      snapshot: {
        t: 1.033, // 30Hz tick
        truth: { power: 60000, period: 10, fuelTemp: 300, rods: { regulating: { position: 0.5, moving: null } } }
      }
    } as any);

    // 4. Send second snapshot to trigger PID output
    copilot.onSnapshot({
      kind: 'snapshot',
      snapshot: {
        t: 1.066, // 30Hz tick
        truth: { power: 60000, period: 10, fuelTemp: 300, rods: { regulating: { position: 0.5, moving: null } } }
      }
    } as any);

    // 5. Assert that the client was commanded to push regulating rod 'in'
    expect(mockClient.command).toHaveBeenCalledWith(
      { type: 'rod.move', rod: 'regulating', direction: 'in' },
      undefined,
      'operator'
    );
  });
});



