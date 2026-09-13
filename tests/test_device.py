"""Unit tests for the PZEM004TDevice simulator."""

from __future__ import annotations

import pytest

from python_grpc.device import PZEM004TDevice


@pytest.fixture
def device() -> PZEM004TDevice:
    return PZEM004TDevice(seed=7)


def test_read_produces_realistic_plausible_values(device: PZEM004TDevice) -> None:
    report = device.read()
    assert report.device_id == "PZEM-004T-0001"
    assert report.device_type == "PZEM-004T"
    assert report.timestamp_unix_ms > 0
    assert report.voltage == pytest.approx(230.0, abs=10.0)
    assert report.current == pytest.approx(2.5, abs=0.3)
    assert report.active_power > 0.0
    assert report.frequency == pytest.approx(50.0, abs=2.0)
    assert report.power_factor <= 1.0


def test_seeded_rng_is_reproducible() -> None:
    a = PZEM004TDevice(seed=7)
    b = PZEM004TDevice(seed=7)
    assert a.read().voltage == b.read().voltage


def test_energy_monotonically_increases(device: PZEM004TDevice) -> None:
    first = device.read()
    assert device.read().energy >= first.energy


def test_read_many_yields_requested_count(device: PZEM004TDevice) -> None:
    assert len(list(device.read_many(8))) == 8
