"""Recommendation engine for kube-saver.

Phase 2 — Step 11.

Supports namespace-level, label-level, and annotation-level exclusion policies
to suppress recommendations for protected workloads.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from kube_saver.analyzers.resource_waste import PodWaste, ResourceWasteReport
from kube_saver.config import SafetyConfig
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
    safety = config.safety.normalized() if config else SafetyConfig(
        min_cpu_millicores=50, min_memory_bytes=64 * 1024**2, aggressive_mode=True
    )
    workloads: dict[tuple[str, str, str], list[PodWaste]] = {}

    for ns in report.namespaces:
        # Namespace-level exclusion
        if config and config.is_namespace_protected(ns.namespace.name):
            continue

        for pod_waste in ns.pod_waste:
            pod = pod_waste.pod
            key = (pod.namespace, pod.workload_kind, pod.workload_name)
            workloads.setdefault(key, []).append(pod_waste)

    for observations in workloads.values():
        # A controller patch affects every replica, including siblings that
        # would not independently generate a recommendation.
        if any(
            pw.pod.actual.source is MetricSource.ESTIMATED
            or len(pw.pod.containers) != 1
            or (config and config.is_pod_excluded(
                pw.pod.name, pw.pod.labels, pw.pod.annotations
            ))
            for pw in observations
        ):
            continue
        if len({pw.pod.containers[0].name for pw in observations}) != 1:
            continue
        candidates = [
            rec for pw in observations
            for rec in _recommend_for_pod(pw, pricing, safety)
        ]
        recs.extend(_consolidate_replicas(candidates, pricing, observations, safety))

    def sort_key(rec: Recommendation) -> tuple[float, int]:
        rank = {"high": 0, "medium": 1, "low": 2}.get(rec.confidence, 3)
        return (-rec.estimated_savings.monthly_usd, rank)

    return sorted(recs, key=sort_key)


def _suggested_resources(pw: PodWaste, safety: SafetyConfig) -> tuple[int, int]:
    pod = pw.pod
    cpu = max(pod.actual.cpu_millicores * 1.5, safety.min_cpu_millicores)
    memory = max(pod.actual.memory_bytes * 1.2, safety.min_memory_bytes)
    if not safety.aggressive_mode:
        cpu = max(cpu, pod.resources.cpu_millicores_request * safety.prod_cpu_floor_ratio)
        memory = max(memory, pod.resources.memory_bytes_request * safety.prod_memory_floor_ratio)
    # Round upwards in the emitted units so formatting cannot erode headroom.
    return math.ceil(cpu), math.ceil(memory / 1024**2) * 1024**2


def _recommend_for_pod(
    pw: PodWaste, pricing: PricingEngine, safety: SafetyConfig
) -> list[Recommendation]:
    pod = pw.pod
    # Pod-level metrics cannot be divided safely among sidecars. Until
    # container-level history is available, only recommend for pods whose
    # complete usage belongs to one known container.
    if len(pod.containers) != 1:
        return []

    container_name = pod.containers[0].name
    req = pod.resources
    recs: list[Recommendation] = []
    suggested_cpu, suggested_mem = _suggested_resources(pw, safety)

    if req.cpu_millicores_request > 0 and pw.cpu_waste_ratio >= 0.4:
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
    observations: list[PodWaste],
    safety: SafetyConfig,
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
        cpu = selected.resource_type.startswith("cpu")
        values = [_suggested_resources(pw, safety)[0 if cpu else 1] for pw in observations]
        suggested = max(values)
        requests = [
            pw.pod.resources.cpu_millicores_request if cpu
            else pw.pod.resources.memory_bytes_request
            for pw in observations
        ]
        # Never turn a downsize candidate into an increase for another replica.
        if any(suggested >= request for request in requests):
            continue
        selected.suggested_value = f"{suggested}m" if cpu else _fmt_bytes(suggested)
        total_saved = sum(
            max(request - suggested, 0.0) for request in requests
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
        if len(observations) > 1:
            selected.reason += f"; conservative maximum across {len(observations)} replicas"
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
    if b >= 1024**2:
        return f"{math.ceil(b / 1024**2)}Mi"
    return f"{b}B"
