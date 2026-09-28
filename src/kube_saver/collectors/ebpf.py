"""Safety-aware placeholder for a future eBPF collector.

Capability detection is implemented, but live probes are not. This collector
therefore always reports itself unavailable so callers continue to the real
metrics-server source instead of mistaking default values for eBPF samples.
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
    """Capability gate that safely falls through until probes are implemented."""

    def __init__(self) -> None:
        self.safety = check_ebpf_safety()

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> EbpfCollectionResult:
        """Attempt to collect advanced runtime data for pods."""
        result = EbpfCollectionResult(safety=self.safety, supported=False)

        if not self.safety.supported:
            result.warnings.extend(self.safety.reasons)
            result.warnings.extend(self.safety.warnings)
            logger.info("eBPF collection unavailable: %s", self.safety.summary)
            return result

        result.warnings.extend(self.safety.warnings)
        result.warnings.append(
            "eBPF probes are not implemented; using metrics-server when available"
        )
        return result


__all__ = ["EbpfCollectionResult", "EbpfCollector"]
