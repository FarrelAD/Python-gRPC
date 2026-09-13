"""CLI entry point for running the REST-to-gRPC FastAPI Gateway."""

from __future__ import annotations

import argparse
import os
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="PZEM-004t REST-to-gRPC Gateway Service")
    parser.add_argument("--host", default=os.getenv("GATEWAY_HOST", "0.0.0.0"), help="Host to bind")
    parser.add_argument("--port", type=int, default=int(os.getenv("GATEWAY_PORT", "8000")), help="Port to bind")
    parser.add_argument("--grpc-target", default=os.getenv("GRPC_TARGET", "localhost:50051"), help="Target gRPC server")
    args = parser.parse_args()

    os.environ["GRPC_TARGET"] = args.grpc_target
    print(f"Starting REST-to-gRPC Gateway on http://{args.host}:{args.port} -> gRPC {args.grpc_target}")
    uvicorn.run("python_grpc.gateway.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
