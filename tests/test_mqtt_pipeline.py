"""Integration test for Embedded MQTT Ingestion in Collector & gRPC Streaming.

Tests the simulated ESP32 MQTT Sensor Node publishing over MQTT,
the Telemetry Collector ingesting readings via its embedded MQTT consumer,
and a gRPC client (such as the REST Gateway or monitoring station)
receiving live telemetry streamed via gRPC Subscribe().
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from typing import Any
from unittest.mock import patch

import grpc
import paho.mqtt.client as mqtt
import pytest

from python_grpc.apps.collector.mqtt_consumer import CollectorMQTTConsumer
from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.apps.mqtt_sensor_node.app import run_sensor_node
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc


@pytest.fixture
async def collector_with_mqtt() -> AsyncGenerator[
    tuple[DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, str]
]:
    server = grpc.aio.server()
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
    try:
        yield servicer, stub, f"127.0.0.1:{port}"
    finally:
        await channel.close()
        await server.stop(grace=0)


async def test_embedded_mqtt_collector_to_grpc_streaming(
    collector_with_mqtt: tuple[
        DeviceTelemetryServicer, pzem_004t_pb2_grpc.DeviceTelemetryStub, str
    ],
) -> None:
    """Verifies that MQTT messages are ingested directly into the Collector and streamed out via gRPC Subscribe."""
    servicer, stub, _target = collector_with_mqtt

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
            msg = mqtt.MQTTMessage(topic=topic.encode("utf-8"))
            msg.payload = payload.encode("utf-8")
            msg.qos = qos
            for _sub_topic, client in subscribers:
                if client.on_message:
                    client.on_message(client, None, msg)
            return mqtt.MQTTMessageInfo(0)

    with patch("paho.mqtt.client.Client", side_effect=MockPahoClient):
        # 1. Start embedded MQTT consumer in the collector
        mqtt_consumer = CollectorMQTTConsumer(
            servicer=servicer,
            broker_host="mock-broker",
            broker_port=1883,
        )
        mqtt_consumer.start()

        # 2. Open gRPC live subscriber stream (simulating REST Gateway / dashboard)
        received_over_grpc: list[pzem_004t_pb2.ReadingReport] = []

        async def _grpc_subscriber() -> None:
            call = stub.Subscribe(pzem_004t_pb2.SubscribeRequest(device_id="*"))
            async for reading in call:
                received_over_grpc.append(reading)
                if len(received_over_grpc) == 2:
                    call.cancel()
                    break

        subscriber_task = asyncio.create_task(_grpc_subscriber())
        await asyncio.sleep(0.05)

        # 3. Run simulated ESP32 sensor node publishing over MQTT
        loop = asyncio.get_running_loop()
        sensor_task = loop.run_in_executor(
            None,
            run_sensor_node,
            "mock-broker",
            1883,
            "ESP32-EMBEDDED-01",
            "devices",
            0.01,
            2,
        )

        await asyncio.gather(subscriber_task, sensor_task)
        mqtt_consumer.stop()

    # 4. Assert both readings were ingested by the servicer
    assert len(servicer.readings) == 2
    assert servicer.readings[0].device_id == "ESP32-EMBEDDED-01"

    # 5. Assert readings were streamed over gRPC in real time to the subscriber
    assert len(received_over_grpc) == 2
    assert received_over_grpc[0].device_id == "ESP32-EMBEDDED-01"
    assert received_over_grpc[0].voltage > 0.0
    assert received_over_grpc[1].voltage > 0.0
