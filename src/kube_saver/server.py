"""Minimal HTTP server mode for kube-saver."""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

from kube_saver.version import VERSION


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/healthz", "/readyz"}:
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/api/v1/report":
            report_builder = getattr(self.server, "report_builder", None)
            payload = report_builder() if report_builder else {"error": "no report builder"}
            self._send_json(200, payload)
            return
        if self.path in {"/openapi.json", "/swagger.json"}:
            self._send_json(200, _openapi_stub())
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def log_message(self, log_format: str, *args: object) -> None:  # noqa: A003
        return

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_server(
    report_builder: Callable[[], dict[str, object]],
    host: str = "127.0.0.1",
    port: int = 8080,
) -> HTTPServer:
    """Create an HTTP server exposing kube-saver API endpoints."""
    server = HTTPServer((host, port), _Handler)
    server.report_builder = report_builder  # type: ignore[attr-defined]
    return server


def _openapi_stub() -> dict[str, object]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "kube-saver API", "version": VERSION},
        "paths": {
            "/healthz": {"get": {"summary": "Health check"}},
            "/api/v1/report": {"get": {"summary": "Current kube-saver report"}},
        },
    }


__all__ = ["build_server"]
