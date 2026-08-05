"""gRPC collector server for the PZEM-004t telemetry demo."""

from python_grpc.server.app import serve
from python_grpc.server.servicer import DeviceTelemetryServicer

__all__ = ["DeviceTelemetryServicer", "serve"]
