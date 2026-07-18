"""Metrics collector for kube-saver.

Queries the Kubernetes Metrics API (metrics-server) to populate actual
CPU/memory usage on ``PodResourceInfo`` objects.

Falls back gracefully when metrics-server is unavailable: pods keep
``MetricSource.ESTIMATED`` and zero actual usage, so waste calculations
still run (they will just report all requests as "wasted").
"""

from __future__ import annotations

import logging
from datetime import datetime

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


class MetricsCollector:
    """Collects actual resource usage from the Kubernetes Metrics API.

    Attributes:
        available: True if metrics-server was detected on first call.
        source: The metric source being used.
    """

    def __init__(self) -> None:
        self.available: bool | None = None
        self.source: MetricSource = MetricSource.ESTIMATED

    def get_cpu_millicores(self, actual: ActualUsage, request: float) -> float:
        """Return actual CPU usage in millicores (0 if not available)."""
        if self.available is False:
            return 0.0
        if actual.cpu_millicores > 0:
            return actual.cpu_millicores
        return 0.0

    def get_memory_bytes(self, actual: ActualUsage, request: int) -> int:
        """Return actual memory usage in bytes (0 if not available)."""
        if self.available is False:
            return 0
        if actual.memory_bytes > 0:
            return actual.memory_bytes
        return 0

    def collect_pod_metrics(
        self,
        pods: list[PodResourceInfo],
        namespace: str | None = None,
    ) -> dict[str, ActualUsage]:
        """Fetch metrics for all pods and return a name -> ActualUsage map.

        Populates ``pod.actual`` in-place for each pod as well.

        Args:
            pods: Pod info list with resource requests already set.
            namespace: If given, query only this namespace's pod metrics.

        Returns:
            Dict mapping pod name to its ``ActualUsage``.
        """
        if not _K8S_AVAILABLE or k8s_client is None:
            self.available = False
            logger.info("kubernetes package not installed — using estimated metrics")
            return {}

        custom_api = k8s_client.CustomObjectsApi()

        if namespace:
            try:
                metrics = custom_api.list_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                )
                self.available = True
            except ApiException as exc:
                self.available = False
                logger.warning(
                    "metrics-server not available for namespace %s: %s",
                    namespace,
                    exc,
                )
                return {}
        else:
            try:
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

        self.source = MetricSource.METRICS_SERVER if self.available else MetricSource.ESTIMATED

        pod_map: dict[str, PodResourceInfo] = {
            p.name: p for p in pods
        }
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
                cpu = _parse_cpu_to_millicores(container.get("usage", {}).get("cpu"))
                mem = _parse_memory_to_bytes(container.get("usage", {}).get("memory"))
                total_cpu += cpu
                total_mem += mem
                sample_count += 1

            usage = ActualUsage(
                cpu_millicores=total_cpu,
                memory_bytes=total_mem,
                source=MetricSource.METRICS_SERVER,
                observed_at=now,
                sample_count=max(sample_count, 1),
            )
            result[pod_name] = usage
            pod_map[pod_name].actual = usage

        logger.debug(
            "Collected metrics for %d / %d pods",
            len(result),
            len(pods),
        )
        return result

    def collect_all_pods(
        self,
        pods: list[PodResourceInfo],
    ) -> dict[str, ActualUsage]:
        """Collect metrics across all namespaces for the given pods.

        Groups pods by namespace and issues one Metrics API call per
        namespace to avoid calling the (potentially slow) cluster-wide endpoint.
        """
        by_namespace: dict[str, list[PodResourceInfo]] = {}
        for pod in pods:
            by_namespace.setdefault(pod.namespace, []).append(pod)

        all_metrics: dict[str, ActualUsage] = {}
        for ns, ns_pods in by_namespace.items():
            all_metrics.update(self.collect_pod_metrics(ns_pods, namespace=ns))

        return all_metrics

    def calculate_utilization(
        self,
        actual: ActualUsage,
        request: ResourceQuantities,
    ) -> dict[str, float]:
        """Calculate utilization percentages.

        Returns dict with keys:
            cpu_utilization:  actual CPU / requested CPU (0.0 – inf)
            memory_utilization: actual memory / requested memory (0.0 – inf)

        Values > 1.0 mean the pod is using more than requested (risky).
        Values of 0.0 mean no metrics are available.
        """
        cpu_util = 0.0
        mem_util = 0.0

        if request.cpu_millicores_request > 0:
            cpu_util = actual.cpu_millicores / request.cpu_millicores_request
        if request.memory_bytes_request > 0:
            mem_util = actual.memory_bytes / request.memory_bytes_request

        return {
            "cpu_utilization": cpu_util,
            "memory_utilization": mem_util,
        }


__all__ = ["MetricsCollector"]
