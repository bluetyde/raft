"""Tests for the trace-based rise-rate fit (validation/trace_period.py). Standard library only."""
from __future__ import annotations

import math
import unittest

from validation.trace_period import fit_omega, invert


def synthetic(omega: float, noise: float = 0.0, base: float = 0.05, dt: float = 5e-5) -> list[float]:
    """Flat baseline for 0.3 s, then base + A exp(omega t) up to a 100 MW peak, then a fall; deterministic 'noise'."""
    out = [base + noise * math.sin(1.7 * k) for k in range(int(0.3 / dt))]
    t_peak = math.log(100.0 / 1e-6) / omega
    k = 0
    while k * dt < t_peak:
        out.append(base + 1e-6 * math.exp(omega * k * dt) + noise * math.sin(1.7 * len(out)))
        k += 1
    out += [base + 100.0 * math.exp(-40.0 * j * dt) for j in range(2000)]
    return out


class TestFit(unittest.TestCase):
    def test_recovers_rate(self):
        for omega in (40.0, 90.0, 170.0):
            fit = fit_omega(synthetic(omega), 5e-5)
            self.assertIsNotNone(fit)
            self.assertAlmostEqual(fit[0] / omega, 1.0, delta=2e-3, msg=omega)

    def test_baseline_is_removed(self):
        a = fit_omega(synthetic(90.0, base=0.0), 5e-5)[0]
        b = fit_omega(synthetic(90.0, base=0.3), 5e-5)[0]
        self.assertAlmostEqual(a / b, 1.0, delta=2e-3)

    def test_too_noisy_gives_none(self):
        # noise so large that 10 x noise exceeds a third of 20 % of the peak: no usable rise
        self.assertIsNone(fit_omega(synthetic(90.0, noise=1.0), 5e-5))

    def test_invert(self):
        curve = [(1.0, 0.0), (1.5, 80.0), (2.0, 170.0)]
        self.assertAlmostEqual(invert(curve, 125.0), 1.75)
        self.assertIsNone(invert(curve, 200.0))


if __name__ == "__main__":
    unittest.main()
