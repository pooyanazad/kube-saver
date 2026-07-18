"""Unified runtime collector for Phase 4.

Implements the fallback chain:
    1. eBPF (best accuracy)
    2. metrics-server
    3. estimated zero-usage data
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kube_saver.collectors.ebpf import EbpfCollector, EbpfCollectionResult
from kube_saver.collectors.metrics import MetricsCollector
from kube_saver.collectors.runtime_models import AdvancedRuntimeMetrics, DiskIO, MemoryBreakdown, NetworkIO
from kube_saver.models.core import ActualUsage, MetricSource, PodResourceInfo


@dataclass
class RuntimeCollectionResult:
    source: MetricSource = MetricSource.ESTIMATED
    metrics_available: bool = False
    used_fallback: bool = False
    warnings: list[str] = field(default_factory=list)
    advanced_metrics: dict[str, AdvancedRuntimeMetrics] = field(default_factory=dict)


class RuntimeCollector:
    """Runtime collector with eBPF-first fallback behavior."""

    def __init__(self, prefer_ebpf: bool = True) -> None:
        self.prefer_ebpf = prefer_ebpf
        self.ebpf = EbpfCollector()
        self.metrics = MetricsCollector()

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> RuntimeCollectionResult:
        result = RuntimeCollectionResult()

        if self.prefer_ebpf:
            ebpf_result = self.ebpf.collect_all_pods(pods)
            if ebpf_result.available:
                result.source = MetricSource.EBPF
                result.metrics_available = True
                result.advanced_metrics = ebpf_result.metrics
                result.warnings.extend(ebpf_result.warnings)
                for pod in pods:
                    key = f"{pod.namespace}/{pod.name}"
                    if key in ebpf_result.metrics:
                        pod.actual.source = MetricSource.EBPF
                        pod.actual.cpu_millicores = ebpf_result.metrics[key].cpu_millicores
                return result
            result.used_fallback = True
            result.warnings.extend(ebpf_result.warnings)

        metric_map = self.metrics.collect_all_pods(pods)
        if self.metrics.available:
            result.source = MetricSource.METRICS_SERVER
            result.metrics_available = True
            for pod in pods:
                key = f"{pod.namespace}/{pod.name}"
                usage = metric_map.get(pod.name)
                if usage is None:
                    usage = pod.actual
                result.advanced_metrics[key] = AdvancedRuntimeMetrics(
                    pod_name=pod.name,
                    namespace=pod.namespace,
                    cpu_millicores=usage.cpu_millicores,
                    memory=MemoryBreakdown(working_set_bytes=usage.memory_bytes),
                    network=NetworkIO(),
                    disk=DiskIO(),
                    source=MetricSource.METRICS_SERVER.value,
                    idle_hint=usage.cpu_millicores == 0 and usage.memory_bytes < 16 * 1024**2,
                )
            return result

        result.source = MetricSource.ESTIMATED
        result.metrics_available = False
        result.used_fallback = True
        result.warnings.append("metrics-server unavailable; using estimated zero-usage data")
        for pod in pods:
            pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
            key = f"{pod.namespace}/{pod.name}"
            result.advanced_metrics[key] = AdvancedRuntimeMetrics(
                pod_name=pod.name,
                namespace=pod.namespace,
                source=MetricSource.ESTIMATED.value,
                idle_hint=True,
            )
        return result


__all__ = ["RuntimeCollectionResult", "RuntimeCollector"]
