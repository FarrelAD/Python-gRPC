"""Telemetry REST endpoints forwarding payloads to internal gRPC collector."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated

import grpc
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from python_grpc.apps.rest_gateway.dependencies import get_telemetry_stub
from python_grpc.apps.rest_gateway.schemas import (
    AckResponse,
    BatchSummaryResponse,
    ReadingPayload,
)
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

TelemetryStubDep = Annotated[
    pzem_004t_pb2_grpc.DeviceTelemetryStub, Depends(get_telemetry_stub)
]

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


@router.post("", response_model=AckResponse)
async def report_reading(
    payload: ReadingPayload,
    stub: TelemetryStubDep,
) -> AckResponse:
    """Proxy HTTP POST to gRPC ReportReading (unary)."""
    request = pzem_004t_pb2.ReadingReport(
        device_id=payload.device_id,
        device_type=payload.device_type,
        timestamp_unix_ms=payload.timestamp_unix_ms or 0,
        voltage=payload.voltage,
        current=payload.current,
        active_power=payload.active_power,
        energy=payload.energy,
        frequency=payload.frequency,
        power_factor=payload.power_factor,
    )
    try:
        ack = await stub.ReportReading(request, timeout=5.0)
        return AckResponse(
            success=ack.success,
            message=ack.message,
            received_at_unix_ms=ack.received_at_unix_ms,
        )
    except grpc.RpcError as exc:
        raise HTTPException(
            status_code=502, detail=f"gRPC call failed: {exc.details()}"
        ) from exc


@router.post("/batch", response_model=BatchSummaryResponse)
async def report_batch(
    readings: list[ReadingPayload],
    stub: TelemetryStubDep,
) -> BatchSummaryResponse:
    """Proxy HTTP POST list to gRPC ReportReadings (client-streaming)."""

    async def _generator() -> AsyncGenerator[pzem_004t_pb2.ReadingReport]:
        for r in readings:
            yield pzem_004t_pb2.ReadingReport(
                device_id=r.device_id,
                device_type=r.device_type,
                timestamp_unix_ms=r.timestamp_unix_ms or 0,
                voltage=r.voltage,
                current=r.current,
                active_power=r.active_power,
                energy=r.energy,
                frequency=r.frequency,
                power_factor=r.power_factor,
            )

    try:
        summary = await stub.ReportReadings(_generator(), timeout=10.0)
        return BatchSummaryResponse(
            received=summary.received,
            rejected=summary.rejected,
            avg_active_power=summary.avg_active_power,
        )
    except grpc.RpcError as exc:
        raise HTTPException(
            status_code=502, detail=f"gRPC call failed: {exc.details()}"
        ) from exc


@router.get("/live")
async def stream_live_telemetry(
    stub: TelemetryStubDep,
    device_id: str = "*",
) -> StreamingResponse:
    """Stream live telemetry from gRPC Collector to HTTP clients via Server-Sent Events (SSE)."""

    async def _event_generator() -> AsyncGenerator[str]:
        request = pzem_004t_pb2.SubscribeRequest(device_id=device_id)
        call = stub.Subscribe(request)
        try:
            async for reading in call:
                payload = {
                    "device_id": reading.device_id,
                    "device_type": reading.device_type,
                    "timestamp_unix_ms": reading.timestamp_unix_ms,
                    "voltage": reading.voltage,
                    "current": reading.current,
                    "active_power": reading.active_power,
                    "energy": reading.energy,
                    "frequency": reading.frequency,
                    "power_factor": reading.power_factor,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except (grpc.RpcError, asyncio.CancelledError):
            return
        finally:
            call.cancel()

    return StreamingResponse(_event_generator(), media_type="text/event-stream")
