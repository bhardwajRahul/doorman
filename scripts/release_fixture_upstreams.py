#!/usr/bin/env python3
"""Deterministic HTTP and gRPC upstreams for the isolated release harness."""

from __future__ import annotations

import json
import os
import signal
import threading
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return

    def send(self, content_type: str, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send(
            "application/json",
            json.dumps({"ok": True, "protocol": "rest", "path": self.path}).encode(),
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        size = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(size) if size else b""
        if self.path.endswith("/graphql"):
            self.send(
                "application/json",
                json.dumps({"data": {"hello": "Hello, Doorman!"}}).encode(),
            )
        elif self.path.endswith("/soap"):
            self.send(
                "text/xml; charset=utf-8",
                b'<?xml version="1.0"?><Envelope><Body><ok>true</ok></Body></Envelope>',
            )
        else:
            self.send(
                "application/json",
                json.dumps(
                    {
                        "ok": True,
                        "protocol": "rest",
                        "path": self.path,
                        "body_bytes": len(body),
                    }
                ).encode(),
            )


def grpc_server() -> grpc.Server:
    def create(_request: bytes, _context: grpc.ServicerContext) -> bytes:
        message = b"created"
        return bytes((0x0A, len(message))) + message

    handler = grpc.unary_unary_rpc_method_handler(
        create,
        request_deserializer=lambda value: value,
        response_serializer=lambda value: value,
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                "releasegrpc_v1.Resource", {"Create": handler}
            ),
        )
    )
    grpc_port = int(os.environ.get("FIXTURE_GRPC_PORT", "50051"))
    if server.add_insecure_port(f"127.0.0.1:{grpc_port}") == 0:
        raise RuntimeError("could not bind the release gRPC fixture")
    return server


def main() -> int:
    http_port = int(os.environ.get("FIXTURE_HTTP_PORT", "8080"))
    http = ThreadingHTTPServer(("127.0.0.1", http_port), Handler)
    http_thread = threading.Thread(target=http.serve_forever, daemon=True)
    grpc_service = grpc_server()
    stopped = threading.Event()

    def stop(*_args: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    http_thread.start()
    grpc_service.start()
    print("release fixture upstreams ready", flush=True)
    stopped.wait()
    http.shutdown()
    grpc_service.stop(5).wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
