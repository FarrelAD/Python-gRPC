"""Shared constants, channel helpers, and configuration."""

from __future__ import annotations

from typing import Any

# Production HTTP/2 channel options for keepalive and resiliency
DEFAULT_GRPC_CHANNEL_OPTIONS: list[tuple[str, Any]] = [
    ("grpc.keepalive_time_ms", 30000),             # Send keepalive ping every 30s
    ("grpc.keepalive_timeout_ms", 10000),          # Keepalive ping timeout 10s
    ("grpc.keepalive_permit_without_calls", 1),    # Allow pings even when no active RPC calls
    ("grpc.http2.max_pings_without_data", 0),      # Unlimited pings without data
    ("grpc.http2.min_time_between_pings_ms", 10000),
    ("grpc.http2.min_ping_interval_without_data_ms", 5000),
]
