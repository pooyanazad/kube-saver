"""Metrics collector for kube-saver.

Queries the Kubernetes Metrics API (metrics-server) to populate actual
CPU/memory usage on ``PodResourceInfo`` objects.

Falls back gracefully when metrics-server is unavailable: pods keep
``MetricSource.ESTIMATED`` and zero actual usage, so waste calculations
still run (they will just report all requests as "wasted").
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import InvalidOperation

from urllib3.exceptions import HTTPError

from kube_saver.config import TimeoutConfig
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
    )
except ImportError:
    _K8S_AVAILABLE = False

try:
    from kubernetes import client as k8s_client  # type: ignore[import-untyped]
    from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]
    from kubernetes.utils.quantity import parse_quantity  # type: ignore[import-untyped]
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


def _parse_collected_at(value: object) -> datetime | None:
    """Reject missing/invalid timestamps instead of inventing freshness."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return None


class MetricsCollector:
    """Collects actual resource usage from the Kubernetes Metrics API."""

    def __init__(self, timeouts: TimeoutConfig | None = None) -> None:
        self.timeouts = (timeouts or TimeoutConfig()).normalized()
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
                    _request_timeout=self.timeouts.operation_seconds,
                )
            else:
                metrics = custom_api.list_cluster_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="pods",
                    _request_timeout=self.timeouts.operation_seconds,
                )
            self.available = True
        except (ApiException, HTTPError, TimeoutError, ConnectionError) as exc:
            self.available = False
            logger.warning("metrics-server not available: %s", exc)
            return {}

        self.source = MetricSource.METRICS_SERVER
        pod_map = {pod.name: pod for pod in pods}
        result: dict[str, ActualUsage] = {}
        for item in metrics.get("items", []):
            pod_name = item.get("metadata", {}).get("name", "")
            if pod_name not in pod_map:
                continue
            pod = pod_map[pod_name]
            entries = item.get("containers", [])
            if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
                logger.warning("Malformed metrics for %s/%s; treating usage as unavailable", pod.namespace, pod_name)
                pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
                continue
            collected_at = _parse_collected_at(item.get("timestamp"))
            expected = {container.name for container in pod.containers}
            names = [entry.get("name") for entry in entries]
            if expected and not all(isinstance(name, str) for name in names):
                pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
                continue
            if (not entries or collected_at is None
                    or (expected and (set(names) != expected or len(names) != len(expected)))):
                logger.warning("Incomplete metrics for %s/%s; treating usage as unavailable", pod.namespace, pod_name)
                pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
                continue
            try:
                # The Kubernetes quantity parser supports micro/nano CPU as
                # well as milli units; missing fields must not become zeros.
                cpu_values = [float(parse_quantity(entry["usage"]["cpu"])) * 1000 for entry in entries]
                memory_values = [float(parse_quantity(entry["usage"]["memory"])) for entry in entries]
                if not all(math.isfinite(value) and value >= 0 for value in cpu_values + memory_values):
                    raise ValueError("non-finite or negative usage")
                sample = MetricSample(
                    cpu_millicores=sum(cpu_values),
                    memory_bytes=math.ceil(sum(memory_values)),
                    collected_at=collected_at,
                )
            except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError):
                logger.warning("Invalid metrics for %s/%s; treating usage as unavailable", pod.namespace, pod_name)
                pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
                continue
            usage = ActualUsage(
                cpu_millicores=sample.cpu_millicores,
                memory_bytes=sample.memory_bytes,
                source=MetricSource.METRICS_SERVER,
                observed_at=sample.collected_at,
                sample_count=len(entries),
            )
            result[pod_name] = usage
            pod_map[pod_name].actual = usage
        return result

    def collect_all_pods(self, pods: list[PodResourceInfo]) -> dict[str, ActualUsage]:
        """Collect metrics across all namespaces for the given pods.

        Returns a map keyed by ``"namespace/pod_name"`` so identically named
        pods in different namespaces cannot collide.

        ``available`` reflects the *aggregate* outcome: True when at least
        one namespace was read successfully. A failure in one namespace
        therefore degrades only the pods of that namespace (they are simply
        absent from the map) instead of blanking the whole scan.
        """
        by_namespace: dict[str, list[PodResourceInfo]] = {}
        for pod in pods:
            by_namespace.setdefault(pod.namespace, []).append(pod)
        all_metrics: dict[str, ActualUsage] = {}
        any_namespace_ok = False
        for namespace, namespace_pods in by_namespace.items():
            namespace_metrics = self.collect_pod_metrics(namespace_pods, namespace)
            if self.available:
                any_namespace_ok = True
            for pod_name, usage in namespace_metrics.items():
                all_metrics[f"{namespace}/{pod_name}"] = usage
        self.available = any_namespace_ok
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
