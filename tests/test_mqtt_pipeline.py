"""Integration test for MQTT-to-gRPC Ingestion Pipeline.

Tests the simulated ESP32 MQTT Sensor Node publishing over MQTT,
the MQTT-to-gRPC Bridge receiving and transforming to Protobuf,
and the gRPC Telemetry Collector receiving and acknowledging the readings.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any
from unittest.mock import patch

import grpc
import paho.mqtt.client as mqtt
import pytest

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.apps.mqtt_bridge.app import bridge_mqtt_to_grpc
from python_grpc.apps.mqtt_sensor_node.app import run_sensor_node
from python_grpc.proto import pzem_004t_pb2_grpc


@pytest.fixture
async def ephemeral_grpc_collector() -> AsyncGenerator[
    tuple[DeviceTelemetryServicer, str]
]:
    server = grpc.aio.server()
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield servicer, f"127.0.0.1:{port}"
    finally:
        await server.stop(grace=0)


async def test_mqtt_bridge_to_grpc_collector_pipeline(
    ephemeral_grpc_collector: tuple[DeviceTelemetryServicer, str],
) -> None:
    """Verifies MQTT messages correctly convert to ReadingReport and get stored in gRPC servicer."""
    servicer, grpc_target = ephemeral_grpc_collector

    # Registered mock clients across the test
    subscribers: list[tuple[str, Any]] = []

    class MockPahoClient:
        on_connect: Callable[..., None] | None
        on_message: Callable[..., None] | None

        def __init__(self, callback_api_version: mqtt.CallbackAPIVersion) -> None:
            self.callback_api_version = callback_api_version
            self.on_connect = None
            self.on_message = None
            self._is_connected = False

        def connect(self, host: str, port: int, keepalive: int = 60) -> int:
            self._is_connected = True
            if self.on_connect:
                # Trigger successful connection callback (VERSION2 signature)
                flags = mqtt.ConnectFlags(session_present=False)
                rc = mqtt.ReasonCode(mqtt.PacketTypes.CONNACK, "Success")
                self.on_connect(self, None, flags, rc, None)
            return 0

        def loop_start(self) -> int:
            return 0

        def loop_stop(self) -> int:
            return 0

        def disconnect(self) -> int:
            self._is_connected = False
            return 0

        def subscribe(self, topic: str) -> tuple[int, int]:
            subscribers.append((topic, self))
            return 0, 1

        def publish(
            self, topic: str, payload: str, qos: int = 1
        ) -> mqtt.MQTTMessageInfo:
            # Deliver message to subscribers
            msg = mqtt.MQTTMessage(topic=topic.encode("utf-8"))
            msg.payload = payload.encode("utf-8")
            msg.qos = qos
            for _sub_topic, client in subscribers:
                if client.on_message:
                    client.on_message(client, None, msg)
            return mqtt.MQTTMessageInfo(0)

    with patch("paho.mqtt.client.Client", side_effect=MockPahoClient):
        # 1. Run bridge in background (stop after forwarding 2 messages)
        bridge_task = asyncio.create_task(
            bridge_mqtt_to_grpc(
                mqtt_host="mock-broker",
                mqtt_port=1883,
                grpc_target=grpc_target,
                stop_after_count=2,
            )
        )

        # Allow bridge to start and subscribe
        await asyncio.sleep(0.05)

        # 2. Run simulated sensor node in a background thread because run_sensor_node is synchronous
        loop = asyncio.get_running_loop()
        sensor_task = loop.run_in_executor(
            None,
            run_sensor_node,
            "mock-broker",
            1883,
            "ESP32-UNIT-TEST",
            "devices",
            0.01,
            2,
        )

        await asyncio.gather(bridge_task, sensor_task)

    # 3. Assert gRPC collector received both readings
    assert len(servicer.readings) == 2
    assert servicer.readings[0].device_id == "ESP32-UNIT-TEST"
    assert servicer.readings[1].device_id == "ESP32-UNIT-TEST"
    assert servicer.readings[0].voltage > 0.0
    assert servicer.readings[0].current > 0.0
