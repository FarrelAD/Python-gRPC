"""MQTT-to-gRPC Bridge service.

Subscribes to sensor telemetry topics on an MQTT broker using paho-mqtt
and bridges them into the central Telemetry Collector via high-performance gRPC.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os

import grpc
import paho.mqtt.client as mqtt

from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import RequestIdClientInterceptor
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

logger = logging.getLogger("mqtt_grpc_bridge")


async def bridge_mqtt_to_grpc(
    mqtt_host: str,
    mqtt_port: int,
    grpc_target: str,
    topic: str = "devices/+/telemetry",
    stop_after_count: int = 0,
) -> None:
    """Subscribe to MQTT topic pattern via paho-mqtt and forward payloads into gRPC."""
    logger.info(
        "Starting MQTT-to-gRPC Bridge (paho-mqtt): MQTT %s:%d (topic=%r) -> gRPC %s",
        mqtt_host,
        mqtt_port,
        topic,
        grpc_target,
    )

    channel = grpc.aio.insecure_channel(
        grpc_target,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
        interceptors=[RequestIdClientInterceptor(client_version="mqtt-bridge-1.0")],
    )
    stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)

    loop = asyncio.get_running_loop()
    msg_queue: asyncio.Queue[pzem_004t_pb2.ReadingReport] = asyncio.Queue()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        rc: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        if rc.is_failure:
            logger.error("Failed to connect to MQTT broker: %s", rc)
            return
        logger.info("Connected to MQTT broker. Subscribing to %s...", topic)
        client.subscribe(topic)

    def on_message(
        client: mqtt.Client,
        userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            reading = pzem_004t_pb2.ReadingReport(
                device_id=payload.get("device_id", "UNKNOWN"),
                device_type=payload.get("device_type", "PZEM-004T"),
                timestamp_unix_ms=payload.get("timestamp_unix_ms", 0),
                voltage=float(payload.get("voltage", 0.0)),
                current=float(payload.get("current", 0.0)),
                active_power=float(payload.get("active_power", 0.0)),
                energy=float(payload.get("energy", 0.0)),
                frequency=float(payload.get("frequency", 50.0)),
                power_factor=float(payload.get("power_factor", 1.0)),
            )
            loop.call_soon_threadsafe(msg_queue.put_nowait, reading)
        except (json.JSONDecodeError, KeyError, ValueError) as err:
            logger.warning("Failed to parse MQTT message payload: %s", err)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(mqtt_host, mqtt_port, keepalive=60)
    client.loop_start()

    forwarded = 0
    try:
        while True:
            reading = await msg_queue.get()
            try:
                ack = await stub.ReportReading(reading, timeout=5.0)
                forwarded += 1
                logger.info(
                    "[%d] Forwarded MQTT msg from %s to gRPC: %s",
                    forwarded,
                    reading.device_id,
                    ack.message,
                )
            except grpc.RpcError as rpc_err:
                logger.error("gRPC forward failed: %s", rpc_err.details())

            if 0 < stop_after_count <= forwarded:
                logger.info(
                    "Reached stop count %d, exiting bridge loop.", stop_after_count
                )
                break
    finally:
        client.loop_stop()
        client.disconnect()
        await channel.close()
        logger.info("Bridge gRPC channel and MQTT client closed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MQTT-to-gRPC Telemetry Ingestion Bridge (paho-mqtt)"
    )
    parser.add_argument(
        "--mqtt-host",
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="MQTT broker host",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--grpc-target",
        default=os.getenv("GRPC_TARGET", "localhost:50051"),
        help="Target gRPC Telemetry Collector address",
    )
    parser.add_argument(
        "--topic",
        default=os.getenv("MQTT_TOPIC", "devices/+/telemetry"),
        help="MQTT topic filter to subscribe to",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.getenv("COUNT", "0")),
        help="Stop after forwarding N messages (0 for continuous)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        asyncio.run(
            bridge_mqtt_to_grpc(
                mqtt_host=args.mqtt_host,
                mqtt_port=args.mqtt_port,
                grpc_target=args.grpc_target,
                topic=args.topic,
                stop_after_count=args.count,
            )
        )
    except KeyboardInterrupt:
        logger.info("Bridge stopped by user.")


if __name__ == "__main__":
    main()
