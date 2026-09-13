"""FastAPI REST Gateway exposing HTTP endpoints that proxy to the gRPC Telemetry Collector."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import grpc
from fastapi import FastAPI

from python_grpc.apps.rest_gateway.config import GRPC_TARGET
from python_grpc.apps.rest_gateway.dependencies import GatewayState, state
from python_grpc.apps.rest_gateway.routers import health_router, telemetry_router
from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import RequestIdClientInterceptor
from python_grpc.proto import pzem_004t_pb2_grpc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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


def create_app() -> FastAPI:
    """Factory creating and configuring the FastAPI Gateway application."""
    application = FastAPI(
        title="PZEM-004t REST-to-gRPC Gateway",
        description="Demonstrates REST API consumers communicating with internal gRPC microservices.",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(telemetry_router)
    return application


app = create_app()

__all__ = ["GatewayState", "app", "create_app", "lifespan", "state"]
