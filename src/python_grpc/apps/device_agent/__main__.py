"""CLI entry point for the PZEM-004t gRPC demo client."""

from __future__ import annotations

import argparse

from python_grpc.apps.device_agent.agent import DEFAULT_TARGET, run


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PZEM-004t gRPC IoT Device Agent")
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
    run(args.target, args.device_id, args.count, set(args.rpc))


if __name__ == "__main__":
    main()
