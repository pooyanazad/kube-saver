"""Prometheus exposition helpers for kube-saver."""

from __future__ import annotations

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport


def render_prometheus_metrics(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
) -> str:
    """Render waste metrics in Prometheus text exposition format."""
    lines = [
        "# HELP kube_saver_waste_cpu_millicores Total CPU waste in millicores",
        "# TYPE kube_saver_waste_cpu_millicores gauge",
        f"kube_saver_waste_cpu_millicores {resource_report.total_cpu_waste_millicores:.3f}",
        "# HELP kube_saver_waste_memory_bytes Total memory waste in bytes",
        "# TYPE kube_saver_waste_memory_bytes gauge",
        f"kube_saver_waste_memory_bytes {resource_report.total_memory_waste_bytes}",
        "# HELP kube_saver_cost_waste_monthly_usd Total monthly waste in USD",
        "# TYPE kube_saver_cost_waste_monthly_usd gauge",
        f"kube_saver_cost_waste_monthly_usd {cost_report.total_cost_waste.monthly_usd:.6f}",
        "# HELP kube_saver_efficiency_score Overall cluster efficiency score",
        "# TYPE kube_saver_efficiency_score gauge",
        f"kube_saver_efficiency_score {resource_report.overall_efficiency:.3f}",
    ]

    for ns in cost_report.namespaces:
        namespace = ns.namespace.replace('"', '\\"')
        lines.append(
            f'kube_saver_namespace_cost_waste_monthly_usd{{namespace="{namespace}"}} {ns.cost_waste.monthly_usd:.6f}'
        )
        lines.append(
            f'kube_saver_namespace_efficiency_score{{namespace="{namespace}"}} {ns.efficiency_score:.3f}'
        )
    return "\n".join(lines) + "\n"


__all__ = ["render_prometheus_metrics"]
