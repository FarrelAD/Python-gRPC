"""Industry-grade resilient gRPC telemetry client.

Features:
  - HTTP/2 Keepalive & reconnection channel options
  - Client interceptor injecting request-id and client version
  - Client-side timeouts (deadlines) on unary and streams
  - Comprehensive logging and health-check verification
"""

# pyrefly: ignore-errors[missing-attribute]

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import RequestIdClientInterceptor
from python_grpc.core.device.pzem_004t import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

DEFAULT_TARGET = "localhost:50051"
DEFAULT_TIMEOUT_S = 10.0

logger = logging.getLogger("telemetry_device_client")

DeviceTelemetryStub = pzem_004t_pb2_grpc.DeviceTelemetryStub


def _fmt(report: pzem_004t_pb2.ReadingReport) -> str:
    return (
        f"{report.device_id} U={report.voltage:.1f}V I={report.current:.2f}A "
        f"P={report.active_power:.1f}W E={report.energy:.6f}kWh "
        f"f={report.frequency:.2f}Hz PF={report.power_factor:.3f}"
    )


async def check_health(channel: grpc.aio.Channel, service_name: str = "") -> bool:
    """Query the remote gRPC server's standard health service."""
    health_stub = health_pb2_grpc.HealthStub(channel)
    try:
        response = await health_stub.Check(
            health_pb2.HealthCheckRequest(service=service_name),
            timeout=3.0,
        )
        is_healthy = response.status == health_pb2.HealthCheckResponse.SERVING
        logger.info(
            "Health check service=%r status=%s",
            service_name,
            health_pb2.HealthCheckResponse.ServingStatus.Name(response.status),
        )
        return is_healthy
    except grpc.RpcError as exc:
        logger.warning(
            "Health check failed: code=%s details=%s", exc.code(), exc.details()
        )
        return False


async def run_unary(
    stub: DeviceTelemetryStub,
    device: PZEM004TDevice,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> None:
    reading = device.read()
    ack = await stub.ReportReading(reading, timeout=timeout)
    logger.info(
        "[unary]    ReportReading  -> success=%s msg=%r", ack.success, ack.message
    )


async def run_client_streaming(
    stub: DeviceTelemetryStub,
    device: PZEM004TDevice,
    count: int,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> None:
    async def readings() -> AsyncIterable[pzem_004t_pb2.ReadingReport]:
        for _ in range(count):
            yield device.read()

    summary = await stub.ReportReadings(readings(), timeout=timeout)
    logger.info(
        "[client]   ReportReadings -> received=%d rejected=%d avg_power=%.1fW",
        summary.received,
        summary.rejected,
        summary.avg_active_power,
    )


async def run_server_streaming(
    stub: DeviceTelemetryStub,
    device: PZEM004TDevice,
    count: int,
) -> None:
    request = pzem_004t_pb2.SubscribeRequest(device_id=device.device_id)
    logger.info("[server]   Subscribe      -> live readings for %s:", device.device_id)
    call = stub.Subscribe(request)
    i = 0
    try:
        async for report in call:
            logger.info("           %s", _fmt(report))
            i += 1
            if i >= count:
                call.cancel()
                break
    except asyncio.CancelledError:
        pass


async def run_bidi(
    stub: DeviceTelemetryStub,
    device: PZEM004TDevice,
    count: int,
) -> None:
    async def readings() -> AsyncIterable[pzem_004t_pb2.ReadingReport]:
        for _ in range(count):
            yield device.read()

    logger.info("[bidi]     StreamTelemetry -> %d readings sent, acks:", count)
    async for ack in stub.StreamTelemetry(readings()):
        logger.info("           success=%s msg=%r", ack.success, ack.message)


async def run_demo(
    target: str,
    device_id: str,
    count: int,
    rpcs: set[str],
    timeout: float = DEFAULT_TIMEOUT_S,
) -> None:
    device = PZEM004TDevice(device_id=device_id, read_interval_s=1.0)
    interceptors = [RequestIdClientInterceptor(client_version="2.0.0")]

    async with grpc.aio.insecure_channel(
        target,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
        interceptors=interceptors,
    ) as channel:
        # Verify server health first
        logger.info("Connecting to collector at %s (Device: %s)", target, device_id)
        is_healthy = await check_health(channel)
        if not is_healthy:
            logger.warning(
                "Target %s is not currently reporting SERVING status.", target
            )

        stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)

        if "unary" in rpcs:
            await run_unary(stub, device, timeout=timeout)
        if "client-stream" in rpcs:
            await run_client_streaming(stub, device, count, timeout=timeout)
        if "server-stream" in rpcs:
            await run_server_streaming(stub, device, count)
        if "bidi" in rpcs:
            await run_bidi(stub, device, count)
        logger.info("Demo complete.")


def run(target: str, device_id: str, count: int, rpcs: set[str]) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_demo(target, device_id, count, rpcs))
