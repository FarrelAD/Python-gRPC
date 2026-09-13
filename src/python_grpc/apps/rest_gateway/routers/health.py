"""Health check endpoints for the REST Gateway."""

from __future__ import annotations

from fastapi import APIRouter

from python_grpc.apps.rest_gateway.config import GRPC_TARGET

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Return health status and configured gRPC target."""
    return {"status": "ok", "grpc_target": GRPC_TARGET}
