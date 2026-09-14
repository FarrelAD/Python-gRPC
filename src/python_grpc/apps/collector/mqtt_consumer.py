"""Embedded MQTT consumer for the Telemetry Collector application.

Subscribes to telemetry topics on an MQTT broker and directly feeds received
PZEM-004T readings into the collector servicer and its pub/sub broadcast hub.
"""

from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.proto import pzem_004t_pb2

logger = logging.getLogger("collector_mqtt_consumer")


class CollectorMQTTConsumer:
    """Manages an embedded MQTT subscriber client feeding readings directly into servicer."""

    def __init__(
        self,
        servicer: DeviceTelemetryServicer,
        broker_host: str,
        broker_port: int = 1883,
        topic: str = "devices/+/telemetry",
    ) -> None:
        self.servicer = servicer
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self._client: mqtt.Client | None = None

    def start(self) -> None:
        """Connect to the MQTT broker and start background listening."""
        logger.info(
            "Starting embedded MQTT consumer: %s:%d (topic=%r)",
            self.broker_host,
            self.broker_port,
            self.topic,
        )
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

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
            logger.info("Connected to MQTT broker. Subscribing to %s...", self.topic)
            client.subscribe(self.topic)

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
                ack = self.servicer.ingest_reading(reading)
                logger.debug("MQTT reading ingested: %s", ack.message)
            except (json.JSONDecodeError, KeyError, ValueError) as err:
                logger.warning("Failed to parse MQTT message payload: %s", err)

        self._client.on_connect = on_connect
        self._client.on_message = on_message

        try:
            self._client.connect(self.broker_host, self.broker_port, keepalive=60)
            self._client.loop_start()
            logger.info("Embedded MQTT consumer loop started.")
        except Exception as exc:
            logger.warning(
                "Could not connect to MQTT broker at %s:%d (%s). Operating in gRPC-only mode.",
                self.broker_host,
                self.broker_port,
                exc,
            )

    def stop(self) -> None:
        """Cleanly stop MQTT client loop and disconnect."""
        if self._client is not None:
            logger.info("Stopping embedded MQTT consumer...")
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            logger.info("Embedded MQTT consumer stopped.")
