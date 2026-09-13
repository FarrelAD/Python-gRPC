"""FastAPI REST Gateway exposing HTTP endpoints that proxy to the gRPC Telemetry Collector."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
import grpc
from pydantic import BaseModel, Field

from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import RequestIdClientInterceptor
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

GRPC_TARGET = os.getenv("GRPC_TARGET", "localhost:50051")


class ReadingPayload(BaseModel):
    device_id: str = Field(..., examples=["PZEM-004T-REST-01"])
    device_type: str = Field("PZEM-004T")
    timestamp_unix_ms: int | None = None
    voltage: float = Field(..., ge=0.0, le=1000.0)
    current: float = Field(..., ge=0.0, le=1000.0)
    active_power: float = Field(..., ge=0.0)
    energy: float = Field(..., ge=0.0)
    frequency: float = Field(..., ge=45.0, le=65.0)
    power_factor: float = Field(..., ge=0.0, le=1.0)


class AckResponse(BaseModel):
    success: bool
    message: str
    received_at_unix_ms: int


class BatchSummaryResponse(BaseModel):
    received: int
    rejected: int
    avg_active_power: float


class GatewayState:
    channel: grpc.aio.Channel | None = None
    stub: pzem_004t_pb2_grpc.DeviceTelemetryStub | None = None


state = GatewayState()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialize gRPC channel on startup
    state.channel = grpc.aio.insecure_channel(
        GRPC_TARGET,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
        interceptors=[RequestIdClientInterceptor(client_version="gateway-1.0")],
    )
    state.stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(state.channel)
    yield
    # Close channel on shutdown
    if state.channel is not None:
        await state.channel.close()


app = FastAPI(
    title="PZEM-004t REST-to-gRPC Gateway",
    description="Demonstrates REST API consumers communicating with internal gRPC microservices.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/v1/telemetry", response_model=AckResponse)
async def report_reading(payload: ReadingPayload) -> AckResponse:
    """Proxy HTTP POST to gRPC ReportReading (unary)."""
    if state.stub is None:
        raise HTTPException(status_code=503, detail="gRPC gateway channel unavailable")

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
        ack = await state.stub.ReportReading(request, timeout=5.0)
        return AckResponse(
            success=ack.success,
            message=ack.message,
            received_at_unix_ms=ack.received_at_unix_ms,
        )
    except grpc.RpcError as exc:
        raise HTTPException(status_code=502, detail=f"gRPC call failed: {exc.details()}") from exc


@app.post("/api/v1/telemetry/batch", response_model=BatchSummaryResponse)
async def report_batch(readings: list[ReadingPayload]) -> BatchSummaryResponse:
    """Proxy HTTP POST list to gRPC ReportReadings (client-streaming)."""
    if state.stub is None:
        raise HTTPException(status_code=503, detail="gRPC gateway channel unavailable")

    async def _generator():
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
        summary = await state.stub.ReportReadings(_generator(), timeout=10.0)
        return BatchSummaryResponse(
            received=summary.received,
            rejected=summary.rejected,
            avg_active_power=summary.avg_active_power,
        )
    except grpc.RpcError as exc:
        raise HTTPException(status_code=502, detail=f"gRPC call failed: {exc.details()}") from exc


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "grpc_target": GRPC_TARGET}
