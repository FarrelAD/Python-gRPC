"""Routers package for the REST Gateway."""

from __future__ import annotations

from python_grpc.apps.rest_gateway.routers.health import router as health_router
from python_grpc.apps.rest_gateway.routers.telemetry import router as telemetry_router

__all__ = ["health_router", "telemetry_router"]
