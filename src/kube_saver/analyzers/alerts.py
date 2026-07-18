"""Alert evaluation for kube-saver.

Phase 2 — Step 16.
"""

from __future__ import annotations

from dataclasses import dataclass

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.config import AlertConfig


@dataclass
class Alert:
    level: str
    scope: str
    target: str
    message: str


def evaluate_alerts(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
    config: AlertConfig,
) -> list[Alert]:
    alerts: list[Alert] = []

    if cost_report.total_cost_waste.monthly_usd >= config.critical_monthly_usd:
        alerts.append(Alert("critical", "cluster", "all", f"Monthly waste is ${cost_report.total_cost_waste.monthly_usd:.2f}"))
    elif cost_report.total_cost_waste.monthly_usd >= config.warning_monthly_usd:
        alerts.append(Alert("warning", "cluster", "all", f"Monthly waste is ${cost_report.total_cost_waste.monthly_usd:.2f}"))

    for ns in resource_report.namespaces:
        cpu_ratio = ns.cpu_waste_millicores / ns.cpu_request_millicores if ns.cpu_request_millicores > 0 else 0.0
        if cpu_ratio >= config.critical_waste_ratio:
            alerts.append(Alert("critical", "namespace", ns.namespace.name, f"CPU waste is {cpu_ratio:.0%}"))
        elif cpu_ratio >= config.warning_waste_ratio:
            alerts.append(Alert("warning", "namespace", ns.namespace.name, f"CPU waste is {cpu_ratio:.0%}"))

    return alerts
