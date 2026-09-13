"""Configuration settings for the REST-to-gRPC Gateway service."""

from __future__ import annotations

import os

GRPC_TARGET: str = os.getenv("GRPC_TARGET", "localhost:50051")
GATEWAY_HOST: str = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
