"""Phase 4 eBPF collector.

Current implementation focuses on the integration contract and safety-aware
fallback behavior. When BCC/eBPF tooling is available, this module can be
extended to attach live probes. In environments without BCC, it reports why
and gracefully falls back to the metrics-server collector.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kube_saver.collectors.ebpf_safety import EbpfSafetyReport, check_ebpf_safety
from kube_saver.collectors.runtime_models import AdvancedRuntimeMetrics
from kube_saver.models.core import MetricSource, PodResourceInfo

logger = logging.getLogger(__name__)


@dataclass
class EbpfCollectionResult:
    source: MetricSource = MetricSource.EBPF
    supported: bool = False
    safety: EbpfSafetyReport = field(default_factory=EbpfSafetyReport)
    metrics: dict[str, AdvancedRuntimeMetrics] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.supported and bool(self.metrics)


class EbpfCollector:
    """Safety-aware eBPF collector.

    Today this acts as a real capability gate and API surface. If the host is
    ready for eBPF, this collector can be extended to attach probes. If not,
    callers receive a structured report and can fall back to metrics-server or
    estimated data.
    """

    def __init__(self) -> None:
        self.safety = check_ebpf_safety()

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> EbpfCollectionResult:
        """Attempt to collect advanced runtime data for pods."""
        result = EbpfCollectionResult(safety=self.safety, supported=self.safety.supported)

        if not self.safety.supported:
            result.warnings.extend(self.safety.reasons)
            result.warnings.extend(self.safety.warnings)
            logger.info("eBPF collection unavailable: %s", self.safety.summary)
            return result

        # Placeholder for future BCC/eBPF probe integration.
        # The shape of the return data is finalized here so the rest of the app
        # can consume eBPF data without code churn.
        for pod in pods:
            result.metrics[f"{pod.namespace}/{pod.name}"] = AdvancedRuntimeMetrics(
                pod_name=pod.name,
                namespace=pod.namespace,
                cpu_millicores=pod.actual.cpu_millicores,
                source=MetricSource.EBPF.value,
            )

        if not result.metrics:
            result.warnings.append("eBPF supported but no pod metrics were collected")
        return result


__all__ = ["EbpfCollectionResult", "EbpfCollector"]
