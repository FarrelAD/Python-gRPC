"""Dependency injection and gRPC connection management for the REST Gateway."""

from __future__ import annotations

import grpc
from fastapi import HTTPException

from python_grpc.proto import pzem_004t_pb2_grpc


class GatewayState:
    """Manages the lifecycle of gRPC channel and client stubs."""

    channel: grpc.aio.Channel | None = None
    stub: pzem_004t_pb2_grpc.DeviceTelemetryStub | None = None


state = GatewayState()


def get_telemetry_stub() -> pzem_004t_pb2_grpc.DeviceTelemetryStub:
    """FastAPI dependency yielding the active gRPC telemetry client stub."""
    if state.stub is None:
        raise HTTPException(
            status_code=503,
            detail="gRPC gateway channel unavailable",
        )
    return state.stub
