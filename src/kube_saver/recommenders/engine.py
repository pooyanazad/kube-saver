"""Recommendation engine for kube-saver.

Phase 2 — Step 11.
"""

from __future__ import annotations

from dataclasses import dataclass

from kube_saver.analyzers.resource_waste import PodWaste, ResourceWasteReport
from kube_saver.models.core import CostInfo, Recommendation
from kube_saver.pricing.engine import PricingEngine


def generate_recommendations(report: ResourceWasteReport, pricing: PricingEngine) -> list[Recommendation]:
    recs: list[Recommendation] = []

    for ns in report.namespaces:
        for pod_waste in ns.pod_waste:
            recs.extend(_recommend_for_pod(pod_waste, pricing))

    def sort_key(rec: Recommendation) -> tuple[float, int]:
        rank = {"high": 0, "medium": 1, "low": 2}.get(rec.confidence, 3)
        return (-rec.estimated_savings.monthly_usd, rank)

    return sorted(recs, key=sort_key)


def _recommend_for_pod(pw: PodWaste, pricing: PricingEngine) -> list[Recommendation]:
    pod = pw.pod
    req = pod.resources
    act = pod.actual
    recs: list[Recommendation] = []

    if req.cpu_millicores_request > 0 and pw.cpu_waste_ratio >= 0.4:
        suggested_cpu = max(act.cpu_millicores * 1.5, 50.0)
        saved_cpu = max(req.cpu_millicores_request - suggested_cpu, 0.0)
        recs.append(
            Recommendation(
                target_kind=pod.workload_kind,
                target_name=pod.workload_name,
                target_namespace=pod.namespace,
                container_name=pod.name,
                resource_type="cpu-request",
                current_value=f"{int(req.cpu_millicores_request)}m",
                suggested_value=f"{int(suggested_cpu)}m",
                confidence=_confidence_from_ratio(pw.cpu_waste_ratio),
                reason=f"CPU utilization is low ({1 - pw.cpu_waste_ratio:.0%} used, {pw.cpu_waste_ratio:.0%} wasted)",
                estimated_savings=pricing.cost_from_resources(saved_cpu, 0),
            )
        )

    if req.memory_bytes_request > 0 and pw.memory_waste_ratio >= 0.4:
        suggested_mem = max(int(act.memory_bytes * 1.2), 64 * 1024**2)
        saved_mem = max(req.memory_bytes_request - suggested_mem, 0)
        recs.append(
            Recommendation(
                target_kind=pod.workload_kind,
                target_name=pod.workload_name,
                target_namespace=pod.namespace,
                container_name=pod.name,
                resource_type="memory-request",
                current_value=_fmt_bytes(req.memory_bytes_request),
                suggested_value=_fmt_bytes(suggested_mem),
                confidence=_confidence_from_ratio(pw.memory_waste_ratio),
                reason=f"Memory utilization is low ({1 - pw.memory_waste_ratio:.0%} used, {pw.memory_waste_ratio:.0%} wasted)",
                estimated_savings=pricing.cost_from_resources(0, saved_mem),
            )
        )

    return recs


def _confidence_from_ratio(ratio: float) -> str:
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.6:
        return "medium"
    return "low"


def _fmt_bytes(b: int) -> str:
    if b >= 1024**3:
        return f"{b / 1024**3:.1f}Gi"
    if b >= 1024**2:
        return f"{b / 1024**2:.0f}Mi"
    return f"{b}B"
