"""Recommendation engine for kube-saver.

Phase 2 — Step 11.

Supports namespace-level, label-level, and annotation-level exclusion policies
to suppress recommendations for protected workloads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kube_saver.analyzers.resource_waste import PodWaste, ResourceWasteReport
from kube_saver.models.core import MetricSource, Recommendation
from kube_saver.pricing.engine import PricingEngine

if TYPE_CHECKING:
    from kube_saver.config import KubeSaverConfig


def generate_recommendations(
    report: ResourceWasteReport,
    pricing: PricingEngine,
    config: KubeSaverConfig | None = None,
) -> list[Recommendation]:
    """Generate right-sizing recommendations for every pod with waste.

    Args:
        report: The resource waste analysis result.
        pricing: The pricing engine for calculating dollar savings.
        config: Optional application config with exclusion policies.

    Returns:
        Sorted list of recommendations (highest confidence + savings first).
    """
    recs: list[Recommendation] = []

    for ns in report.namespaces:
        # Namespace-level exclusion
        if config and config.is_namespace_protected(ns.namespace.name):
            continue

        for pod_waste in ns.pod_waste:
            # Estimated samples represent missing telemetry, not observed zero
            # usage. They are useful for showing requested capacity, but must
            # never drive an actionable right-sizing recommendation.
            if pod_waste.pod.actual.source is MetricSource.ESTIMATED:
                continue

            # Pod-level exclusion via labels/annotations
            if config and config.is_pod_excluded(
                pod_waste.pod.name,
                pod_labels=pod_waste.pod.labels,
                pod_annotations=pod_waste.pod.annotations,
            ):
                continue

            recs.extend(_recommend_for_pod(pod_waste, pricing))

    recs = _consolidate_replicas(recs, pricing)

    def sort_key(rec: Recommendation) -> tuple[float, int]:
        rank = {"high": 0, "medium": 1, "low": 2}.get(rec.confidence, 3)
        return (-rec.estimated_savings.monthly_usd, rank)

    return sorted(recs, key=sort_key)


def _recommend_for_pod(pw: PodWaste, pricing: PricingEngine) -> list[Recommendation]:
    pod = pw.pod
    # Pod-level metrics cannot be divided safely among sidecars. Until
    # container-level history is available, only recommend for pods whose
    # complete usage belongs to one known container.
    if len(pod.containers) != 1:
        return []

    container_name = pod.containers[0].name
    req = pod.resources
    act = pod.actual
    recs: list[Recommendation] = []

    if req.cpu_millicores_request > 0 and pw.cpu_waste_ratio >= 0.4:
        suggested_cpu = max(act.cpu_millicores * 1.5, 50.0)
        saved_cpu = max(req.cpu_millicores_request - suggested_cpu, 0.0)
        if saved_cpu > 0:
            recs.append(
                Recommendation(
                    target_kind=pod.workload_kind,
                    target_name=pod.workload_name,
                    target_namespace=pod.namespace,
                    container_name=container_name,
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
        if saved_mem > 0:
            recs.append(
                Recommendation(
                    target_kind=pod.workload_kind,
                    target_name=pod.workload_name,
                    target_namespace=pod.namespace,
                    container_name=container_name,
                    resource_type="memory-request",
                    current_value=_fmt_bytes(req.memory_bytes_request),
                    suggested_value=_fmt_bytes(suggested_mem),
                    confidence=_confidence_from_ratio(pw.memory_waste_ratio),
                    reason=f"Memory utilization is low ({1 - pw.memory_waste_ratio:.0%} used, {pw.memory_waste_ratio:.0%} wasted)",
                    estimated_savings=pricing.cost_from_resources(0, saved_mem),
                )
            )

    return recs


def _consolidate_replicas(
    recommendations: list[Recommendation],
    pricing: PricingEngine,
) -> list[Recommendation]:
    """Return one conservative recommendation per workload resource.

    Every replica produces a pod-level observation. A workload patch affects
    all replicas, so choose the largest suggested value seen across them and
    calculate savings for applying that value to every observed replica.
    """
    grouped: dict[tuple[str, str, str, str, str], list[Recommendation]] = {}
    for rec in recommendations:
        key = (
            rec.target_namespace,
            rec.target_kind,
            rec.target_name,
            rec.container_name,
            rec.resource_type,
        )
        grouped.setdefault(key, []).append(rec)

    consolidated: list[Recommendation] = []
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    for group in grouped.values():
        selected = max(group, key=lambda rec: _value_in_base_units(rec.suggested_value))
        suggested = _value_in_base_units(selected.suggested_value)
        total_saved = sum(
            max(_value_in_base_units(rec.current_value) - suggested, 0.0)
            for rec in group
        )
        if total_saved <= 0:
            continue

        if selected.resource_type.startswith("cpu"):
            selected.estimated_savings = pricing.cost_from_resources(total_saved, 0)
        else:
            selected.estimated_savings = pricing.cost_from_resources(0, int(total_saved))
        selected.confidence = max(
            (rec.confidence for rec in group),
            key=lambda confidence: confidence_rank.get(confidence, 3),
        )
        if len(group) > 1:
            selected.reason += f"; conservative maximum across {len(group)} replicas"
        consolidated.append(selected)
    return consolidated


def _value_in_base_units(value: str) -> float:
    """Parse values emitted by this module into millicores or bytes."""
    if value.endswith("m"):
        return float(value[:-1])
    memory_units = {
        "Gi": 1024**3,
        "Mi": 1024**2,
        "Ki": 1024,
        "B": 1,
    }
    for suffix, multiplier in memory_units.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value)


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
