"""Generate gRPC stubs from the pzem_004t.proto definition.

Run from the repository root (or via `poetry run python scripts/gen_proto.py`).
Writes pzem_004t_pb2.py / pzem_004t_pb2_grpc.py / .pyi next to the proto.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PROTO = SRC / "python_grpc" / "proto" / "pzem_004t.proto"


def main() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={SRC}",
            f"--python_out={SRC}",
            f"--pyi_out={SRC}",
            f"--grpc_python_out={SRC}",
            str(PROTO),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    print("Generated stubs for", PROTO.name, "->", SRC / "python_grpc" / "proto")


if __name__ == "__main__":
    main()
