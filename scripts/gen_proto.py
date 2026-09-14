"""Generate gRPC stubs from all .proto definitions in the repository.

Run from the repository root:
    poetry run python scripts/gen_proto.py

Automatically discovers all `*.proto` files located in `src/python_grpc/proto/`
and compiles them into:
    - `*_pb2.py` (Protobuf message classes)
    - `*_pb2.pyi` (Protobuf type stubs)
    - `*_pb2_grpc.py` (gRPC client & servicer classes)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PROTO_DIR = SRC / "python_grpc" / "proto"


def main() -> None:
    if not PROTO_DIR.exists():
        print(f"Error: Proto directory '{PROTO_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    proto_files = sorted(PROTO_DIR.glob("*.proto"))
    if not proto_files:
        print(f"No .proto files found in {PROTO_DIR}", file=sys.stderr)
        return

    print(f"Discovered {len(proto_files)} .proto file(s) in {PROTO_DIR}:")
    for proto in proto_files:
        print(f"  - {proto.name}")

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={SRC}",
        f"--python_out={SRC}",
        f"--pyi_out={SRC}",
        f"--grpc_python_out={SRC}",
        *[str(p) for p in proto_files],
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Protoc compilation failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)

    print("\nSuccessfully compiled all proto definitions into Python stubs.")


if __name__ == "__main__":
    main()
