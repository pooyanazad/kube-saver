"""Resource waste analyzer for kube-saver.

Phase 2 — Step 9 / Step 14.

Computes resource waste as:

    waste = max(request - actual_usage, 0)

and aggregates results per pod, per deployment, and per namespace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from kube_saver.models.core import (
    ActualUsage,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
    ResourceWaste,
)


@dataclass
class PodWaste:
    """Resource waste for a single pod."""

    pod: PodResourceInfo
    cpu_waste_millicores: float = 0.0
    memory_waste_bytes: int = 0
    cpu_waste_ratio: float = 0.0
    memory_waste_ratio: float = 0.0
    has_usage_data: bool = False


@dataclass
class DeploymentWaste:
    """Aggregated waste for a deployment / workload."""

    name: str
    namespace: str
    kind: str = "Deployment"
    pod_count: int = 0
    cpu_waste_millicores: float = 0.0
    memory_waste_bytes: int = 0
    pods: list[PodWaste] = field(default_factory=list)

    @property
    def avg_cpu_waste_millicores(self) -> float:
        return self.cpu_waste_millicores / max(self.pod_count, 1)

    @property
    def avg_memory_waste_bytes(self) -> float:
        return self.memory_waste_bytes / max(self.pod_count, 1)


@dataclass
class NamespaceAnalysis:
    """Aggregated waste for a namespace."""

    namespace: NamespaceInfo
    pod_count: int = 0
    pod_waste: list[PodWaste] = field(default_factory=list)
    deployments: list[DeploymentWaste] = field(default_factory=list)
    cpu_waste_millicores: float = 0.0
    memory_waste_bytes: int = 0
    cpu_request_millicores: float = 0.0
    memory_request_bytes: int = 0
    efficiency_score: float = 100.0


@dataclass
class ResourceWasteReport:
    """Full cluster resource-waste report."""

    namespaces: list[NamespaceAnalysis] = field(default_factory=list)
    total_cpu_waste_millicores: float = 0.0
    total_memory_waste_bytes: int = 0
    total_cpu_request_millicores: float = 0.0
    total_memory_request_bytes: int = 0
    total_pods: int = 0
    metrics_available: bool = False
    has_real_usage: bool = False

    @property
    def overall_efficiency(self) -> float:
        req = max(self.total_cpu_request_millicores, 1.0)
        return round((req - self.total_cpu_waste_millicores) / req * 100, 1)


def analyze_resource_waste(
    namespaces: list[NamespaceInfo],
    pods: list[PodResourceInfo],
    metrics_available: bool,
) -> ResourceWasteReport:
    """Build a full resource waste report from collected Kubernetes state."""
    pods_by_namespace: dict[str, list[PodResourceInfo]] = {}
    for pod in pods:
        pods_by_namespace.setdefault(pod.namespace, []).append(pod)

    report = ResourceWasteReport(
        namespaces=[],
        metrics_available=metrics_available,
        has_real_usage=metrics_available and any(
            pod.actual.cpu_millicores > 0 or pod.actual.memory_bytes > 0 for pod in pods
        ),
    )

    for ns in namespaces:
        ns_pods = pods_by_namespace.get(ns.name, [])
        ns_analysis = NamespaceAnalysis(
            namespace=ns,
            pod_count=len(ns_pods),
        )

        waste_by_workload: dict[str, DeploymentWaste] = {}

        for pod in ns_pods:
            pw = _analyze_pod(pod)
            ns_analysis.pod_waste.append(pw)
            ns_analysis.cpu_waste_millicores += pw.cpu_waste_millicores
            ns_analysis.memory_waste_bytes += pw.memory_waste_bytes
            ns_analysis.cpu_request_millicores += pod.resources.cpu_millicores_request
            ns_analysis.memory_request_bytes += pod.resources.memory_bytes_request

            workload_key = f"{pod.workload_kind}/{pod.workload_name}"
            if workload_key not in waste_by_workload:
                waste_by_workload[workload_key] = DeploymentWaste(
                    name=pod.workload_name,
                    namespace=ns.name,
                    kind=pod.workload_kind,
                )
            dw = waste_by_workload[workload_key]
            dw.pod_count += 1
            dw.cpu_waste_millicores += pw.cpu_waste_millicores
            dw.memory_waste_bytes += pw.memory_waste_bytes
            dw.pods.append(pw)

        ns_analysis.deployments = sorted(
            waste_by_workload.values(), key=lambda d: d.cpu_waste_millicores, reverse=True
        )

        ns_analysis.efficiency_score = _score_efficiency(
            ns_analysis.cpu_waste_millicores,
            ns_analysis.cpu_request_millicores,
        )

        report.namespaces.append(ns_analysis)
        report.total_pods += ns_analysis.pod_count
        report.total_cpu_waste_millicores += ns_analysis.cpu_waste_millicores
        report.total_memory_waste_bytes += ns_analysis.memory_waste_bytes
        report.total_cpu_request_millicores += ns_analysis.cpu_request_millicores
        report.total_memory_request_bytes += ns_analysis.memory_request_bytes

    report.namespaces.sort(key=lambda n: n.cpu_waste_millicores, reverse=True)
    return report


def _analyze_pod(pod: PodResourceInfo) -> PodWaste:
    """Compute waste for a single pod."""
    req = pod.resources
    act = pod.actual
    has_usage = act.cpu_millicores > 0 or act.memory_bytes > 0

    cpu_waste = max(req.cpu_millicores_request - act.cpu_millicores, 0) if has_usage else req.cpu_millicores_request
    mem_waste = max(req.memory_bytes_request - act.memory_bytes, 0) if has_usage else req.memory_bytes_request

    cpu_ratio = cpu_waste / req.cpu_millicores_request if req.cpu_millicores_request else 0.0
    mem_ratio = mem_waste / req.memory_bytes_request if req.memory_bytes_request else 0.0

    return PodWaste(
        pod=pod,
        cpu_waste_millicores=cpu_waste,
        memory_waste_bytes=mem_waste,
        cpu_waste_ratio=min(max(cpu_ratio, 0.0), 1.0),
        memory_waste_ratio=min(max(mem_ratio, 0.0), 1.0),
        has_usage_data=has_usage,
    )


def _score_efficiency(waste_cpu_millicores: float, request_cpu_millicores: float) -> float:
    if request_cpu_millicores <= 0:
        return 100.0
    used = request_cpu_millicores - waste_cpu_millicores
    score = used / request_cpu_millicores * 100
    return round(max(min(score, 100.0), 0.0), 1)
