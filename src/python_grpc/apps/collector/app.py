"""Async gRPC telemetry collector application bootstrap with custom interceptors,

health checking, and graceful shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from typing import Any

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from python_grpc.apps.collector.mqtt_consumer import CollectorMQTTConsumer
from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import ServerLoggingAndRecoveryInterceptor
from python_grpc.proto import pzem_004t_pb2_grpc

logger = logging.getLogger("telemetry_collector_server")


async def serve(
    host: str = "0.0.0.0",
    port: int = 50051,
    mqtt_host: str | None = None,
    mqtt_port: int = 1883,
    mqtt_topic: str = "devices/+/telemetry",
) -> None:
    # 1. Initialize server with channel options and interceptors
    interceptors = [ServerLoggingAndRecoveryInterceptor()]
    server = grpc.aio.server(
        interceptors=interceptors,
        options=DEFAULT_GRPC_CHANNEL_OPTIONS,
    )

    # 2. Register main business servicer
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)

    # 3. Register standard gRPC Health Servicer (grpc.health.v1)
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Mark services as SERVING
    service_name = pzem_004t_pb2_grpc.DeviceTelemetryServicer.__name__
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)

    listen_addr = f"{host}:{port}"
    server.add_insecure_port(listen_addr)
    await server.start()
    logger.info("Collector service started on %s (Health check enabled)", listen_addr)

    # 4. Start embedded MQTT consumer if host is configured
    mqtt_consumer: CollectorMQTTConsumer | None = None
    if mqtt_host:
        mqtt_consumer = CollectorMQTTConsumer(
            servicer=servicer,
            broker_host=mqtt_host,
            broker_port=mqtt_port,
            topic=mqtt_topic,
        )
        mqtt_consumer.start()

    # 5. Graceful shutdown handling
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _trigger_stop(*args: Any) -> None:
        logger.info("Shutdown signal received, initiating graceful termination...")
        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        health_servicer.set(service_name, health_pb2.HealthCheckResponse.NOT_SERVING)
        stop_event.set()

    # On Windows, add_signal_handler is limited, so we handle OS signals if supported
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _trigger_stop)
    except (NotImplementedError, AttributeError):
        # Fallback for Windows event loops
        pass

    try:
        # Wait either for stop event or termination
        server_task = asyncio.create_task(server.wait_for_termination())
        stop_task = asyncio.create_task(stop_event.wait())

        done, pending = await asyncio.wait(
            [server_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        if mqtt_consumer is not None:
            mqtt_consumer.stop()
        logger.info("Stopping gRPC server with 5s grace period...")
        await server.stop(grace=5.0)
        logger.info("Collector service stopped cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PZEM-004t gRPC Telemetry Collector Service"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("COLLECTOR_HOST", "0.0.0.0"),
        help="Host address to bind to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("COLLECTOR_PORT", "50051")),
        help="Port to listen on",
    )
    parser.add_argument(
        "--mqtt-host",
        default=os.getenv("MQTT_BROKER_HOST", None),
        help="Optional MQTT broker host to subscribe to sensor readings",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        help="MQTT broker port",
    )
    parser.add_argument(
        "--mqtt-topic",
        default=os.getenv("MQTT_TOPIC", "devices/+/telemetry"),
        help="MQTT topic filter to subscribe to",
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
            serve(
                host=args.host,
                port=args.port,
                mqtt_host=args.mqtt_host,
                mqtt_port=args.mqtt_port,
                mqtt_topic=args.mqtt_topic,
            )
        )
    except KeyboardInterrupt:
        logger.info("Application interrupted by user.")


if __name__ == "__main__":
    main()
