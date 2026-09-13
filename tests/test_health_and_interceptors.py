"""Integration tests for standard gRPC health checks and interceptors."""

# pyrefly: ignore-errors[missing-attribute]

from __future__ import annotations

import unittest
from typing import override

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from python_grpc.common.interceptors import RequestIdClientInterceptor, ServerLoggingAndRecoveryInterceptor
from python_grpc.device import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2_grpc
from python_grpc.server import DeviceTelemetryServicer


class TestHealthAndInterceptors(unittest.IsolatedAsyncioTestCase):
    @override
    async def asyncSetUp(self) -> None:
        self.server = grpc.aio.server(interceptors=[ServerLoggingAndRecoveryInterceptor()])
        self.servicer = DeviceTelemetryServicer()
        self.health_servicer = health.HealthServicer()

        pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(self.servicer, self.server)
        health_pb2_grpc.add_HealthServicer_to_server(self.health_servicer, self.server)

        self.service_name = pzem_004t_pb2_grpc.DeviceTelemetryServicer.__name__
        self.health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
        self.health_servicer.set(self.service_name, health_pb2.HealthCheckResponse.SERVING)

        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()

        self.channel = grpc.aio.insecure_channel(
            f"localhost:{port}",
            interceptors=[RequestIdClientInterceptor(client_version="test-1.0")],
        )
        self.stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(self.channel)
        self.health_stub = health_pb2_grpc.HealthStub(self.channel)
        self.device = PZEM004TDevice(seed=99)

    @override
    async def asyncTearDown(self) -> None:
        await self.channel.close()
        await self.server.stop(grace=0)

    async def test_health_check_returns_serving(self) -> None:
        res = await self.health_stub.Check(health_pb2.HealthCheckRequest(service=self.service_name))
        self.assertEqual(res.status, health_pb2.HealthCheckResponse.SERVING)

    async def test_health_check_unknown_service_returns_not_found(self) -> None:
        with self.assertRaises(grpc.aio.AioRpcError) as ctx:
            await self.health_stub.Check(health_pb2.HealthCheckRequest(service="non.existent.Service"))
        self.assertEqual(ctx.exception.code(), grpc.StatusCode.NOT_FOUND)

    async def test_unary_call_with_client_and_server_interceptors(self) -> None:
        ack = await self.stub.ReportReading(self.device.read())
        self.assertTrue(ack.success)
        self.assertEqual(len(self.servicer.readings), 1)


if __name__ == "__main__":
    unittest.main()
