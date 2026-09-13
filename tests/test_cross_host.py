"""Automated pytest integration tests for cross-host gRPC communication.

Simulates two or more physically separate client hosts communicating concurrently
over HTTP/2 gRPC with a central collector server:
  - Host 1 (Edge IoT Gateway): Transmits periodic telemetry readings over gRPC
  - Host 2 (Remote Monitoring Dashboard): Subscribes to live streams over gRPC
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import grpc
import pytest

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import (
    RequestIdClientInterceptor,
    ServerLoggingAndRecoveryInterceptor,
)
from python_grpc.core.device.pzem_004t import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc


@pytest.fixture
async def cross_host_topology() -> AsyncGenerator[
    tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
    ],
    None,
]:
    """Spins up a central gRPC server and connects two completely independent

    client channels representing Host A (Edge IoT) and Host B (Remote Monitor).
    """
    server = grpc.aio.server(
        interceptors=[ServerLoggingAndRecoveryInterceptor()],
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
    )
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)

    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    target = f"127.0.0.1:{port}"

    # Channel 1: Host A (Edge IoT Device)
    edge_channel = grpc.aio.insecure_channel(
        target,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
        interceptors=[RequestIdClientInterceptor(client_version="edge-iot-1.0")],
    )
    edge_stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(edge_channel)

    # Channel 2: Host B (Remote Monitoring Station)
    monitor_channel = grpc.aio.insecure_channel(
        target,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
        interceptors=[RequestIdClientInterceptor(client_version="monitor-1.0")],
    )
    monitor_stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(monitor_channel)

    try:
        yield servicer, edge_stub, monitor_stub
    finally:
        await edge_channel.close()
        await monitor_channel.close()
        await server.stop(grace=0)


async def test_cross_host_telemetry_streaming(
    cross_host_topology: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
    ],
) -> None:
    """Verifies that readings reported by Edge Host A are broadcast in real time

    over gRPC to Monitor Host B.
    """
    servicer, edge_stub, monitor_stub = cross_host_topology
    device = PZEM004TDevice(device_id="PZEM-CROSS-01", seed=42)

    received_readings: list[pzem_004t_pb2.ReadingReport] = []

    async def _subscriber() -> None:
        call = monitor_stub.Subscribe(pzem_004t_pb2.SubscribeRequest(device_id="PZEM-CROSS-01"))
        async for reading in call:
            received_readings.append(reading)
            if len(received_readings) == 3:
                call.cancel()
                break

    async def _producer() -> None:
        # Allow subscriber channel to establish connection and register
        await asyncio.sleep(0.05)
        for _ in range(3):
            report = device.read()
            ack = await edge_stub.ReportReading(report, timeout=5.0)
            assert ack.success is True
            await asyncio.sleep(0.02)

    subscriber_task = asyncio.create_task(_subscriber())
    producer_task = asyncio.create_task(_producer())

    await asyncio.gather(subscriber_task, producer_task)

    assert len(received_readings) == 3
    for r in received_readings:
        assert r.device_id == "PZEM-CROSS-01"
        assert r.voltage > 0.0
        assert r.current > 0.0
        assert r.active_power > 0.0

    assert len(servicer.readings) == 3


async def test_cross_host_wildcard_subscription(
    cross_host_topology: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
    ],
) -> None:
    """Verifies that a monitor subscribed with wildcard '*' receives reports

    originating from multiple distinct edge devices.
    """
    _, edge_stub, monitor_stub = cross_host_topology

    dev1 = PZEM004TDevice(device_id="PZEM-DEV-ALPHA", seed=1)
    dev2 = PZEM004TDevice(device_id="PZEM-DEV-BETA", seed=2)

    received_devices: list[str] = []

    async def _subscriber() -> None:
        call = monitor_stub.Subscribe(pzem_004t_pb2.SubscribeRequest(device_id="*"))
        async for reading in call:
            received_devices.append(reading.device_id)
            if len(received_devices) == 2:
                call.cancel()
                break

    async def _producer() -> None:
        await asyncio.sleep(0.05)
        await edge_stub.ReportReading(dev1.read(), timeout=5.0)
        await asyncio.sleep(0.02)
        await edge_stub.ReportReading(dev2.read(), timeout=5.0)

    subscriber_task = asyncio.create_task(_subscriber())
    producer_task = asyncio.create_task(_producer())

    await asyncio.gather(subscriber_task, producer_task)

    assert "PZEM-DEV-ALPHA" in received_devices
    assert "PZEM-DEV-BETA" in received_devices


async def test_cross_host_subscriber_disconnect_resilience(
    cross_host_topology: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
    ],
) -> None:
    """Verifies that when a monitor client abruptly disconnects, the edge client

    can still publish readings without server errors.
    """
    servicer, edge_stub, monitor_stub = cross_host_topology
    dev = PZEM004TDevice(device_id="PZEM-DEV-RESILIENT", seed=99)

    # 1. Connect subscriber and immediately cancel
    call = monitor_stub.Subscribe(pzem_004t_pb2.SubscribeRequest(device_id="PZEM-DEV-RESILIENT"))
    call.cancel()

    # 2. Allow event loop to process cancellation
    await asyncio.sleep(0.05)

    # 3. Edge device publishes reading — must succeed
    ack = await edge_stub.ReportReading(dev.read(), timeout=5.0)
    assert ack.success is True
    assert len(servicer.readings) == 1
