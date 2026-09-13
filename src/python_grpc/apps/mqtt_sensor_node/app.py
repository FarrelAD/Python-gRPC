"""Simulated Microcontroller (ESP32) reading PZEM-004T and publishing over MQTT."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time

import paho.mqtt.client as mqtt

from python_grpc.core.device.pzem_004t import PZEM004TDevice

logger = logging.getLogger("mqtt_sensor_node")


def run_sensor_node(
    broker_host: str,
    broker_port: int,
    device_id: str,
    topic_prefix: str = "devices",
    interval_s: float = 1.0,
    count: int = 0,
) -> None:
    """Read sensor data from PZEM-004T and publish as JSON over MQTT using standard paho-mqtt."""
    sensor = PZEM004TDevice(device_id=device_id, read_interval_s=interval_s)
    topic = f"{topic_prefix}/{device_id}/telemetry"

    logger.info(
        "Connecting to MQTT broker %s:%d to publish on topic %s",
        broker_host,
        broker_port,
        topic,
    )

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
        else:
            logger.info("Connected to MQTT broker successfully.")

    client.on_connect = on_connect

    try:
        client.connect(broker_host, broker_port, keepalive=60)
        client.loop_start()

        published = 0
        while True:
            reading = sensor.read()
            payload = {
                "device_id": reading.device_id,
                "device_type": reading.device_type,
                "timestamp_unix_ms": reading.timestamp_unix_ms,
                "voltage": reading.voltage,
                "current": reading.current,
                "active_power": reading.active_power,
                "energy": reading.energy,
                "frequency": reading.frequency,
                "power_factor": reading.power_factor,
            }
            raw_payload = json.dumps(payload)
            client.publish(topic, payload=raw_payload, qos=1)
            published += 1
            logger.info(
                "[%d] Published to %s: V=%.1fV I=%.2fA P=%.1fW",
                published,
                topic,
                reading.voltage,
                reading.current,
                reading.active_power,
            )

            if 0 < count <= published:
                logger.info("Published requested count (%d), stopping.", count)
                break

            time.sleep(interval_s)
    finally:
        client.loop_stop()
        client.disconnect()
        logger.info("Disconnected from MQTT broker.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulated ESP32 + PZEM-004T MQTT Sensor Node (paho-mqtt)"
    )
    parser.add_argument(
        "--broker-host",
        default=os.getenv("MQTT_BROKER_HOST", "localhost"),
        help="MQTT broker host",
    )
    parser.add_argument(
        "--broker-port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--device-id",
        default=os.getenv("DEVICE_ID", "ESP32-PZEM-01"),
        help="Device ID identifier",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("READ_INTERVAL_S", "1.0")),
        help="Publishing interval in seconds",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=int(os.getenv("COUNT", "0")),
        help="Number of readings to publish (0 for continuous)",
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
        run_sensor_node(
            broker_host=args.broker_host,
            broker_port=args.broker_port,
            device_id=args.device_id,
            interval_s=args.interval,
            count=args.count,
        )
    except KeyboardInterrupt:
        logger.info("Sensor node interrupted by user.")


if __name__ == "__main__":
    main()
