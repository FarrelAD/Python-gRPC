"""Pydantic data validation schemas for the REST-to-gRPC Gateway."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
