"""Collector application package."""

from python_grpc.apps.collector.app import main, serve
from python_grpc.apps.collector.servicer import DeviceTelemetryServicer

__all__ = ["main", "serve", "DeviceTelemetryServicer"]
