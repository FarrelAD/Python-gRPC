"""Shared gRPC interceptors for telemetry microservices."""

# pyrefly: ignore-errors[bad-override, missing-override-decorator, direct-abstract-base-instantiation, bad-argument-type, implicit-any-empty-container]

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import grpc
from grpc.aio import (
    ClientCallDetails,
    ServerInterceptor,
    UnaryStreamClientInterceptor,
    UnaryUnaryClientInterceptor,
)

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"
CLIENT_VERSION_HEADER = "x-client-version"


class RequestIdClientInterceptor(
    UnaryUnaryClientInterceptor, UnaryStreamClientInterceptor
):
    """Injects a unique request-id header into outgoing gRPC calls if not already present."""

    def __init__(self, client_version: str = "1.0.0") -> None:
        self.client_version = client_version

    def _inject_metadata(
        self, client_call_details: ClientCallDetails
    ) -> ClientCallDetails:
        metadata = list(client_call_details.metadata or [])
        has_req_id = any(k == REQUEST_ID_HEADER for k, _ in metadata)
        if not has_req_id:
            metadata.append((REQUEST_ID_HEADER, str(uuid.uuid4())))
        metadata.append((CLIENT_VERSION_HEADER, self.client_version))

        return ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

    async def intercept_unary_unary(
        self,
        continuation: Callable[[ClientCallDetails, Any], Awaitable[Any]],
        client_call_details: ClientCallDetails,
        request: Any,
    ) -> Any:
        new_details = self._inject_metadata(client_call_details)
        return await continuation(new_details, request)

    async def intercept_unary_stream(
        self,
        continuation: Callable[[ClientCallDetails, Any], Awaitable[AsyncIterator[Any]]],
        client_call_details: ClientCallDetails,
        request: Any,
    ) -> AsyncIterator[Any]:
        new_details = self._inject_metadata(client_call_details)
        return await continuation(new_details, request)


class ServerLoggingAndRecoveryInterceptor(ServerInterceptor):
    """Server-side interceptor that logs RPC metrics (method, duration, peer, status)

    and catches unexpected unhandled exceptions, returning standard gRPC status codes.
    """

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[Any]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        # Extract request id
        request_id = "unknown"
        if handler_call_details.invocation_metadata:
            for k, v in handler_call_details.invocation_metadata:
                if k.lower() == REQUEST_ID_HEADER:
                    request_id = str(v)
                    break

        method = handler_call_details.method

        if handler.unary_unary:
            unary_unary_fn = handler.unary_unary

            async def logged_unary_unary(
                request: Any, context: grpc.aio.ServicerContext[Any, Any]
            ) -> Any:
                start = time.perf_counter()
                peer = context.peer()
                try:
                    res_raw = unary_unary_fn(request, context)
                    if hasattr(res_raw, "__await__"):
                        res = await res_raw
                    else:
                        res = res_raw

                    duration_ms = (time.perf_counter() - start) * 1000.0
                    logger.info(
                        "gRPC Unary OK method=%s peer=%s req_id=%s duration=%.2fms",
                        method,
                        peer,
                        request_id,
                        duration_ms,
                    )
                    return res
                except grpc.RpcError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    duration_ms = (time.perf_counter() - start) * 1000.0
                    logger.exception(
                        "gRPC Unary ERROR method=%s peer=%s req_id=%s duration=%.2fms err=%s",
                        method,
                        peer,
                        request_id,
                        duration_ms,
                        exc,
                    )
                    await context.abort(
                        grpc.StatusCode.INTERNAL, f"Internal server error: {exc}"
                    )

            return grpc.unary_unary_rpc_method_handler(
                logged_unary_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler
