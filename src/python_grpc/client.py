"""Demo client: a simulated PZEM-004t device pushing telemetry via gRPC.

Exercises all four gRPC call types against the collector server:
  - unary         : ReportReading    (single reading -> ack)
  - client-stream : ReportReadings   (batch upload -> summary)
  - server-stream : Subscribe        (receive live readings)
  - bidi-stream   : StreamTelemetry  (continuous two-way exchange)
"""

from __future__ import annotations

import argparse
import asyncio

import grpc

from python_grpc.device import PZEM004TDevice
from python_grpc.proto import pzem_004t_pb2, pzem_004t_pb2_grpc

DEFAULT_TARGET = "localhost:50051"


def _fmt(report: pzem_004t_pb2.ReadingReport) -> str:
    return (
        f"{report.device_id} U={report.voltage:.1f}V I={report.current:.2f}A "
        f"P={report.active_power:.1f}W E={report.energy:.6f}kWh "
        f"f={report.frequency:.2f}Hz PF={report.power_factor:.3f}"
    )


async def run_unary(stub, device: PZEM004TDevice) -> None:
    ack = await stub.ReportReading(device.read())
    print(f"[unary]    ReportReading  -> success={ack.success} msg={ack.message!r}")


async def run_client_streaming(stub, device: PZEM004TDevice, count: int) -> None:
    async def readings():
        for _ in range(count):
            yield device.read()

    summary = await stub.ReportReadings(readings())
    print(
        f"[client]   ReportReadings -> received={summary.received} "
        f"rejected={summary.rejected} avg_power={summary.avg_active_power:.1f}W"
    )


async def run_server_streaming(stub, device: PZEM004TDevice, count: int) -> None:
    request = pzem_004t_pb2.SubscribeRequest(device_id=device.device_id)
    print(f"[server]   Subscribe      -> live readings for {device.device_id}:")
    call = stub.Subscribe(request)
    i = 0
    async for report in call:
        print(f"           {_fmt(report)}")
        i += 1
        if i >= count:
            call.cancel()
            break


async def run_bidi(stub, device: PZEM004TDevice, count: int) -> None:
    async def readings():
        for _ in range(count):
            yield device.read()

    print(f"[bidi]     StreamTelemetry -> {count} readings sent, acks:")
    async for ack in stub.StreamTelemetry(readings()):
        print(f"           success={ack.success} msg={ack.message!r}")


async def run_demo(
    target: str,
    device_id: str,
    count: int,
    rpcs: set[str],
) -> None:
    device = PZEM004TDevice(device_id=device_id, read_interval_s=1.0)
    async with grpc.aio.insecure_channel(target) as channel:
        stub = pzem_004t_pb2_grpc.DeviceTelemetryStub(channel)
        print(f"Connecting to {target} as {device_id}")
        if "unary" in rpcs:
            await run_unary(stub, device)
        if "client-stream" in rpcs:
            await run_client_streaming(stub, device, count)
        if "server-stream" in rpcs:
            await run_server_streaming(stub, device, count)
        if "bidi" in rpcs:
            await run_bidi(stub, device, count)
        print("Done.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PZEM-004t gRPC demo client")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="server address, e.g. localhost:50051")
    parser.add_argument("--device-id", default="PZEM-004T-0001")
    parser.add_argument("--count", type=int, default=5, help="readings per streaming RPC")
    parser.add_argument(
        "--rpc",
        default=["unary", "client-stream", "server-stream", "bidi"],
        choices=["unary", "client-stream", "server-stream", "bidi"],
        nargs="*",
        help="RPC types to run (default: all)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(run_demo(args.target, args.device_id, args.count, set(args.rpc)))


if __name__ == "__main__":
    main()
