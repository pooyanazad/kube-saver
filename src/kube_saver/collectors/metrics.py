"""Metrics collector for kube-saver.

Queries the Kubernetes Metrics API (metrics-server) to populate actual
CPU/memory usage on ``PodResourceInfo`` objects.

Falls back gracefully when metrics-server is unavailable: pods keep
``MetricSource.ESTIMATED`` and zero actual usage, so waste calculations
still run (they will just report all requests as "wasted").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from kube_saver.models.core import (
    ActualUsage,
    MetricSource,
    PodResourceInfo,
    ResourceQuantities,
)

logger = logging.getLogger(__name__)

try:
    from kube_saver.collectors.k8s_client import (
        _K8S_AVAILABLE,
        _parse_cpu_to_millicores,
        _parse_memory_to_bytes,
    )
except ImportError:
    _K8S_AVAILABLE = False

try:
    from kubernetes import client as k8s_client  # type: ignore[import-untyped]
    from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]
except ImportError:
    k8s_client = None

    class ApiException(Exception):  # type: ignore[no-redef]  # noqa: N818
        pass


@dataclass(frozen=True)
class MetricSample:
    """A single pod metric sample returned by the Metrics API.

    Attributes:
        cpu_millicores: Total CPU usage across the pod's containers.
        memory_bytes: Total memory usage across the pod's containers.
        collected_at: Timestamp supplied by metrics-server for this sample.
    """

    cpu_millicores: float
    memory_bytes: int
    collected_at: datetime


def _parse_collected_at(value: object, fallback: datetime) -> datetime:
    """Parse a Metrics API timestamp, falling back to collection time."""
    if not isinstance(value, str) or not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class MetricsCollector:
    """Collects actual resource usage from the Kubernetes Metrics API."""

    def __init__(self) -> None:
        self.available: bool | None = None
        self.source: MetricSource = MetricSource.ESTIMATED

    def get_cpu_millicores(self, actual: ActualUsage, request: float) -> float:
        """Return actual CPU usage in millicores (0 if not available)."""
        if self.available is False:
            return 0.0
        return actual.cpu_millicores if actual.cpu_millicores > 0 else 0.0

    def get_memory_bytes(self, actual: ActualUsage, request: int) -> int:
        """Return actual memory usage in bytes (0 if not available)."""
        if self.available is False:
            return 0
        return actual.memory_bytes if actual.memory_bytes > 0 else 0

    def collect_pod_metrics(
        self,
        pods: list[PodResourceInfo],
        namespace: str | None = None,
    ) -> dict[str, ActualUsage]:
        """Fetch metrics for all pods and return a name-to-usage map."""
        if not _K8S_AVAILABLE or k8s_client is None:
            self.available = False
            logger.info("kubernetes package not installed — using estimated metrics")
            return {}

        custom_api = k8s_client.CustomObjectsApi()
        try:
            if namespace:
                metrics = custom_api.list_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                )
            else:
                metrics = custom_api.list_cluster_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="pods",
                )
            self.available = True
        except ApiException as exc:
            self.available = False
            logger.warning("metrics-server not available: %s", exc)
            return {}

        self.source = MetricSource.METRICS_SERVER
        pod_map = {pod.name: pod for pod in pods}
        result: dict[str, ActualUsage] = {}
        now = datetime.now()
        for item in metrics.get("items", []):
            pod_name = item.get("metadata", {}).get("name", "")
            if pod_name not in pod_map:
                continue
            total_cpu = 0.0
            total_mem = 0
            sample_count = 0
            for container in item.get("containers", []):
                total_cpu += _parse_cpu_to_millicores(
                    container.get("usage", {}).get("cpu")
                )
                total_mem += _parse_memory_to_bytes(
                    container.get("usage", {}).get("memory")
                )
                sample_count += 1
            sample = MetricSample(
                cpu_millicores=total_cpu,
                memory_bytes=total_mem,
                collected_at=_parse_collected_at(item.get("timestamp"), now),
            )
            usage = ActualUsage(
                cpu_millicores=sample.cpu_millicores,
                memory_bytes=sample.memory_bytes,
                source=MetricSource.METRICS_SERVER,
                observed_at=sample.collected_at,
                sample_count=max(sample_count, 1),
            )
            result[pod_name] = usage
            pod_map[pod_name].actual = usage
        return result

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> dict[str, ActualUsage]:
        """Collect metrics across all namespaces for the given pods."""
        by_namespace: dict[str, list[PodResourceInfo]] = {}
        for pod in pods:
            by_namespace.setdefault(pod.namespace, []).append(pod)
        all_metrics: dict[str, ActualUsage] = {}
        for namespace, namespace_pods in by_namespace.items():
            all_metrics.update(self.collect_pod_metrics(namespace_pods, namespace))
        return all_metrics

    def calculate_utilization(
        self,
        actual: ActualUsage,
        request: ResourceQuantities,
    ) -> dict[str, float]:
        """Calculate CPU and memory utilization percentages."""
        return {
            "cpu_utilization": (
                actual.cpu_millicores / request.cpu_millicores_request
                if request.cpu_millicores_request > 0
                else 0.0
            ),
            "memory_utilization": (
                actual.memory_bytes / request.memory_bytes_request
                if request.memory_bytes_request > 0
                else 0.0
            ),
        }


__all__ = ["MetricSample", "MetricsCollector"]
