"""End-to-end tests for all four gRPC call types using a real (local) server."""

from __future__ import annotations

import unittest
from typing import override

import grpc

from python_grpc.device import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc
from python_grpc.server import DeviceTelemetryServicer


class TelemetryTestCase(unittest.IsolatedAsyncioTestCase):
    @override
    async def asyncSetUp(self) -> None:
        self.server = grpc.aio.server()
        self.servicer = DeviceTelemetryServicer()
        pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(self.servicer, self.server)
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()
        self.channel = grpc.aio.insecure_channel(f"localhost:{port}")
        self.stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(self.channel)
        self.device = PZEM004TDevice(seed=42)

    @override
    async def asyncTearDown(self) -> None:
        await self.channel.close()
        await self.server.stop(grace=0)


class TestReportReading(TelemetryTestCase):
    async def test_valid_reading_is_acknowledged_and_stored(self) -> None:
        ack = await self.stub.ReportReading(self.device.read())
        self.assertTrue(ack.success)
        self.assertIn(self.device.device_id, ack.message)
        self.assertGreater(ack.received_at_unix_ms, 0)
        self.assertEqual(len(self.servicer.readings), 1)

    async def test_invalid_reading_is_rejected(self) -> None:
        report = self.device.read()
        report.voltage = 0.0
        ack = await self.stub.ReportReading(report)
        self.assertFalse(ack.success)
        self.assertEqual(len(self.servicer.readings), 0)


class TestReportReadings(TelemetryTestCase):
    async def test_batch_upload_produces_summary(self) -> None:
        async def readings():
            for _ in range(10):
                yield self.device.read()
            bad_voltage = self.device.read()
            bad_voltage.voltage = 9999.0
            yield bad_voltage
            no_id = self.device.read()
            no_id.device_id = ""
            yield no_id

        summary = await self.stub.ReportReadings(readings())
        self.assertEqual(summary.received, 10)
        self.assertEqual(summary.rejected, 2)
        self.assertGreater(summary.avg_active_power, 0.0)
        self.assertEqual(len(self.servicer.readings), 10)


class TestSubscribe(TelemetryTestCase):
    async def test_streams_live_readings_for_device(self) -> None:
        request = pzem_004t_pb2.SubscribeRequest(device_id=self.device.device_id)
        received: list[pzem_004t_pb2.ReadingReport] = []
        async for report in self.stub.Subscribe(request):
            received.append(report)
            if len(received) == 3:
                break
        self.assertEqual(len(received), 3)
        for report in received:
            self.assertEqual(report.device_id, self.device.device_id)
            self.assertGreater(report.voltage, 0.0)
            self.assertGreater(report.frequency, 0.0)


class TestStreamTelemetry(TelemetryTestCase):
    async def test_every_reading_gets_an_ack(self) -> None:
        async def readings():
            for _ in range(5):
                yield self.device.read()

        acks: list[pzem_004t_pb2.Ack] = []
        async for ack in self.stub.StreamTelemetry(readings()):
            acks.append(ack)
        self.assertEqual(len(acks), 5)
        self.assertTrue(all(a.success for a in acks))
        self.assertEqual(len(self.servicer.readings), 5)


if __name__ == "__main__":
    unittest.main()
