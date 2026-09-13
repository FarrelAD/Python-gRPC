"""Integration test for FastAPI REST-to-gRPC Gateway."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import grpc
import httpx
import pytest

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.apps.rest_gateway.app import app, state
from python_grpc.proto import pzem_004t_pb2_grpc


@pytest.fixture
async def gateway_client() -> AsyncGenerator[
    tuple[httpx.AsyncClient, DeviceTelemetryServicer]
]:
    server = grpc.aio.server()
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    # Connect gateway state directly to ephemeral server
    state.channel = grpc.aio.insecure_channel(f"localhost:{port}")
    state.stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(state.channel)

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    try:
        yield client, servicer
    finally:
        await client.aclose()
        if state.channel is not None:
            await state.channel.close()
            state.channel = None
            state.stub = None
        await server.stop(grace=0)


async def test_gateway_unary_post(
    gateway_client: tuple[httpx.AsyncClient, DeviceTelemetryServicer],
) -> None:
    client, servicer = gateway_client
    payload = {
        "device_id": "REST-DEVICE-01",
        "device_type": "PZEM-004T",
        "voltage": 230.5,
        "current": 2.1,
        "active_power": 484.05,
        "energy": 1.25,
        "frequency": 50.0,
        "power_factor": 0.99,
    }
    response = await client.post("/api/telemetry", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "REST-DEVICE-01" in data["message"]
    assert len(servicer.readings) == 1


async def test_gateway_batch_post(
    gateway_client: tuple[httpx.AsyncClient, DeviceTelemetryServicer],
) -> None:
    client, servicer = gateway_client
    readings = [
        {
            "device_id": f"REST-DEVICE-{i}",
            "device_type": "PZEM-004T",
            "voltage": 230.0,
            "current": 1.5,
            "active_power": 345.0,
            "energy": 0.5,
            "frequency": 50.0,
            "power_factor": 1.0,
        }
        for i in range(3)
    ]
    response = await client.post("/api/telemetry/batch", json=readings)
    assert response.status_code == 200
    data = response.json()
    assert data["received"] == 3
    assert data["rejected"] == 0
    assert len(servicer.readings) == 3
