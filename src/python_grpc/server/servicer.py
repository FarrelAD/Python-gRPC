"""gRPC servicer implementing the DeviceTelemetry service.

Implements all four gRPC call types:
  - ReportReading     : unary-unary           (single reading -> ack)
  - ReportReadings    : client-streaming      (batch upload -> summary)
  - Subscribe         : server-streaming      (live readings pushed out)
  - StreamTelemetry   : bidi-streaming        (continuous two-way exchange)
"""

from __future__ import annotations

import asyncio
import logging
import time

import grpc

from python_grpc.device import PZEM004TDevice
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
    def __init__(self) -> None:
        self._readings: list[pzem_004t_pb2.ReadingReport] = []

    @property
    def readings(self) -> list[pzem_004t_pb2.ReadingReport]:
        return self._readings

    async def ReportReading(
        self,
        request: pzem_004t_pb2.ReadingReport,
        context: grpc.aio.ServicerContext,
    ) -> pzem_004t_pb2.Ack:
        if not _is_valid(request):
            return _ack(False, f"rejected invalid reading from {request.device_id}")
        self._readings.append(request)
        logger.info(
            "ReportReading device=%s v=%.1fV i=%.2fA p=%.1fW",
            request.device_id,
            request.voltage,
            request.current,
            request.active_power,
        )
        return _ack(True, f"stored reading #{len(self._readings)} from {request.device_id}")

    async def ReportReadings(
        self,
        request_iterator: grpc.aio.AsyncIterable[pzem_004t_pb2.ReadingReport],
        context: grpc.aio.ServicerContext,
    ) -> pzem_004t_pb2.BatchSummary:
        received = 0
        rejected = 0
        total_power = 0.0
        async for report in request_iterator:
            if _is_valid(report):
                self._readings.append(report)
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

    async def Subscribe(
        self,
        request: pzem_004t_pb2.SubscribeRequest,
        context: grpc.aio.ServicerContext,
    ):
        device_id = request.device_id or "PZEM-004T-LIVE"
        device = PZEM004TDevice(device_id=device_id)
        logger.info("Subscribe device=%s connected", device_id)
        try:
            while True:
                yield device.read()
                await asyncio.sleep(1.0)
        except (asyncio.CancelledError, grpc.RpcError):
            logger.info("Subscribe device=%s disconnected", device_id)

    async def StreamTelemetry(
        self,
        request_iterator: grpc.aio.AsyncIterable[pzem_004t_pb2.ReadingReport],
        context: grpc.aio.ServicerContext,
    ):
        async for report in request_iterator:
            if _is_valid(report):
                self._readings.append(report)
                yield _ack(True, f"stored reading from {report.device_id}")
            else:
                yield _ack(False, f"rejected invalid reading from {report.device_id}")
