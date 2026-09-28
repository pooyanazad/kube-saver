"""Regression tests for the non-TUI analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from kube_saver import cli as cli_mod
from kube_saver.config import KubeSaverConfig
from kube_saver.models.core import (
    ActualUsage,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
    ScanResult,
)


def _pod() -> PodResourceInfo:
    return PodResourceInfo(
        name="api-abc",
        namespace="prod",
        workload_kind="Deployment",
        workload_name="api",
        resources=ResourceQuantities(
            cpu_millicores_request=1000,
            memory_bytes_request=1024**3,
        ),
    )


class _FakeClient:
    created: _FakeClient | None = None

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.pod = _pod()
        type(self).created = self

    def connect(self) -> None:
        pass

    def get_all_pods(self) -> ScanResult:
        return ScanResult.success([self.pod])

    def get_namespaces(self) -> list[NamespaceInfo]:
        return [NamespaceInfo(name="prod")]


@dataclass
class _RuntimeResult:
    metrics_available: bool


class _MeasuredRuntime:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> _RuntimeResult:
        pods[0].actual = ActualUsage(
            cpu_millicores=100,
            memory_bytes=128 * 1024**2,
            source=MetricSource.METRICS_SERVER,
        )
        return _RuntimeResult(metrics_available=True)


class _UnavailableRuntime:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> _RuntimeResult:
        return _RuntimeResult(metrics_available=False)


def _install_fakes(monkeypatch, runtime: type[object]) -> KubeSaverConfig:
    from kube_saver import config as config_mod

    config = KubeSaverConfig(
        namespace_filter=["prod"],
        protected_namespaces=[],
        kubeconfig_context="test-context",
    )
    monkeypatch.setattr(config_mod, "load_config", lambda: config)
    monkeypatch.setattr(cli_mod, "K8sClient", _FakeClient)
    monkeypatch.setattr(cli_mod, "RuntimeCollector", runtime)
    return config


def test_cli_analysis_collects_runtime_metrics(monkeypatch) -> None:
    config = _install_fakes(monkeypatch, _MeasuredRuntime)

    resource, _cost, recommendations, _scan = cli_mod._run_analysis()

    assert resource.metrics_available is True
    assert resource.total_cpu_waste_millicores == 900
    assert recommendations
    assert _FakeClient.created is not None
    assert _FakeClient.created.kwargs["context"] == "test-context"
    assert _FakeClient.created.kwargs["namespace_filter"] == ["prod"]
    assert _FakeClient.created.kwargs["exclude_namespaces"] == config.exclude_namespaces


def test_cli_analysis_does_not_recommend_from_estimates(monkeypatch) -> None:
    _install_fakes(monkeypatch, _UnavailableRuntime)

    resource, _cost, recommendations, _scan = cli_mod._run_analysis()

    assert resource.metrics_available is False
    assert resource.total_cpu_waste_millicores == 1000
    assert recommendations == []
