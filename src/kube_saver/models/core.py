"""Core data models for kube-saver.

These dataclasses are the foundation of the entire system.
All collectors, analyzers, recommenders, and exporters exchange data
through these well-defined types.

Units:
- CPU is always in millicores (1000m = 1 full core)
- Memory is always in bytes
- Currency is configurable (default USD)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CloudProvider(str, Enum):
    """Cloud provider for cost calculations."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ON_PREM = "on-prem"
    UNKNOWN = "unknown"


class MetricSource(str, Enum):
    """Source of the metric data."""

    METRICS_SERVER = "metrics-server"
    EBPF = "ebpf"
    CADVISOR = "cAdvisor"
    ESTIMATED = "estimated"


class Currency(str, Enum):
    """Supported currencies for cost display."""

    USD = "usd"
    EUR = "eur"
    GBP = "gbp"
    AED = "aed"
    JPY = "jpy"
    INR = "inr"

    @property
    def symbol(self) -> str:
        """Return the currency symbol for display."""
        symbols = {
            Currency.USD: "$",
            Currency.EUR: "€",
            Currency.GBP: "£",
            Currency.AED: "د.إ",
            Currency.JPY: "¥",
            Currency.INR: "₹",
        }
        return symbols[self]

    @property
    def code(self) -> str:
        """Return the ISO currency code."""
        return self.value.upper()


@dataclass
class Money:
    """A currency-aware amount for display."""

    amount: float = 0.0
    currency: Currency = Currency.USD

    @property
    def formatted(self) -> str:
        """Return formatted string like '$62.05' or '€57.09'."""
        return f"{self.currency.symbol}{self.amount:.2f}"

    @property
    def yearly_formatted(self) -> str:
        """Return yearly formatted string."""
        return f"{self.currency.symbol}{self.amount * 12:.2f}"

    def __repr__(self) -> str:
        return self.formatted


@dataclass
class ClusterInfo:
    """Information about a Kubernetes cluster.

    Attributes:
        name: Human-readable cluster name.
        context: kubeconfig context name.
        provider: Cloud provider hosting this cluster.
        version: Kubernetes version (e.g., "1.29.0").
        node_count: Number of worker nodes.
        total_cpu_millicores: Cluster-wide allocatable CPU in millicores.
        total_memory_bytes: Cluster-wide allocatable memory in bytes.
    """

    name: str
    context: str
    provider: CloudProvider = CloudProvider.UNKNOWN
    version: str = "unknown"
    node_count: int = 0
    total_cpu_millicores: int = 0
    total_memory_bytes: int = 0


@dataclass
class ResourceQuantities:
    """Resource quantities for a Kubernetes workload component.

    Attribute convention:
    - request: what the workload asks for (guaranteed allocation)
    - limit: the hard cap the workload cannot exceed
    """

    cpu_millicores_request: float = 0.0
    cpu_millicores_limit: float = 0.0
    memory_bytes_request: int = 0
    memory_bytes_limit: int = 0

    @property
    def has_requests(self) -> bool:
        """Return True if either CPU or memory requests are set."""
        return self.cpu_millicores_request > 0 or self.memory_bytes_request > 0

    @property
    def has_limits(self) -> bool:
        """Return True if either CPU or memory limits are set."""
        return self.cpu_millicores_limit > 0 or self.memory_bytes_limit > 0


@dataclass
class NamespaceInfo:
    """Aggregated information for a Kubernetes namespace.

    Attributes:
        name: Namespace name.
        labels: Namespace labels (key-value).
        pod_count: Number of pods currently running.
        resources: Aggregated resource quantities for the namespace.
        annotation_is_production: True if labeled production-like.
    """

    name: str
    labels: dict[str, str] = field(default_factory=dict)
    pod_count: int = 0
    resources: ResourceQuantities = field(default_factory=ResourceQuantities)

    @property
    def is_production(self) -> bool:
        """Heuristically determine if this is a production namespace."""
        production_indicators = {"prod", "production", "live"}
        for value in self.labels.values():
            if value.lower() in production_indicators:
                return True
        return self.name.lower() in production_indicators


@dataclass
class ActualUsage:
    """Measured CPU/memory usage from metrics-server or eBPF.

    Attributes:
        cpu_millicores: Average CPU usage across the observation window.
        memory_bytes: Average working-set memory usage.
        source: Where this measurement came from.
        observed_at: Timestamp of the measurement.
        sample_count: Number of samples used to compute the average.
    """

    cpu_millicores: float = 0.0
    memory_bytes: int = 0
    source: MetricSource = MetricSource.ESTIMATED
    observed_at: datetime = field(default_factory=datetime.now)
    sample_count: int = 1


@dataclass
class PodResourceInfo:
    """Resource information for a single pod.

    Combines static request/limit with dynamic actual-usage data.

    Attributes:
        name: Pod name.
        namespace: Owning namespace.
        node_name: Node the pod runs on (None if unscheduled).
        workload_kind: Owning controller (Deployment, StatefulSet, etc.).
        workload_name: Owning controller name.
        containers: Resource data per container.
        resources: Aggregated resources across all containers in the pod.
        actual: Measured usage for the pod.
        restart_count: Number of container restarts (OOMs show up here).
    """

    name: str
    namespace: str = ""
    node_name: Optional[str] = None
    workload_kind: str = "Unknown"
    workload_name: str = ""
    containers: list[ContainerResourceInfo] = field(default_factory=list)
    resources: ResourceQuantities = field(default_factory=ResourceQuantities)
    actual: ActualUsage = field(default_factory=ActualUsage)
    restart_count: int = 0

    @property
    def had_oom_events(self) -> bool:
        """Return True if any container was restarted recently (possible OOM)."""
        return self.restart_count > 0


@dataclass
class ContainerResourceInfo:
    """Resource info for a single container within a pod.

    Attributes:
        name: Container name.
        resources: Container's resource requests and limits.
        actual: Container-level measured usage.
    """

    name: str
    resources: ResourceQuantities = field(default_factory=ResourceQuantities)
    actual: ActualUsage = field(default_factory=ActualUsage)


@dataclass
class CostInfo:
    """Cost information expressed in USD.

    All amounts are USD. Duration-based costs are scaled by the caller.

    Attributes:
        hourly_usd: Cost per hour, USD.
        daily_usd: Cost per day, USD (hourly * 24).
        monthly_usd: Cost per month, USD (hourly * 730, AWS standard).
        yearly_usd: Cost per year, USD (monthly * 12).
    """

    hourly_usd: float = 0.0
    daily_usd: float = 0.0
    monthly_usd: float = 0.0
    yearly_usd: float = 0.0

    @classmethod
    def from_hourly(cls, hourly: float) -> CostInfo:
        """Build CostInfo from a single hourly USD amount."""
        return cls(
            hourly_usd=hourly,
            daily_usd=hourly * 24,
            monthly_usd=hourly * 730,
            yearly_usd=hourly * 730 * 12,
        )

    def __add__(self, other: CostInfo) -> CostInfo:
        """Add two CostInfo objects element-wise."""
        if not isinstance(other, CostInfo):
            return NotImplemented
        return CostInfo(
            hourly_usd=self.hourly_usd + other.hourly_usd,
            daily_usd=self.daily_usd + other.daily_usd,
            monthly_usd=self.monthly_usd + other.monthly_usd,
            yearly_usd=self.yearly_usd + other.yearly_usd,
        )


@dataclass
class ResourceWaste:
    """Amount of waste for a single resource dimension.

    Attributes:
        cpu_millicores: Wasted CPU (request - actual).
        memory_bytes: Wasted memory (request - actual).
    """

    cpu_millicores: float = 0.0
    memory_bytes: int = 0


@dataclass
class Recommendation:
    """A single resource tuning recommendation.

    Attributes:
        target_kind: 'Deployment', 'StatefulSet', etc.
        target_name: Name of the workload.
        target_namespace: Owning namespace.
        container_name: Container within the workload.
        resource_type: 'cpu-request', 'cpu-limit', 'memory-request', etc.
        current_value: Current value as parsed string (e.g., '500m', '256Mi').
        suggested_value: Proposed value as parsed string.
        confidence: Confidence level (high/medium/low).
        reason: Human-readable rationale for the suggestion.
        estimated_savings: Estimated monthly savings if applied.
    """

    target_kind: str = "Deployment"
    target_name: str = ""
    target_namespace: str = ""
    container_name: str = ""
    resource_type: str = ""
    current_value: str = ""
    suggested_value: str = ""
    confidence: str = "medium"
    reason: str = ""
    estimated_savings: CostInfo = field(default_factory=CostInfo)


@dataclass
class WasteReport:
    """Aggregate report of waste across the cluster or a subset.

    Attributes:
        cluster: Cluster this report covers.
        generated_at: Timestamp of report generation.
        total_pods: Pod count included in the report.
        waste: Total waste amounts.
        cost_waste: Cost impact of the waste.
        recommendations: All actionable recommendations.
        namespaces_breakdown: Per-namespace waste for ranked display.
    """

    cluster: ClusterInfo = field(default_factory=ClusterInfo)
    generated_at: datetime = field(default_factory=datetime.now)
    total_pods: int = 0
    waste: ResourceWaste = field(default_factory=ResourceWaste)
    cost_waste: CostInfo = field(default_factory=CostInfo)
    recommendations: list[Recommendation] = field(default_factory=list)
    namespaces_breakdown: list[NamespaceWaste] = field(default_factory=list)


@dataclass
class NamespaceWaste:
    """Per-namespace waste summary.

    Attributes:
        namespace: Source namespace.
        pod_count: Number of pods in the namespace.
        waste: Aggregate waste in the namespace.
        cost_waste: Cost impact for the namespace.
        efficiency_score: 0-100 efficiency rating (higher is better).
    """

    namespace: NamespaceInfo
    pod_count: int = 0
    waste: ResourceWaste = field(default_factory=ResourceWaste)
    cost_waste: CostInfo = field(default_factory=CostInfo)
    efficiency_score: float = 100.0


__all__ = [
    "CloudProvider",
    "MetricSource",
    "ClusterInfo",
    "ResourceQuantities",
    "NamespaceInfo",
    "ActualUsage",
    "PodResourceInfo",
    "ContainerResourceInfo",
    "CostInfo",
    "ResourceWaste",
    "Recommendation",
    "WasteReport",
    "NamespaceWaste",
]
