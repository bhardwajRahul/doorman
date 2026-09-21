#!/usr/bin/env python3
"""Deterministic, stateful protocol fixture; one profile per container."""

from __future__ import annotations

import base64
import gzip
import json
import os
import signal
import struct
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import grpc

PROFILE = os.environ["FIXTURE_PROFILE"]
PROFILES = {
    "rest-1", "rest-2", "graphql-1", "graphql-2", "soap-1", "soap-2",
    "grpc-1", "grpc-2", "grpc-web-1", "grpc-web-2",
}
if PROFILE not in PROFILES:
    raise SystemExit(f"unknown FIXTURE_PROFILE: {PROFILE}")

LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "journal": [],
    "counts": {},
    "items": {},
    "next_id": 1,
    "control": {"latency_ms": 0, "disconnect": False, "malformed": False, "statuses": []},
}


def reset() -> None:
    with LOCK:
        STATE.update(journal=[], counts={}, items={}, next_id=1)
        STATE["control"] = {
            "latency_ms": 0, "disconnect": False, "malformed": False, "statuses": []
        }


def frame(payload: bytes, flag: int = 0) -> bytes:
    return bytes([flag]) + struct.pack(">I", len(payload)) + payload


def trailer(status: int = 0, message: str = "") -> bytes:
    value = f"grpc-status: {status}\r\ngrpc-message: {message}\r\n".encode()
    return frame(value, 0x80)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def reply(
        self, status: int, body: bytes = b"", content_type: str = "application/json", headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Fixture-Profile", PROFILE)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def reply_json(self, status: int, value: Any, headers: dict[str, str] | None = None) -> None:
        self.reply(status, json.dumps(value, sort_keys=True).encode(), headers=headers)

    def record(self, body: bytes) -> tuple[int | None, dict[str, Any]]:
        with LOCK:
            control = dict(STATE["control"])
            STATE["counts"][self.command] = STATE["counts"].get(self.command, 0) + 1
            STATE["journal"].append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {key.lower(): value for key, value in self.headers.items()},
                    "body_bytes": len(body),
                }
            )
            status = STATE["control"]["statuses"].pop(0) if STATE["control"]["statuses"] else None
        latency = max(0, min(int(control["latency_ms"]), 30000))
        if latency:
            time.sleep(latency / 1000)
        if control["disconnect"]:
            self.close_connection = True
            self.connection.shutdown(2)
            return status, control
        return status, control

    def control(self, path: str, body: bytes) -> bool:
        if path == "/health":
            self.reply_json(200, {"status": "healthy", "profile": PROFILE})
            return True
        if path == "/__control/journal":
            with LOCK:
                self.reply_json(200, {"profile": PROFILE, "requests": STATE["journal"]})
            return True
        if path == "/__control/counters":
            with LOCK:
                self.reply_json(200, {"profile": PROFILE, "counts": STATE["counts"]})
            return True
        if path == "/__control/reset" and self.command == "POST":
            reset()
            self.reply_json(200, {"reset": True, "profile": PROFILE})
            return True
        if path == "/__control/faults" and self.command in {"PUT", "POST"}:
            try:
                value = json.loads(body or b"{}")
                allowed = {"latency_ms", "disconnect", "malformed", "statuses"}
                if not isinstance(value, dict) or set(value) - allowed:
                    raise ValueError
                statuses = value.get("statuses", [])
                if not isinstance(statuses, list) or not all(isinstance(item, int) for item in statuses):
                    raise ValueError
                with LOCK:
                    STATE["control"].update(value)
                self.reply_json(200, {"updated": True})
            except (ValueError, json.JSONDecodeError):
                self.reply_json(400, {"error": "invalid fault controls"})
            return True
        return False

    def discovery(self, path: str) -> bool:
        if path == "/openapi.json" and PROFILE == "rest-1":
            self.reply_json(
                200,
                {
                    "openapi": "3.1.0",
                    "info": {"title": "Doorman REST fixture", "version": "1.0"},
                    "paths": {"/items/{id}": {"get": {"operationId": "getItem"}}},
                },
            )
            return True
        if path == "/swagger.json" and PROFILE == "rest-2":
            self.reply_json(
                200,
                {
                    "swagger": "2.0",
                    "info": {"title": "Doorman REST fixture", "version": "2.0"},
                    "basePath": "/",
                    "paths": {"/upload": {"post": {"operationId": "upload"}}},
                },
            )
            return True
        if path == "/service.wsdl" and PROFILE.startswith("soap"):
            soap12 = PROFILE == "soap-2"
            namespace = "http://schemas.xmlsoap.org/wsdl/soap12/" if soap12 else "http://schemas.xmlsoap.org/wsdl/soap/"
            xml = f'''<?xml version="1.0"?><definitions xmlns="http://schemas.xmlsoap.org/wsdl/" xmlns:soap="{namespace}" targetNamespace="urn:doorman:fixture"><service name="Fixture"><port name="FixturePort"><soap:address location="http://fixture/soap"/></port></service></definitions>'''.encode()
            self.reply(200, xml, "application/wsdl+xml")
            return True
        return False

    def dispatch(self) -> None:
        body = self.read_body()
        path = urlsplit(self.path).path
        if self.control(path, body) or self.discovery(path):
            return
        forced, control = self.record(body)
        if control["disconnect"]:
            return
        if forced is not None:
            self.reply_json(forced, {"forced": forced, "profile": PROFILE})
            return
        if control["malformed"]:
            self.reply(200, b"{not-valid", "application/json")
            return
        if PROFILE.startswith("rest"):
            self.rest(path, body)
        elif PROFILE.startswith("graphql"):
            self.graphql(body)
        elif PROFILE.startswith("soap"):
            self.soap(body)
        elif PROFILE.startswith("grpc-web"):
            self.grpc_web(body)
        else:
            self.reply_json(404, {"error": "native gRPC is served on port 50051"})

    def rest(self, path: str, body: bytes) -> None:
        if path == "/redirect":
            self.reply(302, headers={"Location": "/items"})
            return
        if path == "/large":
            self.reply(200, b"x" * (2 * 1024 * 1024), "application/octet-stream")
            return
        if path == "/gzip":
            value = gzip.compress(b'{"compressed":true}')
            self.reply(200, value, headers={"Content-Encoding": "gzip"})
            return
        if path == "/etag":
            if self.headers.get("If-None-Match") == '"fixture-v1"':
                self.reply(304, headers={"ETag": '"fixture-v1"'})
            else:
                self.reply_json(200, {"etag": True}, {"ETag": '"fixture-v1"'})
            return
        if path == "/upload" and self.command == "POST":
            self.reply_json(201, {"bytes": len(body), "content_type": self.headers.get("Content-Type")})
            return
        if path == "/items" and self.command == "POST":
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                self.reply_json(400, {"error": "malformed json"})
                return
            with LOCK:
                item_id = str(STATE["next_id"])
                STATE["next_id"] += 1
                STATE["items"][item_id] = value
            self.reply_json(201, {"id": item_id, **value})
            return
        if path == "/items":
            query = parse_qs(urlsplit(self.path).query)
            with LOCK:
                items = [{"id": key, **value} for key, value in sorted(STATE["items"].items())]
            limit = int(query.get("limit", [len(items) or 1])[0])
            self.reply_json(200, {"items": items[:limit], "next": None})
            return
        match = __import__("re").fullmatch(r"/items/([^/]+)", path)
        if match:
            item_id = match.group(1)
            with LOCK:
                found = STATE["items"].get(item_id)
                if found is not None and self.command in {"PUT", "PATCH"}:
                    found.update(json.loads(body))
                if found is not None and self.command == "DELETE":
                    del STATE["items"][item_id]
            if found is None:
                self.reply_json(404, {"error": "not found"})
            elif self.command == "DELETE":
                self.reply(204)
            else:
                self.reply_json(200, {"id": item_id, **found})
            return
        self.reply_json(200, {"ok": True, "method": self.command, "path": self.path})

    def graphql(self, body: bytes) -> None:
        try:
            value = json.loads(body)
            query = value["query"]
        except (json.JSONDecodeError, KeyError, TypeError):
            self.reply_json(400, {"errors": [{"message": "invalid GraphQL request"}]})
            return
        if "__schema" in query and PROFILE == "graphql-2":
            self.reply_json(403, {"errors": [{"message": "introspection disabled"}]})
        elif query.count("{") > 6 and PROFILE == "graphql-2":
            self.reply_json(400, {"errors": [{"message": "maximum depth exceeded"}]})
        elif "partial" in query and PROFILE == "graphql-2":
            self.reply_json(200, {"data": {"partial": "available"}, "errors": [{"message": "partial failure"}]})
        elif "mutation" in query:
            self.reply_json(200, {"data": {"updateItem": {"ok": True}}})
        else:
            self.reply_json(200, {"data": {"hello": "Hello, Doorman!", "variables": value.get("variables")}})

    def soap(self, body: bytes) -> None:
        media = self.headers.get("Content-Type", "")
        if PROFILE == "soap-2" and "application/soap+xml" not in media:
            self.reply(415, b"wrong SOAP 1.2 content type", "text/plain")
            return
        if PROFILE == "soap-2" and b"UsernameToken" not in body:
            fault = b'<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Body><env:Fault><env:Reason><env:Text>Security required</env:Text></env:Reason></env:Fault></env:Body></env:Envelope>'
            self.reply(500, fault, "application/soap+xml")
            return
        if b"<FaultRequest" in body:
            self.reply(500, b"<Envelope><Body><Fault><faultcode>Fixture.Typed</faultcode></Fault></Body></Envelope>", "text/xml")
            return
        if b"Envelope" not in body:
            self.reply(400, b"<error>malformed envelope</error>", "text/xml")
            return
        content_type = "application/soap+xml" if PROFILE == "soap-2" else "text/xml; charset=utf-8"
        self.reply(200, b'<?xml version="1.0"?><Envelope><Body><PingResponse><ok>true</ok></PingResponse></Body></Envelope>', content_type)

    def grpc_web(self, body: bytes) -> None:
        origin = self.headers.get("Origin")
        if self.command == "OPTIONS":
            if PROFILE == "grpc-web-2" and origin == "https://denied.example":
                self.reply(403)
            else:
                self.reply(204, headers={"Access-Control-Allow-Origin": origin or "*", "Access-Control-Allow-Headers": "content-type,x-grpc-web"})
            return
        text_mode = PROFILE == "grpc-web-2"
        try:
            raw = base64.b64decode(body, validate=True) if text_mode else body
            if len(raw) < 5 or len(raw) != 5 + struct.unpack(">I", raw[1:5])[0]:
                raise ValueError
        except (ValueError, struct.error):
            response = trailer(13, "malformed frame")
        else:
            response = trailer(7, "fixture denial") if text_mode else frame(b"\x0a\x02ok") + trailer()
        if text_mode:
            response = base64.b64encode(response)
        media = "application/grpc-web-text" if text_mode else "application/grpc-web+proto"
        self.reply(200, response, media, {"grpc-status": "0"})

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_OPTIONS = dispatch


def grpc_service() -> grpc.Server | None:
    if not PROFILE.startswith("grpc-") or PROFILE.startswith("grpc-web"):
        return None

    def unary(request: bytes, context: grpc.ServicerContext) -> bytes:
        with LOCK:
            STATE["counts"]["grpc"] = STATE["counts"].get("grpc", 0) + 1
            control = dict(STATE["control"])
            status = STATE["control"]["statuses"].pop(0) if STATE["control"]["statuses"] else 0
            STATE["journal"].append(
                {
                    "method": "GRPC",
                    "path": "/fixture.v1.Resource/*",
                    "body_bytes": len(request),
                    "metadata": dict(context.invocation_metadata()),
                }
            )
        if control["latency_ms"]:
            time.sleep(control["latency_ms"] / 1000)
        if status:
            context.abort(grpc.StatusCode.UNAVAILABLE if status == 14 else grpc.StatusCode.INVALID_ARGUMENT, "controlled fixture error")
        return b"\x0a\x02ok"

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    handler = grpc.unary_unary_rpc_method_handler(unary, request_deserializer=lambda value: value, response_serializer=lambda value: value)
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("fixture.v1.Resource", {"Create": handler, "Get": handler, "Update": handler, "Delete": handler}),))
    if server.add_insecure_port("0.0.0.0:50051") == 0:
        raise RuntimeError("could not bind native gRPC fixture")
    return server


def main() -> int:
    http = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    grpc_server = grpc_service()
    stopped = threading.Event()

    def stop(*_args: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    thread.start()
    if grpc_server:
        grpc_server.start()
    print(json.dumps({"status": "ready", "profile": PROFILE}), flush=True)
    stopped.wait()
    http.shutdown()
    if grpc_server:
        grpc_server.stop(5).wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
