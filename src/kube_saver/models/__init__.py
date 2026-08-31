"""kube-saver models — core data structures (dataclasses).

All models are defined in ``kube_saver.models.core`` and re-exported here
for convenient access: ``from kube_saver.models import ClusterInfo, ...``.
"""

from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ClusterInfo,
    ContainerResourceInfo,
    CostInfo,
    MetricSource,
    NamespaceInfo,
    NamespaceWaste,
    PodResourceInfo,
    Recommendation,
    ResourceQuantities,
    ResourceWaste,
    ScanResult,
    WasteReport,
)

__all__ = [
    "ActualUsage",
    "CloudProvider",
    "ClusterInfo",
    "ContainerResourceInfo",
    "CostInfo",
    "MetricSource",
    "NamespaceInfo",
    "NamespaceWaste",
    "PodResourceInfo",
    "Recommendation",
    "ResourceQuantities",
    "ResourceWaste",
    "ScanResult",
    "WasteReport",
]
