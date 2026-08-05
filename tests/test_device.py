"""Unit tests for the PZEM004TDevice simulator."""

from __future__ import annotations

import unittest
from typing import override

from python_grpc.device import PZEM004TDevice


class TestPZEM004TDevice(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.device = PZEM004TDevice(seed=7)

    def test_read_produces_realistic_plausible_values(self) -> None:
        report = self.device.read()
        self.assertEqual(report.device_id, "PZEM-004T-0001")
        self.assertEqual(report.device_type, "PZEM-004T")
        self.assertGreater(report.timestamp_unix_ms, 0)
        self.assertAlmostEqual(report.voltage, 230.0, delta=10.0)
        self.assertAlmostEqual(report.current, 2.5, delta=0.3)
        self.assertGreater(report.active_power, 0.0)
        self.assertAlmostEqual(report.frequency, 50.0, delta=2.0)
        self.assertLessEqual(report.power_factor, 1.0)

    def test_seeded_rng_is_reproducible(self) -> None:
        a = PZEM004TDevice(seed=7)
        b = PZEM004TDevice(seed=7)
        self.assertEqual(a.read().voltage, b.read().voltage)

    def test_energy_monotonically_increases(self) -> None:
        first = self.device.read()
        self.assertGreaterEqual(self.device.read().energy, first.energy)

    def test_read_many_yields_requested_count(self) -> None:
        self.assertEqual(len(list(self.device.read_many(8))), 8)


if __name__ == "__main__":
    unittest.main()
