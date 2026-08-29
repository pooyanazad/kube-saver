"""Tests for K8sClient retry wrapping of API calls (C2.4a, C2.4b, C2.4c).

Each high-level query (``get_namespaces``, ``get_pods``, ``get_cluster_info``)
is wrapped in ``retry_call`` so transient failures (5xx, 429, timeouts) are
retried with backoff before surfacing as an RBAC / empty-list fallback.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kube_saver.config import RetryConfig, TimeoutConfig

# ── Fake kubernetes fixture (shared with test_timeouts) ───────────────────


def _make_api_exception(status: int, reason: str | None = None) -> Exception:
    """Build an ApiException-like object carrying a status attribute."""
    exc = Exception(f"http {status}: {reason or ''}")
    exc.status = status
    exc.reason = reason
    return exc


def _install_fake_kubernetes(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Patch sys.modules so K8sClient believes the kubernetes package exists.

    Returns the fakes dict (core_api, version_api, ...) for assertions.
    """
    fake_k8s_client = MagicMock(name="k8s_client")
    fake_k8s_config = MagicMock(name="k8s_config")
    fake_k8s_config.ConfigException = type("ConfigException", (Exception,), {})
    fake_k8s_config.load_kube_config.return_value = None
    fake_k8s_config.load_incluster_config.return_value = None

    fake_core_api = MagicMock(name="CoreV1Api")
    fake_apps_api = MagicMock(name="AppsV1Api")
    fake_version_api = MagicMock(name="VersionApi")
    fake_k8s_client.CoreV1Api.return_value = fake_core_api
    fake_k8s_client.AppsV1Api.return_value = fake_apps_api
    fake_k8s_client.VersionApi.return_value = fake_version_api

    pool_manager = MagicMock(name="pool_manager")
    pool_manager.connection_pool_kw = {}
    rest_client = MagicMock(name="rest_client")
    rest_client.pool_manager = pool_manager
    api_client = MagicMock(name="api_client")
    api_client.rest_client = rest_client
    fake_core_api.rest_client = rest_client
    fake_core_api.api_client = api_client
    fake_apps_api.rest_client = rest_client
    fake_apps_api.api_client = api_client

    fake_rest_module = MagicMock(name="kubernetes.client.rest")
    fake_rest_module.ApiException = _make_api_exception.__class__  # placeholder

    fake_pkg = types.ModuleType("kubernetes")
    fake_pkg.client = fake_k8s_client
    fake_pkg.config = fake_k8s_config

    monkeypatch.setitem(sys.modules, "kubernetes", fake_pkg)
    monkeypatch.setitem(sys.modules, "kubernetes.client", fake_k8s_client)
    monkeypatch.setitem(sys.modules, "kubernetes.config", fake_k8s_config)
    monkeypatch.setitem(sys.modules, "kubernetes.client.rest", fake_rest_module)

    from kube_saver.collectors import k8s_client as kmod

    monkeypatch.setattr(kmod, "_K8S_AVAILABLE", True)
    monkeypatch.setattr(kmod, "k8s_client", fake_k8s_client)
    monkeypatch.setattr(kmod, "k8s_config", fake_k8s_config)
    # NOTE: do not patch retry.ApiException here — _patch_api_exception_type
    # owns that so is_transient recognises our status-bearing fakes.

    return {
        "core_api": fake_core_api,
        "apps_api": fake_apps_api,
        "version_api": fake_version_api,
        "client": fake_k8s_client,
        "config": fake_k8s_config,
    }


def _api_exc_type() -> type:
    """Return the ApiException type that retry.is_transient will recognise."""
    from kube_saver.collectors import retry as rmod

    return rmod.ApiException  # type: ignore[no-any-return]


def _build_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Construct a connected K8sClient against the fake kubernetes package."""
    cfg = tmp_path / "config"
    cfg.write_text("apiVersion: v1\n")
    monkeypatch.setenv("KUBECONFIG", str(cfg))

    from kube_saver.collectors.k8s_client import K8sClient

    fakes = _install_fake_kubernetes(monkeypatch)
    client = K8sClient(
        timeouts=TimeoutConfig(operation_seconds=5),
        retries=RetryConfig(max_attempts=3, initial_backoff_ms=1, max_backoff_ms=5),
    )
    client.connect()
    return client, fakes


def _patch_api_exception_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retry.is_transient recognise our fake ApiException instances.

    The real kubernetes ApiException is a class; our fake exceptions are plain
    ``Exception`` subclasses carrying a ``status`` attribute. We point the retry
    module's ``ApiException`` at a type whose ``__instancecheck__`` matches
    any object exposing a numeric ``status`` attribute.
    """

    class _ApiExceptionMeta(type):
        def __instancecheck__(cls, instance: object) -> bool:
            status = getattr(instance, "status", None)
            try:
                return status is not None and int(status)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False

    class _ApiException(metaclass=_ApiExceptionMeta):
        pass

    from kube_saver.collectors import retry as rmod

    monkeypatch.setattr(rmod, "ApiException", _ApiException)


# ── C2.4a: get_namespaces retries transient failures ─────────────────────


class TestGetNamespacesRetries:
    def test_success_on_first_call(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        ns1 = MagicMock()
        ns1.metadata.name = "team-a"
        ns1.metadata.labels = {}
        ns2 = MagicMock()
        ns2.metadata.name = "team-b"
        ns2.metadata.labels = {}
        fakes["core_api"].list_namespace.return_value = MagicMock(items=[ns1, ns2])

        result = client.get_namespaces()

        assert [n.name for n in result] == ["team-a", "team-b"]
        assert fakes["core_api"].list_namespace.call_count == 1

    def test_retries_then_recovers_on_503(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        ns = MagicMock()
        ns.metadata.name = "team-a"
        ns.metadata.labels = {}
        fakes["core_api"].list_namespace.side_effect = [
            _make_api_exception(503, "Service Unavailable"),
            MagicMock(items=[ns]),
        ]

        result = client.get_namespaces()

        assert [n.name for n in result] == ["team-a"]
        assert fakes["core_api"].list_namespace.call_count == 2

    def test_returns_empty_after_exhaustion(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.side_effect = _make_api_exception(503)

        result = client.get_namespaces()

        assert result == []
        assert fakes["core_api"].list_namespace.call_count == 3

    def test_non_transient_4xx_returns_empty_without_retry(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.side_effect = _make_api_exception(403, "Forbidden")

        result = client.get_namespaces()

        assert result == []
        assert fakes["core_api"].list_namespace.call_count == 1
