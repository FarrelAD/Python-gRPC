"""Integration test for FastAPI REST-to-gRPC Gateway."""

from __future__ import annotations

import unittest
from typing import override

import httpx
import grpc

from python_grpc.gateway.app import app, state
from python_grpc.proto import pzem_004t_pb2_grpc
from python_grpc.server import DeviceTelemetryServicer


class TestRestGateway(unittest.IsolatedAsyncioTestCase):
    @override
    async def asyncSetUp(self) -> None:
        self.server = grpc.aio.server()
        self.servicer = DeviceTelemetryServicer()
        pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(self.servicer, self.server)
        port = self.server.add_insecure_port("127.0.0.1:0")
        await self.server.start()

        # Connect gateway state directly to ephemeral server
        state.channel = grpc.aio.insecure_channel(f"localhost:{port}")
        state.stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(state.channel)

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    @override
    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        if state.channel is not None:
            await state.channel.close()
        await self.server.stop(grace=0)

    async def test_gateway_unary_post(self) -> None:
        payload = {
            "device_id": "REST-DEVICE-01",
            "device_type": "PZEM-004T",
            "voltage": 230.5,
            "current": 2.1,
            "active_power": 484.05,
            "energy": 1.25,
            "frequency": 50.0,
            "power_factor": 0.99,
        }
        response = await self.client.post("/api/v1/telemetry", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("REST-DEVICE-01", data["message"])
        self.assertEqual(len(self.servicer.readings), 1)

    async def test_gateway_batch_post(self) -> None:
        readings = [
            {
                "device_id": f"REST-DEVICE-{i}",
                "device_type": "PZEM-004T",
                "voltage": 230.0,
                "current": 1.5,
                "active_power": 345.0,
                "energy": 0.5,
                "frequency": 50.0,
                "power_factor": 1.0,
            }
            for i in range(3)
        ]
        response = await self.client.post("/api/v1/telemetry/batch", json=readings)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["received"], 3)
        self.assertEqual(data["rejected"], 0)
        self.assertEqual(len(self.servicer.readings), 3)


if __name__ == "__main__":
    unittest.main()
