"""Tests for K8sClient.get_all_pods returning a ScanResult (C3.1b).

Verifies the three scan outcomes against the same fake-kubernetes harness
used by the retry tests:

* ``ok``     — every namespace lists cleanly.
* ``partial``— one namespace fails after retries; the other's pods are
  still returned and the failed namespace's final error is preserved in
  ``ScanResult.errors``.
* ``failed`` — every namespace fails (or no namespaces are readable) so
  no pods are returned and the error is recorded.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kube_saver.config import RetryConfig, TimeoutConfig


def _make_api_exception(status: int, reason: str | None = None) -> Exception:
    """Build an ApiException-like object carrying a status attribute."""
    exc = Exception(f"http {status}: {reason or ''}")
    exc.status = status
    exc.reason = reason
    return exc


def _install_fake_kubernetes(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Patch sys.modules so K8sClient believes the kubernetes package exists."""
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

    return {
        "core_api": fake_core_api,
        "apps_api": fake_apps_api,
        "version_api": fake_version_api,
        "client": fake_k8s_client,
        "config": fake_k8s_config,
    }


def _patch_api_exception_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make retry.is_transient recognise our status-bearing fake exceptions."""

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
        exclude_namespaces=set(),
    )
    client.connect()
    return client, fakes


def _namespace(name: str) -> MagicMock:
    """Build a minimal namespace-like object the client can parse."""
    ns = MagicMock(name=f"ns-{name}")
    ns.metadata.name = name
    ns.metadata.labels = {}
    return ns


def _pod(name: str, namespace: str) -> MagicMock:
    """Build a minimal pod-like object the client can parse."""
    container = MagicMock(name=f"{name}-c")
    container.name = name + "-c"
    container.resources = {}

    pod_spec = MagicMock(name=f"{name}-spec")
    pod_spec.node_name = "node-1"
    pod_spec.containers = [container]

    meta = MagicMock(name=f"{name}-meta")
    meta.name = name
    meta.owner_references = []
    meta.labels = {}
    meta.annotations = {}

    status = MagicMock(name=f"{name}-status")
    status.container_statuses = []

    pod = MagicMock(name=name)
    pod.spec = pod_spec
    pod.metadata = meta
    pod.status = status
    return pod


class TestGetAllPodsScanResult:
    def test_ok_when_every_namespace_lists_cleanly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.return_value = MagicMock(
            items=[_namespace("team-a"), _namespace("team-b")]
        )
        fakes["core_api"].list_namespaced_pod.side_effect = [
            MagicMock(items=[_pod("api-0", "team-a")]),
            MagicMock(items=[_pod("worker-0", "team-b")]),
        ]

        result = client.get_all_pods()

        assert result.ok is True
        assert result.partial is False
        assert result.failed is False
        assert result.errors == []
        assert sorted(p.name for p in result.pods) == ["api-0", "worker-0"]
        assert fakes["core_api"].list_namespaced_pod.call_count == 2

    def test_partial_preserves_failed_namespace_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.return_value = MagicMock(
            items=[_namespace("team-a"), _namespace("team-b")]
        )
        # team-a lists cleanly on the first call; team-b raises a transient
        # 503 on every attempt so it is retried until the budget is exhausted.
        exc_503 = _make_api_exception(503, "Service Unavailable")

        def _list_namespaced_pod(*args, **kwargs):
            # The client iterates namespaces in order: team-a first, then team-b.
            namespace = kwargs.get("namespace") or (args[0] if args else "")
            if namespace == "team-a":
                return MagicMock(items=[_pod("api-0", "team-a")])
            raise exc_503

        fakes["core_api"].list_namespaced_pod.side_effect = _list_namespaced_pod

        result = client.get_all_pods()

        assert result.ok is False
        assert result.partial is True
        assert result.failed is False
        assert [p.name for p in result.pods] == ["api-0"]
        assert len(result.errors) == 1
        assert result.errors[0].startswith("team-b:")
        assert "503" in result.errors[0]
        # team-a (1) + team-b exhausted 3 retry attempts.
        assert fakes["core_api"].list_namespaced_pod.call_count == 1 + 3

    def test_partial_with_non_transient_failure_records_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.return_value = MagicMock(
            items=[_namespace("team-a"), _namespace("team-b")]
        )
        # team-a lists cleanly; team-b is a non-transient 403 (RBAC), no retries.
        fakes["core_api"].list_namespaced_pod.side_effect = [
            MagicMock(items=[_pod("api-0", "team-a")]),
            _make_api_exception(403, "Forbidden"),
        ]

        result = client.get_all_pods()

        assert result.partial is True
        assert [p.name for p in result.pods] == ["api-0"]
        assert len(result.errors) == 1
        assert result.errors[0].startswith("team-b:")
        assert "403" in result.errors[0]
        # team-b failed fast without retrying.
        assert fakes["core_api"].list_namespaced_pod.call_count == 2

    def test_failed_when_every_namespace_exhausts_retries(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        fakes["core_api"].list_namespace.return_value = MagicMock(
            items=[_namespace("team-a"), _namespace("team-b")]
        )
        # Both namespaces fail after retries are exhausted: the same
        # transient 504 is raised on every call (side_effect set to an
        # exception instance re-raises it each time, never exhausting).
        fakes["core_api"].list_namespaced_pod.side_effect = _make_api_exception(
            504, "Gateway Timeout"
        )

        result = client.get_all_pods()

        assert result.ok is False
        assert result.partial is False
        assert result.failed is True
        assert result.pods == []
        assert len(result.errors) == 2
        assert all(e.startswith("team-") for e in result.errors)
        assert all("504" in e for e in result.errors)

    def test_failed_when_no_namespaces_are_readable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_api_exception_type(monkeypatch)
        client, fakes = _build_client(monkeypatch, tmp_path)

        # No readable namespaces (RBAC / cluster down).
        fakes["core_api"].list_namespace.return_value = MagicMock(items=[])

        result = client.get_all_pods()

        assert result.ok is False
        assert result.partial is False
        assert result.failed is True
        assert result.pods == []
        assert len(result.errors) == 1
        assert "get_namespaces" in result.errors[0]
        # Never even tried to list pods since there were no namespaces.
        assert fakes["core_api"].list_namespaced_pod.call_count == 0
