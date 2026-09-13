"""gRPC servicer implementing the DeviceTelemetry service.

Implements all four gRPC call types:
  - ReportReading     : unary-unary           (single reading -> ack)
  - ReportReadings    : client-streaming      (batch upload -> summary)
  - Subscribe         : server-streaming      (live readings pushed out via async Pub/Sub)
  - StreamTelemetry   : bidi-streaming        (continuous two-way exchange)

The overrides below intentionally narrow the untyped signatures inherited from
the generated pzem_004t_pb2_grpc.DeviceTelemetryServicer base class, which
pyrefly flags as `bad-override`.
"""

# pyrefly: ignore-errors[bad-override]

from __future__ import annotations

import asyncio
from collections import defaultdict
import logging
import time
from collections.abc import AsyncIterator
from typing import override

import grpc

from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

logger = logging.getLogger(__name__)


def _is_valid(report: pzem_004t_pb2.ReadingReport) -> bool:
    if not report.device_id:
        return False
    if not 0.0 < report.voltage < 1000.0:
        return False
    if not 0.0 <= report.current <= 1000.0:
        return False
    if report.active_power < 0.0:
        return False
    if not 45.0 <= report.frequency <= 65.0:
        return False
    if not 0.0 <= report.power_factor <= 1.0:
        return False
    return True


def _ack(success: bool, message: str) -> pzem_004t_pb2.Ack:
    return pzem_004t_pb2.Ack(
        success=success,
        message=message,
        received_at_unix_ms=int(time.time() * 1000),
    )


class DeviceTelemetryServicer(pzem_004t_pb2_grpc.DeviceTelemetryServicer):
    """Collector servicer completely decoupled from client/device hardware code.

    Manages an internal subscriber hub broadcasting real-time readings pushed by
    reporting edge devices.
    """

    def __init__(self) -> None:
        self._readings: list[pzem_004t_pb2.ReadingReport] = []
        # Pub/Sub registry: device_id -> set of active subscriber asyncio.Queues
        self._subscribers: dict[str, set[asyncio.Queue[pzem_004t_pb2.ReadingReport]]] = defaultdict(set)

    @property
    def readings(self) -> list[pzem_004t_pb2.ReadingReport]:
        return self._readings

    def _broadcast(self, report: pzem_004t_pb2.ReadingReport) -> None:
        """Distribute a live reading to all active subscribers for the device or wildcard."""
        device_subscribers = self._subscribers.get(report.device_id, set())
        wildcard_subscribers = self._subscribers.get("*", set())
        for q in device_subscribers | wildcard_subscribers:
            try:
                q.put_nowait(report)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full, dropping reading for %s", report.device_id)

    @override
    async def ReportReading(
        self,
        request: pzem_004t_pb2.ReadingReport,
        context: grpc.aio.ServicerContext[pzem_004t_pb2.ReadingReport, pzem_004t_pb2.Ack],
    ) -> pzem_004t_pb2.Ack:
        if not _is_valid(request):
            return _ack(False, f"rejected invalid reading from {request.device_id}")
        self._readings.append(request)
        self._broadcast(request)
        logger.info(
            "ReportReading device=%s v=%.1fV i=%.2fA p=%.1fW",
            request.device_id,
            request.voltage,
            request.current,
            request.active_power,
        )
        return _ack(True, f"stored reading #{len(self._readings)} from {request.device_id}")

    @override
    async def ReportReadings(
        self,
        request_iterator: grpc.aio.AsyncIterable[pzem_004t_pb2.ReadingReport],
        context: grpc.aio.ServicerContext[pzem_004t_pb2.ReadingReport, pzem_004t_pb2.BatchSummary],
    ) -> pzem_004t_pb2.BatchSummary:
        received = 0
        rejected = 0
        total_power = 0.0
        async for report in request_iterator:
            if _is_valid(report):
                self._readings.append(report)
                self._broadcast(report)
                received += 1
                total_power += report.active_power
            else:
                rejected += 1
        summary = pzem_004t_pb2.BatchSummary(
            received=received,
            rejected=rejected,
            avg_active_power=round(total_power / received, 3) if received else 0.0,
        )
        logger.info(
            "ReportReadings received=%d rejected=%d avg_power=%.1fW",
            received,
            rejected,
            summary.avg_active_power,
        )
        return summary

    @override
    async def Subscribe(
        self,
        request: pzem_004t_pb2.SubscribeRequest,
        context: grpc.aio.ServicerContext[pzem_004t_pb2.SubscribeRequest, pzem_004t_pb2.ReadingReport],
    ) -> AsyncIterator[pzem_004t_pb2.ReadingReport]:
        target_device = request.device_id or "*"
        q: asyncio.Queue[pzem_004t_pb2.ReadingReport] = asyncio.Queue(maxsize=100)
        self._subscribers[target_device].add(q)
        logger.info("Subscribe: client registered for device=%s", target_device)

        try:
            while True:
                # Wait for next live reading published by reporting devices
                report = await q.get()
                yield report
        except (asyncio.CancelledError, grpc.RpcError):
            logger.info("Subscribe: client disconnected for device=%s", target_device)
        finally:
            self._subscribers[target_device].discard(q)
            if not self._subscribers[target_device]:
                self._subscribers.pop(target_device, None)

    @override
    async def StreamTelemetry(
        self,
        request_iterator: grpc.aio.AsyncIterable[pzem_004t_pb2.ReadingReport],
        context: grpc.aio.ServicerContext[pzem_004t_pb2.ReadingReport, pzem_004t_pb2.Ack],
    ) -> AsyncIterator[pzem_004t_pb2.Ack]:
        async for report in request_iterator:
            if _is_valid(report):
                self._readings.append(report)
                self._broadcast(report)
                yield _ack(True, f"stored reading from {report.device_id}")
            else:
                yield _ack(False, f"rejected invalid reading from {report.device_id}")
