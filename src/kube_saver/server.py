"""Minimal HTTP server mode for kube-saver."""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

from kube_saver.version import VERSION

# Static server banner. Never reveal the Python/BaseHTTP version.
_SERVER_BANNER = "kube-saver"

# Security headers applied to every response. HSTS is intentionally not set
# because the server is loopback-only by design and is expected to sit behind
# a TLS-terminating reverse proxy when exposed.
_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Type": "application/json",
}

# Methods this server actually understands. Sent in the Allow header on 405.
_ALLOWED_METHODS = "GET, HEAD, OPTIONS"


class _Handler(BaseHTTPRequestHandler):
    # Override BaseHTTPRequestHandler's "BaseHTTP/0.6 Python/x.y" banner so
    # service fingerprinting (e.g. nmap -sV) cannot read the runtime version.
    server_version = _SERVER_BANNER
    sys_version = ""

    def version_string(self) -> str:  # noqa: D401
        return _SERVER_BANNER

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

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path in {"/healthz", "/readyz", "/api/v1/report", "/openapi.json", "/swagger.json"}:
            self._send_json(200, None)
            return
        self._send_json(404, None)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(200, {"status": "ok"}, extra_headers={"Allow": _ALLOWED_METHODS})

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    def log_message(self, log_format: str, *args: object) -> None:  # noqa: A003
        return

    def _send_json(
        self,
        status: int,
        payload: dict[str, object] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        for name, value in _SECURITY_HEADERS.items():
            self.send_header(name, value)
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
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
