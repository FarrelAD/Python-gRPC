"""Async gRPC telemetry collector application bootstrap."""

from __future__ import annotations

import asyncio
import logging

import grpc

from python_grpc.proto import pzem_004t_pb2_grpc
from python_grpc.server.servicer import DeviceTelemetryServicer


async def serve(host: str = "[::]", port: int = 50051) -> None:
    server = grpc.aio.server()
    servicer = DeviceTelemetryServicer()
    pzem_004t_pb2_grpc.add_DeviceTelemetryServicer_to_server(servicer, server)
    listen_addr = f"{host}:{port}"
    server.add_insecure_port(listen_addr)
    await server.start()
    print(f"PZEM-004t collector listening on {listen_addr}")
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(serve())
