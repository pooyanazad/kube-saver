import json
from http.client import HTTPConnection
from threading import Thread
from urllib.request import urlopen

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.exporters.json_output import build_json_report
from kube_saver.models.core import CloudProvider, ClusterInfo, Recommendation
from kube_saver.server import build_server


def test_build_json_report() -> None:
    payload = build_json_report(
        cluster=ClusterInfo(name="demo", context="ctx", provider=CloudProvider.UNKNOWN),
        resource_report=ResourceWasteReport(total_pods=2, metrics_available=True),
        cost_report=CostWasteReport(),
        recommendations=[Recommendation(target_name="demo", resource_type="cpu-request")],
    )
    assert payload["cluster"]["name"] == "demo"
    assert payload["resource_report"]["total_pods"] == 2
    assert payload["recommendations"][0]["resource_type"] == "cpu-request"



def test_server_mode_endpoints() -> None:
    payload = {"ok": True, "items": 1}
    server = build_server(lambda: payload, port=0)
    try:
        host, port = server.server_address
        from threading import Thread

        thread = Thread(target=server.handle_request, daemon=True)
        thread.start()
        data = json.loads(urlopen(f"http://{host}:{port}/api/v1/report", timeout=2).read().decode())
        assert data == payload

        thread = Thread(target=server.handle_request, daemon=True)
        thread.start()
        health = json.loads(urlopen(f"http://{host}:{port}/healthz", timeout=2).read().decode())
        assert health["status"] == "ok"
    finally:
        server.server_close()


def _serve_once(server) -> None:
    """Handle exactly one request in a background thread."""
    Thread(target=server.handle_request, daemon=True).start()


def test_server_static_banner_no_version_leak() -> None:
    """Server header must not leak BaseHTTP/Python versions."""
    server = build_server(lambda: {}, port=0)
    try:
        host, port = server.server_address
        _serve_once(server)
        conn = HTTPConnection(host, port, timeout=2)
        conn.request("GET", "/healthz")
        resp = conn.getresponse()
        resp.read()
        assert resp.getheader("Server") == "kube-saver"
        assert "Python" not in (resp.getheader("Server") or "")
        assert "BaseHTTP" not in (resp.getheader("Server") or "")
        conn.close()
    finally:
        server.server_close()


def test_server_security_headers_present() -> None:
    """Security headers must be sent on every response."""
    server = build_server(lambda: {}, port=0)
    try:
        host, port = server.server_address
        _serve_once(server)
        conn = HTTPConnection(host, port, timeout=2)
        conn.request("GET", "/healthz")
        resp = conn.getresponse()
        resp.read()
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        assert resp.getheader("X-Frame-Options") == "DENY"
        assert resp.getheader("Referrer-Policy") == "no-referrer"
        assert resp.getheader("Cache-Control") == "no-store"
        conn.close()
    finally:
        server.server_close()


def test_server_head_returns_no_body_and_200() -> None:
    """HEAD must return 200 (not 501) with an empty body."""
    server = build_server(lambda: {"x": 1}, port=0)
    try:
        host, port = server.server_address
        _serve_once(server)
        conn = HTTPConnection(host, port, timeout=2)
        conn.request("HEAD", "/healthz")
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status == 200
        assert body == b""
        conn.close()
    finally:
        server.server_close()


def test_server_options_returns_allow_and_200() -> None:
    """OPTIONS must return 200 with an Allow header (not 501)."""
    server = build_server(lambda: {}, port=0)
    try:
        host, port = server.server_address
        _serve_once(server)
        conn = HTTPConnection(host, port, timeout=2)
        conn.request("OPTIONS", "/healthz")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 200
        allow = resp.getheader("Allow") or ""
        assert "GET" in allow and "HEAD" in allow and "OPTIONS" in allow
        conn.close()
    finally:
        server.server_close()


def test_server_unknown_methods_return_405() -> None:
    """POST/PUT/DELETE/PATCH/TRACE must return 405, not 501."""
    server = build_server(lambda: {}, port=0)
    try:
        host, port = server.server_address
        for method in ("POST", "PUT", "DELETE", "PATCH", "TRACE"):
            _serve_once(server)
            conn = HTTPConnection(host, port, timeout=2)
            conn.request(method, "/healthz")
            resp = conn.getresponse()
            resp.read()
            assert resp.status == 405, f"{method} should be 405, got {resp.status}"
            assert "GET" in (resp.getheader("Allow") or "")
            conn.close()
    finally:
        server.server_close()


def test_server_trace_does_not_echo_request() -> None:
    """TRACE must never echo the request body back (cross-site tracing)."""
    import socket

    server = build_server(lambda: {}, port=0)
    try:
        host, port = server.server_address
        _serve_once(server)
        sock = socket.create_connection((host, port), timeout=2)
        try:
            sock.sendall(b"TRACE /healthz HTTP/1.1\r\nHost: x\r\nSecret: hunter2\r\n\r\n")
            data = sock.recv(4096)
            assert b"hunter2" not in data
            assert b"405" in data
        finally:
            sock.close()
    finally:
        server.server_close()
