"""Integration tests for Step 42."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kube_saver.config import load_config
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ClusterInfo,
    Currency,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
    ScanResult,
)
from kube_saver.tui import data as tui_data
from kube_saver.version import VERSION


@dataclass
class _FakeRuntimeResult:
    source: MetricSource
    metrics_available: bool
    used_fallback: bool
    warnings: list[str]
    advanced_metrics: dict


class _FakeRuntimeCollector:
    def __init__(
        self,
        prefer_ebpf: bool = True,
        max_metric_age_seconds: float = 300.0,
    ) -> None:
        self.prefer_ebpf = prefer_ebpf
        self.max_metric_age_seconds = max_metric_age_seconds

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> _FakeRuntimeResult:
        return _FakeRuntimeResult(
            source=MetricSource.METRICS_SERVER,
            metrics_available=True,
            used_fallback=False,
            warnings=["integration-test-warning"],
            advanced_metrics={f"{p.namespace}/{p.name}": {"ok": True} for p in pods},
        )


class _FakeK8sClient:
    def __init__(self, context=None, exclude_namespaces=None, namespace_filter=None, timeouts=None, retries=None) -> None:
        self.context = context
        self.exclude_namespaces = exclude_namespaces or set()
        self.namespace_filter = namespace_filter
        self.timeouts = timeouts
        self.retries = retries
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def get_cluster_info(self) -> ClusterInfo:
        return ClusterInfo(
            name="fake-cluster",
            context=self.context or "fake",
            provider=CloudProvider.UNKNOWN,
            version="1.30.0",
            node_count=2,
            total_cpu_millicores=4000,
            total_memory_bytes=8 * 1024**3,
        )

    def get_namespaces(self) -> list[NamespaceInfo]:
        items = [
            NamespaceInfo(name="team-a", labels={"env": "production"}),
            NamespaceInfo(name="team-b", labels={"env": "dev"}),
        ]
        if self.namespace_filter:
            items = [ns for ns in items if ns.name in self.namespace_filter]
        return [ns for ns in items if ns.name not in self.exclude_namespaces]

    def get_all_pods(self) -> ScanResult:
        pods = [
            PodResourceInfo(
                name="api-0",
                namespace="team-a",
                workload_kind="Deployment",
                workload_name="api",
                resources=ResourceQuantities(
                    cpu_millicores_request=1000,
                    memory_bytes_request=1024 * 1024**2,
                ),
                actual=ActualUsage(
                    cpu_millicores=100,
                    memory_bytes=128 * 1024**2,
                    source=MetricSource.METRICS_SERVER,
                ),
            ),
            PodResourceInfo(
                name="worker-0",
                namespace="team-b",
                workload_kind="Deployment",
                workload_name="worker",
                resources=ResourceQuantities(
                    cpu_millicores_request=500,
                    memory_bytes_request=512 * 1024**2,
                ),
                actual=ActualUsage(
                    cpu_millicores=50,
                    memory_bytes=64 * 1024**2,
                    source=MetricSource.METRICS_SERVER,
                ),
            ),
        ]
        namespaces = {ns.name for ns in self.get_namespaces()}
        visible = [pod for pod in pods if pod.namespace in namespaces]
        return ScanResult.success(visible)


class _FailingK8sClient:
    def __init__(self, context=None, exclude_namespaces=None, namespace_filter=None, timeouts=None, retries=None) -> None:
        self.context = context

    def connect(self) -> None:
        raise RuntimeError("boom")


class _DegradedK8sClient(_FakeK8sClient):
    """Fake client whose pod scan is partial — team-b failed.

    Used by C3.2d tests to prove a partial scan sets ``degraded=True`` on
    the resulting ``TUIData`` without breaking the rest of the pipeline.
    """

    def get_all_pods(self) -> ScanResult:
        # team-a collected cleanly; team-b failed after retries.
        pods = [
            PodResourceInfo(
                name="api-0",
                namespace="team-a",
                workload_kind="Deployment",
                workload_name="api",
                resources=ResourceQuantities(
                    cpu_millicores_request=1000,
                    memory_bytes_request=1024 * 1024**2,
                ),
                actual=ActualUsage(
                    cpu_millicores=100,
                    memory_bytes=128 * 1024**2,
                    source=MetricSource.METRICS_SERVER,
                ),
            ),
        ]
        return ScanResult.partial_success(
            pods,
            ["team-b: http 503: Service Unavailable"],
        )


class _FakeApp:
    def __init__(self, config) -> None:
        self.config = config
        self.ran = False

    def run(self) -> None:
        self.ran = True


class TestConfigIntegration:
    def test_load_config_layering(self, tmp_path: Path) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text("cloud_provider: aws\ncurrency: eur\n")
        local_cfg.write_text("provider_tier: t3\ncurrency: jpy\n")
        cfg = load_config(global_path=global_cfg, local_path=local_cfg)
        assert cfg.cloud_provider == CloudProvider.AWS
        assert cfg.provider_tier == "t3"
        assert cfg.currency == Currency.JPY


class TestFakeK8sInventoryIntegration:
    def test_fake_client_filters_namespaces(self) -> None:
        client = _FakeK8sClient(exclude_namespaces={"team-b"})
        client.connect()
        namespaces = client.get_namespaces()
        pods = client.get_all_pods()
        assert client.connected is True
        assert [ns.name for ns in namespaces] == ["team-a"]
        assert len(pods.pods) == 1
        assert pods.pods[0].namespace == "team-a"


class TestTuiDataIntegration:
    def test_load_data_with_fake_collectors(self, monkeypatch) -> None:
        monkeypatch.setattr(tui_data, "K8sClient", _FakeK8sClient)
        monkeypatch.setattr(tui_data, "RuntimeCollector", _FakeRuntimeCollector)

        cfg = load_config()
        cfg.exclude_namespaces = set()
        data = tui_data.load_data(cfg)

        assert data.connected is True
        assert data.error is None
        assert data.cluster is not None
        assert data.cluster.name == "fake-cluster"
        assert data.resource_report is not None
        assert data.resource_report.total_pods == 2
        assert data.cost_report is not None
        assert data.metric_source == MetricSource.METRICS_SERVER
        assert data.metrics_available is True
        assert "integration-test-warning" in data.warnings
        assert data.loaded_at is not None

    def test_load_data_connection_failure(self, monkeypatch) -> None:
        monkeypatch.setattr(tui_data, "K8sClient", _FailingK8sClient)
        cfg = load_config()
        data = tui_data.load_data(cfg)
        assert data.connected is False
        assert data.error is not None
        assert "Connection failed" in data.error

    def test_partial_scan_sets_degraded_flag(self, monkeypatch) -> None:
        """C3.2d: a partial scan marks the snapshot degraded with the errors."""
        monkeypatch.setattr(tui_data, "K8sClient", _DegradedK8sClient)
        monkeypatch.setattr(tui_data, "RuntimeCollector", _FakeRuntimeCollector)

        cfg = load_config()
        cfg.exclude_namespaces = set()
        data = tui_data.load_data(cfg)

        # The pipeline still completes — we got partial data, not an error.
        assert data.connected is True
        assert data.error is None
        assert data.resource_report is not None
        assert data.resource_report.total_pods == 1
        # And the degraded flag + errors are surfaced for the TUI/API.
        assert data.degraded is True
        assert len(data.degraded_errors) == 1
        assert data.degraded_errors[0].startswith("team-b:")
        assert "503" in data.degraded_errors[0]

    def test_clean_scan_does_not_set_degraded(self, monkeypatch) -> None:
        """C3.2d: a fully-successful scan leaves degraded=False."""
        monkeypatch.setattr(tui_data, "K8sClient", _FakeK8sClient)
        monkeypatch.setattr(tui_data, "RuntimeCollector", _FakeRuntimeCollector)

        cfg = load_config()
        cfg.exclude_namespaces = set()
        data = tui_data.load_data(cfg)

        assert data.connected is True
        assert data.degraded is False
        assert data.degraded_errors == []


class TestCliIntegration:
    def test_cli_main_launches_app(self, monkeypatch) -> None:
        fake_app = {"instance": None}

        def _fake_import(name, *args, **kwargs):
            if name == "kube_saver.tui.app":
                class _AppModule:
                    class KubeSaverApp(_FakeApp):
                        def __init__(self, config) -> None:
                            super().__init__(config)
                            fake_app["instance"] = self
                return _AppModule()
            return original_import(name, *args, **kwargs)

        import builtins
        original_import = builtins.__import__
        monkeypatch.setattr(builtins, "__import__", _fake_import)

        from click.testing import CliRunner

        from kube_saver.cli import cli as click_cli

        runner = CliRunner()
        result = runner.invoke(click_cli, ["tui"])
        assert result.exit_code == 0
        assert fake_app["instance"] is not None
        assert fake_app["instance"].ran is True

    def test_cli_version(self) -> None:
        from click.testing import CliRunner

        from kube_saver.cli import cli as click_cli

        runner = CliRunner()
        result = runner.invoke(click_cli, ["version"])
        assert result.exit_code == 0
        assert VERSION in result.output
