"""PZEM-004t electrical meter simulator.

A PZEM-004t is an AC power monitoring module measuring voltage, current,
active power, accumulated energy, frequency and power factor. This class
emulates the module and produces realistic, slightly noisy ReadingReport
messages as a gRPC client would transmit them.
"""

from __future__ import annotations

import random
import time
from typing import Iterator

from python_grpc.proto import pzem_004t_pb2

DEVICE_TYPE = "PZEM-004T"

NOMINAL_VOLTAGE_V = 230.0
NOMINAL_CURRENT_A = 2.5
NOMINAL_FREQUENCY_HZ = 50.0
NOMINAL_POWER_FACTOR = 0.98
NOISE_RATIO = 0.02


class PZEM004TDevice:
    def __init__(
        self,
        device_id: str = "PZEM-004T-0001",
        read_interval_s: float = 1.0,
        seed: int | None = None,
        energy_start_kwh: float = 12.34,
    ) -> None:
        self.device_id = device_id
        self.read_interval_s = read_interval_s
        self._energy_kwh = energy_start_kwh
        self._last_read_s = time.monotonic()
        self._rng = random.Random(seed)

    def _noisy(self, nominal: float) -> float:
        return round(nominal * (1.0 + self._rng.uniform(-NOISE_RATIO, NOISE_RATIO)), 3)

    def read(self) -> pzem_004t_pb2.ReadingReport:
        now = time.monotonic()
        elapsed_h = (now - self._last_read_s) / 3600.0
        self._last_read_s = now

        voltage = self._noisy(NOMINAL_VOLTAGE_V)
        current = self._noisy(NOMINAL_CURRENT_A)
        power_factor = min(1.0, self._noisy(NOMINAL_POWER_FACTOR))
        active_power = round(voltage * current * power_factor, 3)
        self._energy_kwh += active_power * elapsed_h / 1000.0

        report = pzem_004t_pb2.ReadingReport()
        report.device_id = self.device_id
        report.device_type = DEVICE_TYPE
        report.timestamp_unix_ms = int(time.time() * 1000)
        report.voltage = voltage
        report.current = current
        report.active_power = active_power
        report.energy = round(self._energy_kwh, 6)
        report.frequency = self._noisy(NOMINAL_FREQUENCY_HZ)
        report.power_factor = power_factor
        return report

    def read_many(self, count: int) -> Iterator[pzem_004t_pb2.ReadingReport]:
        for _ in range(count):
            yield self.read()
