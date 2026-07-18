"""kube-saver analyzers — cost and waste analysis logic.

Phase 2 exports:
    - resource waste analysis
    - cost waste analysis
    - health scoring
    - alert evaluation
"""

from kube_saver.analyzers.alerts import Alert, evaluate_alerts
from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis, analyze_cost_waste
from kube_saver.analyzers.health import pod_health_score
from kube_saver.analyzers.resource_waste import (
    DeploymentWaste,
    NamespaceAnalysis,
    PodWaste,
    ResourceWasteReport,
    analyze_resource_waste,
)

__all__ = [
    "Alert",
    "CostWasteReport",
    "DeploymentWaste",
    "NamespaceAnalysis",
    "NamespaceCostAnalysis",
    "PodWaste",
    "ResourceWasteReport",
    "analyze_cost_waste",
    "analyze_resource_waste",
    "evaluate_alerts",
    "pod_health_score",
]

