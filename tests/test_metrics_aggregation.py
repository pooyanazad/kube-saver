"""Regression tests for the metrics aggregation bugs.

Covers two bugs found in the metrics-server collection chain:

1. ``MetricsCollector.collect_all_pods`` overwrote ``available`` with the
   outcome of the *last* namespace (last-write-wins), so a transient
   failure in one namespace blanked the entire scan into ESTIMATED mode
   and inflated waste numbers.
2. The metric map was keyed by bare pod name, so identically named pods
   in different namespaces collided and got the wrong usage.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

from kube_saver.collectors.metrics import MetricsCollector
from kube_saver.models.core import (
    ActualUsage,
    MetricSource,
    PodResourceInfo,
    ResourceQuantities,
)


class _FakeApiException(Exception):  # noqa: N818 — mirrors upstream name
    """ApiException stand-in matching the upstream attribute surface."""

    def __init__(self, status=None, reason=None):
        super().__init__(status, reason)
        self.status = status
        self.reason = reason


def _fresh_timestamp() -> str:
    """ISO timestamp a few seconds in the past so samples count as fresh."""
    now = datetime.now(timezone.utc) - __import__("datetime").timedelta(seconds=2)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pod(name: str, namespace: str, cpu_used: float = 100.0) -> PodResourceInfo:
    return PodResourceInfo(
        name=name,
        namespace=namespace,
        workload_kind="Deployment",
        workload_name=name,
        resources=ResourceQuantities(cpu_millicores_request=1000),
        actual=ActualUsage(cpu_millicores=cpu_used, source=MetricSource.ESTIMATED),
    )


class _FakeCustomObjectsApi:
    """Fake metrics.k8s.io API with per-namespace success/failure."""

    def __init__(self, failing_namespaces: set[str], pods: list[PodResourceInfo]) -> None:
        self.failing_namespaces = failing_namespaces
        self.pods_by_ns: dict[str, list[str]] = {}
        for pod in pods:
            self.pods_by_ns.setdefault(pod.namespace, []).append(pod.name)
        self.calls: list[str] = []

    def list_namespaced_custom_object(self, group, version, namespace, plural):
        self.calls.append(namespace)
        if namespace in self.failing_namespaces:
            raise _FakeApiException(status=503)
        return {
            "items": [
                {
                    "metadata": {"name": pod_name},
                    "timestamp": _fresh_timestamp(),
                    "containers": [
                        {"usage": {"cpu": "100m", "memory": "128Mi"}},
                    ],
                }
                for pod_name in self.pods_by_ns.get(namespace, [])
            ]
        }


def _install_fake_kubernetes(
    monkeypatch, failing_namespaces: set[str], pods: list[PodResourceInfo]
) -> None:
    """Patch sys.modules so metrics.py believes kubernetes is installed."""
    fake = types.ModuleType("kubernetes")
    client_mod = types.ModuleType("kubernetes.client")
    rest_mod = types.ModuleType("kubernetes.client.rest")

    rest_mod.ApiException = _FakeApiException
    client_mod.rest = rest_mod

    fake_api = _FakeCustomObjectsApi(failing_namespaces, pods)
    client_mod.CustomObjectsApi = lambda: fake_api

    fake.client = client_mod
    monkeypatch.setitem(sys.modules, "kubernetes", fake)
    monkeypatch.setitem(sys.modules, "kubernetes.client", client_mod)
    monkeypatch.setitem(sys.modules, "kubernetes.client.rest", rest_mod)

    # metrics.py imports k8s names at module load; point them at the fake.
    import kube_saver.collectors.metrics as metrics_mod

    monkeypatch.setattr(metrics_mod, "_K8S_AVAILABLE", True)
    monkeypatch.setattr(metrics_mod, "k8s_client", client_mod)
    monkeypatch.setattr(metrics_mod, "ApiException", _FakeApiException)
    return fake_api


class TestAvailableAggregation:
    def test_one_failing_namespace_does_not_blank_scan(self, monkeypatch) -> None:
        """A 503 in one namespace must not mark the whole scan unavailable."""
        pods = [_pod("ns-a-pod", "ns-a"), _pod("ns-b-pod", "ns-b")]
        _install_fake_kubernetes(monkeypatch, failing_namespaces={"ns-b"}, pods=pods)
        collector = MetricsCollector()

        result = collector.collect_all_pods(pods)

        # Aggregate availability: ns-a succeeded, so metrics ARE available.
        assert collector.available is True
        # ns-a pod keeps its real usage; only ns-b pod drops to estimated.
        assert result["ns-a/ns-a-pod"].source is MetricSource.METRICS_SERVER
        assert "ns-b/ns-b-pod" not in result


class TestPodNameCollision:
    def test_same_pod_name_in_two_namespaces_gets_distinct_keys(self, monkeypatch) -> None:
        """Identically named pods must not collide in the metric map."""
        pods = [_pod("api-0", "team-a"), _pod("api-0", "team-b")]
        _install_fake_kubernetes(monkeypatch, failing_namespaces=set(), pods=pods)
        collector = MetricsCollector()

        result = collector.collect_all_pods(pods)

        assert set(result.keys()) == {"team-a/api-0", "team-b/api-0"}
        for pod in pods:
            assert pod.actual.source is MetricSource.METRICS_SERVER


class TestRuntimeUsesNamespacedKeys:
    def test_runtime_resolves_usage_by_namespace_name_key(self, monkeypatch) -> None:
        """runtime.py must look up usage with the ns/name key, not bare name."""
        from kube_saver.collectors.runtime import RuntimeCollector

        pods = [_pod("api-0", "team-a"), _pod("api-0", "team-b")]
        _install_fake_kubernetes(monkeypatch, failing_namespaces=set(), pods=pods)
        collector = RuntimeCollector(prefer_ebpf=False)

        result = collector.collect_all_pods(pods)

        assert result.source is MetricSource.METRICS_SERVER
        assert result.metrics_available is True


class TestMetricsCollectorUnit:
    def test_collect_pod_metrics_marks_unavailable_when_no_kubernetes(self, monkeypatch) -> None:
        import kube_saver.collectors.metrics as metrics_mod

        monkeypatch.setattr(metrics_mod, "_K8S_AVAILABLE", False)
        collector = MetricsCollector()
        result = collector.collect_pod_metrics([_pod("p", "default")])
        assert result == {}
        assert collector.available is False

    def test_available_stays_none_before_any_collection(self) -> None:
        collector = MetricsCollector()
        assert collector.available is None
