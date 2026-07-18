"""Cost waste analyzer for kube-saver.

Phase 2 — Step 10.

Converts resource waste reports into dollar amounts using the pricing engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.models.core import CostInfo, ResourceWaste
from kube_saver.pricing.engine import PricingEngine


@dataclass
class NamespaceCostAnalysis:
    namespace: str
    cost_waste: CostInfo
    cpu_waste_millicores: float
    memory_waste_bytes: int
    efficiency_score: float


@dataclass
class CostWasteReport:
    total_cost_waste: CostInfo = field(default_factory=CostInfo)
    total_requested_cost: CostInfo = field(default_factory=CostInfo)
    namespaces: list[NamespaceCostAnalysis] = field(default_factory=list)

    @property
    def waste_ratio(self) -> float:
        if self.total_requested_cost.monthly_usd <= 0:
            return 0.0
        return min(self.total_cost_waste.monthly_usd / self.total_requested_cost.monthly_usd, 1.0)


def analyze_cost_waste(report: ResourceWasteReport, pricing: PricingEngine) -> CostWasteReport:
    namespaces: list[NamespaceCostAnalysis] = []

    for ns in report.namespaces:
        ns_waste = ResourceWaste(
            cpu_millicores=ns.cpu_waste_millicores,
            memory_bytes=ns.memory_waste_bytes,
        )
        namespaces.append(
            NamespaceCostAnalysis(
                namespace=ns.namespace.name,
                cost_waste=pricing.cost_from_waste(ns_waste),
                cpu_waste_millicores=ns.cpu_waste_millicores,
                memory_waste_bytes=ns.memory_waste_bytes,
                efficiency_score=ns.efficiency_score,
            )
        )

    total_waste = ResourceWaste(
        cpu_millicores=report.total_cpu_waste_millicores,
        memory_bytes=report.total_memory_waste_bytes,
    )
    total_requested = ResourceWaste(
        cpu_millicores=report.total_cpu_request_millicores,
        memory_bytes=report.total_memory_request_bytes,
    )

    namespaces.sort(key=lambda n: n.cost_waste.monthly_usd, reverse=True)

    return CostWasteReport(
        total_cost_waste=pricing.cost_from_waste(total_waste),
        total_requested_cost=pricing.cost_from_waste(total_requested),
        namespaces=namespaces,
    )
