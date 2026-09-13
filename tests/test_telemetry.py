"""End-to-end tests for all four gRPC call types using a real (local) server."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
import grpc
import pytest

from python_grpc.device import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc
from python_grpc.server import DeviceTelemetryServicer


@pytest.fixture
async def telemetry_env() -> AsyncGenerator[
    tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice],
    None,
]:
    server = grpc.aio.server()
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
    device = PZEM004TDevice(seed=42)

    try:
        yield servicer, stub, device
    finally:
        await channel.close()
        await server.stop(grace=0)


async def test_valid_reading_is_acknowledged_and_stored(
    telemetry_env: tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice]
) -> None:
    servicer, stub, device = telemetry_env
    ack = await stub.ReportReading(device.read())
    assert ack.success is True
    assert device.device_id in ack.message
    assert ack.received_at_unix_ms > 0
    assert len(servicer.readings) == 1


async def test_invalid_reading_is_rejected(
    telemetry_env: tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice]
) -> None:
    servicer, stub, device = telemetry_env
    report = device.read()
    report.voltage = 0.0
    ack = await stub.ReportReading(report)
    assert ack.success is False
    assert len(servicer.readings) == 0


async def test_batch_upload_produces_summary(
    telemetry_env: tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice]
) -> None:
    servicer, stub, device = telemetry_env

    async def readings():
        for _ in range(10):
            yield device.read()
        bad_voltage = device.read()
        bad_voltage.voltage = 9999.0
        yield bad_voltage
        no_id = device.read()
        no_id.device_id = ""
        yield no_id

    summary = await stub.ReportReadings(readings())
    assert summary.received == 10
    assert summary.rejected == 2
    assert summary.avg_active_power > 0.0
    assert len(servicer.readings) == 10


async def test_streams_live_readings_for_device(
    telemetry_env: tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice]
) -> None:
    _, stub, device = telemetry_env
    request = pzem_004t_pb2.SubscribeRequest(device_id=device.device_id)
    received: list[pzem_004t_pb2.ReadingReport] = []

    async def _consumer() -> None:
        call = stub.Subscribe(request)
        async for report in call:
            received.append(report)
            if len(received) == 3:
                call.cancel()
                break

    async def _producer() -> None:
        # Short yield to ensure subscriber registration is active
        await asyncio.sleep(0.05)
        for _ in range(3):
            await stub.ReportReading(device.read())
            await asyncio.sleep(0.01)

    consumer_task = asyncio.create_task(_consumer())
    producer_task = asyncio.create_task(_producer())

    await asyncio.gather(consumer_task, producer_task)

    assert len(received) == 3
    for report in received:
        assert report.device_id == device.device_id
        assert report.voltage > 0.0
        assert report.frequency > 0.0


async def test_every_reading_gets_an_ack(
    telemetry_env: tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, PZEM004TDevice]
) -> None:
    servicer, stub, device = telemetry_env

    async def readings():
        for _ in range(5):
            yield device.read()

    acks: list[pzem_004t_pb2.Ack] = []
    async for ack in stub.StreamTelemetry(readings()):
        acks.append(ack)
    assert len(acks) == 5
    assert all(a.success for a in acks)
    assert len(servicer.readings) == 5
