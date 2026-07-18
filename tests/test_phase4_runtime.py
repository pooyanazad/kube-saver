"""Tests for Phase 4 runtime collection and eBPF fallback."""

from kube_saver.collectors.ebpf import EbpfCollector
from kube_saver.collectors.ebpf_safety import check_ebpf_safety
from kube_saver.collectors.runtime import RuntimeCollector
from kube_saver.models.core import (
    ActualUsage,
    MetricSource,
    PodResourceInfo,
    ResourceQuantities,
)


def _pod(name: str = "demo", namespace: str = "default") -> PodResourceInfo:
    return PodResourceInfo(
        name=name,
        namespace=namespace,
        workload_kind="Deployment",
        workload_name="demo",
        resources=ResourceQuantities(
            cpu_millicores_request=500,
            memory_bytes_request=256 * 1024**2,
        ),
        actual=ActualUsage(cpu_millicores=25, memory_bytes=32 * 1024**2, source=MetricSource.METRICS_SERVER),
    )


def test_ebpf_safety_report_has_summary() -> None:
    report = check_ebpf_safety()
    assert isinstance(report.summary, str)
    assert report.kernel_version


def test_ebpf_collector_returns_structured_result() -> None:
    collector = EbpfCollector()
    result = collector.collect_all_pods([_pod()])
    assert result.safety.kernel_version
    assert isinstance(result.warnings, list)
    if not result.supported:
        assert result.available is False


def test_runtime_collector_falls_back_cleanly() -> None:
    collector = RuntimeCollector(prefer_ebpf=True)
    collector.metrics.collect_all_pods = lambda pods: {p.name: p.actual for p in pods}
    collector.metrics.available = True
    pods = [_pod()]
    result = collector.collect_all_pods(pods)
    assert result.source in {MetricSource.EBPF, MetricSource.METRICS_SERVER, MetricSource.ESTIMATED}
    assert isinstance(result.advanced_metrics, dict)
    assert len(result.advanced_metrics) == 1


def test_runtime_collector_builds_metric_key() -> None:
    collector = RuntimeCollector(prefer_ebpf=False)
    collector.metrics.collect_all_pods = lambda pods: {p.name: p.actual for p in pods}
    collector.metrics.available = True
    pods = [_pod(name="demo-pod", namespace="apps")]
    result = collector.collect_all_pods(pods)
    assert "apps/demo-pod" in result.advanced_metrics


def test_runtime_collector_uses_estimated_when_no_metrics() -> None:
    collector = RuntimeCollector(prefer_ebpf=False)
    collector.metrics.collect_all_pods = lambda pods: {}
    collector.metrics.available = False
    pods = [_pod()]
    result = collector.collect_all_pods(pods)
    assert result.source in {MetricSource.METRICS_SERVER, MetricSource.ESTIMATED}
