"""Integration tests for standard gRPC health checks and interceptors."""

# pyrefly: ignore-errors[missing-attribute]

from __future__ import annotations

from collections.abc import AsyncGenerator

import grpc
import pytest
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.core.common.interceptors import (
    RequestIdClientInterceptor,
    ServerLoggingAndRecoveryInterceptor,
)
from python_grpc.core.device.pzem_004t import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2_grpc


@pytest.fixture
async def health_and_interceptors_env() -> AsyncGenerator[
    tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        health_pb2_grpc.HealthStub,
        str,
    ]
]:
    server = grpc.aio.server(interceptors=[ServerLoggingAndRecoveryInterceptor()])
    servicer = DeviceTelemetryServicer()
    health_servicer = health.HealthServicer()

    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    service_name = pzem_004t_pb2_grpc.DeviceTelemetryServicer.__name__
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)

    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    channel = grpc.aio.insecure_channel(
        f"localhost:{port}",
        interceptors=[RequestIdClientInterceptor(client_version="test-1.0")],
    )
    stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
    health_stub = health_pb2_grpc.HealthStub(channel)

    try:
        yield servicer, stub, health_stub, service_name
    finally:
        await channel.close()
        await server.stop(grace=0)


async def test_health_check_returns_serving(
    health_and_interceptors_env: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        health_pb2_grpc.HealthStub,
        str,
    ],
) -> None:
    _, _, health_stub, service_name = health_and_interceptors_env
    res = await health_stub.Check(health_pb2.HealthCheckRequest(service=service_name))
    assert res.status == health_pb2.HealthCheckResponse.SERVING


async def test_health_check_unknown_service_returns_not_found(
    health_and_interceptors_env: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        health_pb2_grpc.HealthStub,
        str,
    ],
) -> None:
    _, _, health_stub, _ = health_and_interceptors_env
    with pytest.raises(grpc.aio.AioRpcError) as ctx:
        await health_stub.Check(
            health_pb2.HealthCheckRequest(service="non.existent.Service")
        )
    assert ctx.value.code() == grpc.StatusCode.NOT_FOUND


async def test_unary_call_with_client_and_server_interceptors(
    health_and_interceptors_env: tuple[
        DeviceTelemetryServicer,
        pzem_004t_pb2_grpc.DeviceTelemetryStub,
        health_pb2_grpc.HealthStub,
        str,
    ],
) -> None:
    servicer, stub, _, _ = health_and_interceptors_env
    device = PZEM004TDevice(seed=99)
    ack = await stub.ReportReading(device.read())
    assert ack.success is True
    assert len(servicer.readings) == 1
