"""Cross-host gRPC communication simulator.

Simulates two or more physically separate hosts communicating over gRPC:
  - Host 1 (Cloud Telemetry Collector Server): Runs gRPC server + health checks
  - Host 2 (Remote Subscriber / Dashboard Client): Subscribes to live readings stream
  - Host 3 (Edge IoT Meter Gateway): Pushes periodic telemetry readings over gRPC

Demonstrates that neither host shares memory or Python modules with the others;
communication is 100% over the wire via HTTP/2 and Protobuf.
"""

from __future__ import annotations

import asyncio
import logging

import grpc

from python_grpc.apps.collector.servicer import DeviceTelemetryServicer
from python_grpc.core.common.config import DEFAULT_GRPC_CHANNEL_OPTIONS
from python_grpc.core.common.interceptors import RequestIdClientInterceptor
from python_grpc.core.device.pzem_004t import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
)
logger = logging.getLogger("cross_host_sim")


async def main() -> None:
    print("\n" + "=" * 70)
    print("  SIMULATING MULTI-HOST / MULTI-SERVER gRPC TELEMETRY COMMUNICATON")
    print("=" * 70 + "\n")

    # 1. Spawn Host 1 (Cloud Server)
    server_logger = logging.getLogger("Host1-CloudServer")
    server = grpc.aio.server(options=DEFAULT_GRPC_CHANNEL_OPTIONS)
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)

    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    server_logger.info("Host 1 (Collector) listening on 127.0.0.1:%d", port)

    target = f"127.0.0.1:{port}"

    # 2. Spawn Host 2 (Remote Dashboard / Monitoring Station)
    host2_logger = logging.getLogger("Host2-RemoteMonitor")
    received_readings: list[pzem_004t_pb2.ReadingReport] = []

    async def host2_subscriber() -> None:
        async with grpc.aio.insecure_channel(
            target,
            options=DEFAULT_GRPC_CHANNEL_OPTIONS,
            interceptors=[RequestIdClientInterceptor(client_version="monitor-1.0")],
        ) as channel:
            stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
            host2_logger.info(
                "Host 2 connected. Subscribing to live telemetry for 'PZEM-REMOTE-01'..."
            )
            call = stub.Subscribe(
                pzem_004t_pb2.SubscribeRequest(device_id="PZEM-REMOTE-01")
            )
            try:
                async for reading in call:
                    host2_logger.info(
                        "-> [LIVE EVENT RECEIVED] Host 2 received reading from %s: %.1fV, %.2fA, %.1fW",
                        reading.device_id,
                        reading.voltage,
                        reading.current,
                        reading.active_power,
                    )
                    received_readings.append(reading)
                    if len(received_readings) >= 3:
                        call.cancel()
                        break
            except asyncio.CancelledError:
                pass

    # 3. Spawn Host 3 (Edge IoT Meter Gateway Device)
    host3_logger = logging.getLogger("Host3-IoTEdgeMeter")

    async def host3_edge_device() -> None:
        await asyncio.sleep(0.2)  # Give Host 2 time to establish subscription
        device = PZEM004TDevice(device_id="PZEM-REMOTE-01", seed=123)

        async with grpc.aio.insecure_channel(
            target,
            options=DEFAULT_GRPC_CHANNEL_OPTIONS,
            interceptors=[RequestIdClientInterceptor(client_version="edge-iot-1.0")],
        ) as channel:
            stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
            host3_logger.info("Host 3 connected to Cloud Server at %s", target)

            for i in range(1, 4):
                reading = device.read()
                host3_logger.info(
                    "<- [TRANSMITTING] Host 3 sending Reading #%d (%.1fV, %.2fA)...",
                    i,
                    reading.voltage,
                    reading.current,
                )
                ack = await stub.ReportReading(reading, timeout=5.0)
                host3_logger.info(
                    "<- [ACKNOWLEDGED] Host 3 got server ack: %s", ack.message
                )
                await asyncio.sleep(0.3)

    # Run Host 2 and Host 3 concurrently communicating through Host 1
    t2 = asyncio.create_task(host2_subscriber())
    t3 = asyncio.create_task(host3_edge_device())

    await asyncio.gather(t2, t3)

    print("\n" + "-" * 70)
    print(
        f"  Simulation complete: Host 2 received {len(received_readings)} live packets streamed from Host 3"
    )
    print("-" * 70 + "\n")

    await server.stop(grace=0)


if __name__ == "__main__":
    asyncio.run(main())
