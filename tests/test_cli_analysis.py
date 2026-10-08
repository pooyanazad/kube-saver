"""Regression tests for the non-TUI analysis pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass

from click.testing import CliRunner

from kube_saver import cli as cli_mod
from kube_saver import exitcodes
from kube_saver.analyzers.cost_waste import analyze_cost_waste
from kube_saver.analyzers.resource_waste import analyze_resource_waste
from kube_saver.config import KubeSaverConfig
from kube_saver.models.core import (
    ActualUsage,
    ContainerResourceInfo,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
    ScanResult,
)
from kube_saver.pricing.engine import PricingEngine


def _pod() -> PodResourceInfo:
    return PodResourceInfo(
        name="api-abc",
        namespace="prod",
        workload_kind="Deployment",
        workload_name="api",
        containers=[ContainerResourceInfo(name="api")],
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


def _analysis_result(scan: ScanResult, measured: bool = True):
    pods = scan.pods
    if measured:
        for pod in pods:
            pod.actual = ActualUsage(
                cpu_millicores=100,
                memory_bytes=128 * 1024**2,
                source=MetricSource.METRICS_SERVER,
            )
    resource = analyze_resource_waste(
        [NamespaceInfo(name="prod")], pods, metrics_available=measured
    )
    cost = analyze_cost_waste(resource, PricingEngine())
    return resource, cost, [], scan


def test_failed_scan_does_not_write_a_successful_empty_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        cli_mod,
        "_run_analysis",
        lambda: _analysis_result(ScanResult.failure(["prod: HTTP 403 Forbidden"])),
    )
    output = tmp_path / "report.html"
    result = CliRunner().invoke(cli_mod.cli, ["report", "-o", str(output)])
    assert result.exit_code == exitcodes.ANALYSIS_ERROR
    assert "prod: HTTP 403 Forbidden" in result.output
    assert not output.exists()


def test_partial_scan_marks_html_and_json_outputs(monkeypatch, tmp_path) -> None:
    scan = ScanResult.partial_success([_pod()], ["staging: HTTP 403 Forbidden"])
    monkeypatch.setattr(cli_mod, "_run_analysis", lambda: _analysis_result(scan))
    html_path = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli_mod.cli,
        ["report", "-o", str(html_path), "--json", str(json_path)],
    )
    assert result.exit_code == 0
    assert "Warning: pod scan incomplete" in result.output
    assert "Incomplete scan" in html_path.read_text()
    payload = json.loads(json_path.read_text())
    assert payload["degraded"] is True
    assert payload["degraded_errors"] == ["staging: HTTP 403 Forbidden"]


def test_notify_does_not_raise_spike_from_request_only_estimates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        cli_mod,
        "_run_analysis",
        lambda: _analysis_result(ScanResult.success([_pod()]), measured=False),
    )
    result = CliRunner().invoke(
        cli_mod.cli,
        ["notify", "-d", str(tmp_path), "--threshold", "0"],
    )
    assert result.exit_code == 0
    assert "No spike alert" in result.output
    assert not list(tmp_path.glob("spike-alert-*.md"))
    summary = next(tmp_path.glob("daily-summary-*.md")).read_text()
    assert "Metrics coverage" in summary
    assert "upper bound" in summary
