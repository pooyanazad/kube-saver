"""Kubernetes API client for kube-saver.

Wraps the official ``kubernetes`` Python client to fetch cluster state:
namespaces, deployments, pods, nodes, and their resource requests/limits.

Handles RBAC failures gracefully — if a resource cannot be read we skip it
rather than crashing the entire scan.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from kube_saver.collectors.retry import _reason, retry_call
from kube_saver.config import RetryConfig, TimeoutConfig
from kube_saver.models.core import (
    CloudProvider,
    ClusterInfo,
    ContainerResourceInfo,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
    ScanResult,
)

logger = logging.getLogger(__name__)

# ── Kubernetes API imports (lazy so the module can be imported even without
# the kubernetes package installed — useful for unit tests). ────────────────
try:
    from kubernetes import client as k8s_client  # type: ignore[import-untyped]
    from kubernetes import config as k8s_config
    from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False
    k8s_client = None
    k8s_config = None

    class ApiException(Exception):  # type: ignore[no-redef]  # noqa: N818
        """Fallback when kubernetes is not installed."""
        pass


# ── Parsing helpers ────────────────────────────────────────────────────────

def _parse_cpu_to_millicores(value: str | None) -> float:
    """Convert a Kubernetes CPU quantity string to millicores.

    Supports: '500m', '0.5', '2', '2000m', '2.5'.
    Returns 0.0 for empty/None or unparseable values.
    """
    if not value:
        return 0.0
    value = str(value).strip()
    if value.endswith("m"):
        return float(value[:-1])
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000
    try:
        return float(value) * 1000
    except ValueError:
        logger.warning("Unparseable CPU value: %r", value)
        return 0.0


def _parse_memory_to_bytes(value: str | None) -> int:
    """Convert a Kubernetes memory quantity string to bytes.

    Supports: '256Mi', '1Gi', '512Ki', '1024'.
    Returns 0 for empty/None or unparseable values.
    """
    if not value:
        return 0
    value = str(value).strip()
    units: dict[str, float] = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "Ei": 1024**6,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
        "P": 1000**5,
        "E": 1000**6,
        "n": 1e-9,
    }
    for suffix, multiplier in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if value.endswith(suffix):
            return int(float(value[: -len(suffix)]) * multiplier)
    try:
        return int(float(value))
    except ValueError:
        logger.warning("Unparseable memory value: %r", value)
        return 0


def _extract_resource_quantities(resource_spec: object) -> ResourceQuantities:
    """Extract request/limit ResourceQuantities from a container resource spec.

    Supports both plain dicts and kubernetes.client.V1ResourceRequirements
    objects returned by the official client.
    """
    if resource_spec is None:
        requests = {}
        limits = {}
    elif isinstance(resource_spec, dict):
        requests = resource_spec.get("requests", {})
        limits = resource_spec.get("limits", {})
    else:
        requests = getattr(resource_spec, "requests", None) or {}
        limits = getattr(resource_spec, "limits", None) or {}
    return ResourceQuantities(
        cpu_millicores_request=_parse_cpu_to_millicores(requests.get("cpu")),
        cpu_millicores_limit=_parse_cpu_to_millicores(limits.get("cpu")),
        memory_bytes_request=_parse_memory_to_bytes(requests.get("memory")),
        memory_bytes_limit=_parse_memory_to_bytes(limits.get("memory")),
    )


# ── Main API client ───────────────────────────────────────────────────────

@dataclass
class K8sClient:
    """Thin wrapper around the Kubernetes Python API.

    Attributes:
        context: kubeconfig context to use (None = current default).
        namespace_filter: If set, only return these namespaces.
        exclude_namespaces: Skip namespaces in this set.
        timeouts: Connect, read, and operation timeouts applied to every
            API call. Defaults guard against slow or unreachable API servers.
    """

    context: str | None = None
    namespace_filter: list[str] | None = None
    exclude_namespaces: set[str] = field(default_factory=lambda: {
        "kube-system", "kube-public", "kube-node-lease",
    })
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retries: RetryConfig = field(default_factory=RetryConfig)

    _core_api: object = field(default=None, init=False, repr=False)
    _apps_api: object = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)

    def connect(self) -> None:
        """Load kubeconfig and build API clients.

        Raises:
            RuntimeError: If the ``kubernetes`` package is not installed.
            FileNotFoundError: If no kubeconfig file exists.
            kubernetes.config.config_exception.ConfigException:
                If the kubeconfig cannot be parsed, or the requested context
                does not exist in the kubeconfig file.
        """
        if not _K8S_AVAILABLE:
            raise RuntimeError(
                "The 'kubernetes' package is required. "
                "Install it with: pip install kube-saver"
            )

        # ── Validate kubeconfig file exists ───────────────────────────────
        kubeconfig_path = self._resolve_kubeconfig_path()
        if kubeconfig_path and not Path(kubeconfig_path).exists():
            raise FileNotFoundError(
                f"Kubeconfig not found at {kubeconfig_path}. "
                "Set KUBECONFIG or place a config at ~/.kube/config"
            )

        # ── Validate requested context exists ─────────────────────────────
        if self.context:
            try:
                contexts, current = k8s_config.list_kube_config_contexts(
                    config_file=kubeconfig_path
                )
            except Exception:
                pass  # ConfigException will be raised by load_kube_config below.
            else:
                available = {c["name"] for c in contexts}
                if self.context not in available:
                    available_str = ", ".join(sorted(available)) or "(none)"
                    raise k8s_config.ConfigException(
                        f"Context '{self.context}' not found in kubeconfig. "
                        f"Available: {available_str}"
                    )

        # ── Load config and build clients ─────────────────────────────────
        try:
            k8s_config.load_kube_config(context=self.context or None)
        except k8s_config.ConfigException:
            if self.context:
                raise
            k8s_config.load_incluster_config()
        self._core_api = k8s_client.CoreV1Api()
        self._apps_api = k8s_client.AppsV1Api()
        self._apply_timeouts_to_clients()
        self._connected = True
        logger.info(
            "Kubeconfig loaded successfully (timeouts: connect=%.1fs read=%.1fs op=%.1fs)",
            self.timeouts.connect_seconds,
            self.timeouts.read_seconds,
            self.timeouts.operation_seconds,
        )

    def _apply_timeouts_to_clients(self) -> None:
        """Push connect/read timeouts into the underlying urllib3 pools.

        The official client stores its HTTP transport on ``ApiClient.rest_client``.
        ``PoolManager.connection_pool_kw['timeout']`` accepts a
        ``urllib3.Timeout`` object (connect/read), not a bare tuple. Per-call
        operation timeouts are handled separately via ``_request_timeout``.
        """
        if not _K8S_AVAILABLE:
            return
        try:
            from urllib3.util.timeout import Timeout as Urllib3Timeout
        except ImportError:
            return
        pool_timeout = Urllib3Timeout(
            connect=self.timeouts.connect_seconds,
            read=self.timeouts.read_seconds,
        )
        for api in (self._core_api, self._apps_api):
            if api is None:
                continue
            rest_client = getattr(api, "rest_client", None) or getattr(
                getattr(api, "api_client", None), "rest_client", None
            )
            if rest_client is None:
                continue
            pool = getattr(rest_client, "pool_manager", None)
            if pool is not None and hasattr(pool, "connection_pool_kw"):
                pool.connection_pool_kw["timeout"] = pool_timeout

    @staticmethod
    def _resolve_kubeconfig_path() -> str | None:
        """Find the kubeconfig file that would be used."""
        explicit = os.environ.get("KUBECONFIG")
        if explicit:
            return explicit.split(os.pathsep)[0] if explicit else None
        return str(Path.home() / ".kube" / "config")

    @property
    def core(self) -> k8s_client.CoreV1Api:
        if not self._connected:
            self.connect()
        return self._core_api

    @property
    def apps(self) -> k8s_client.AppsV1Api:
        if not self._connected:
            self.connect()
        return self._apps_api

    # ── High-level queries ────────────────────────────────────────────────

    def get_cluster_info(self) -> ClusterInfo:
        """Fetch basic cluster information and node totals.

        Returns a ``ClusterInfo`` with the sum of allocatable CPU and memory
        across all worker nodes. Both the version query and the node listing
        are retried via ``retry_call`` using the client's ``RetryConfig`` so a
        transient 5xx/429/timeout cannot blank out the cluster metadata;
        after exhaustion each call falls back to its existing degraded value
        (``version='unknown'`` and an empty node list).
        """
        op_timeout = self.timeouts.operation_seconds
        version = "unknown"
        try:
            version_api = k8s_client.VersionApi()
            version_info = retry_call(
                lambda: version_api.get_code(_request_timeout=op_timeout),
                operation="get_version",
                retry_config=self.retries,
            )
            version = getattr(version_info, "git_version", None) or "unknown"
        except Exception as exc:
            logger.warning("Cannot fetch cluster version after retries: %s", exc)
            version = "unknown"

        try:
            nodes = retry_call(
                lambda: self.core.list_node(_request_timeout=op_timeout).items,
                operation="list_node",
                retry_config=self.retries,
            )
        except ApiException as exc:
            logger.warning("Cannot list nodes (RBAC?): %s", exc)
            nodes = []
        except Exception as exc:
            logger.warning("Cannot list nodes after retries: %s", exc)
            nodes = []

        total_cpu = 0
        total_mem = 0
        for node in nodes:
            alloc = node.status.allocatable or {}
            total_cpu += int(_parse_cpu_to_millicores(alloc.get("cpu")))
            total_mem += _parse_memory_to_bytes(alloc.get("memory"))

        context_name = self.context or "default"
        return ClusterInfo(
            name=context_name,
            context=context_name,
            provider=CloudProvider.UNKNOWN,
            version=version,
            node_count=len(nodes),
            total_cpu_millicores=total_cpu,
            total_memory_bytes=total_mem,
        )

    def get_namespaces(self) -> list[NamespaceInfo]:
        """Return all user-visible namespaces with their metadata.

        Respects ``namespace_filter`` and ``exclude_namespaces``. Transient
        API failures (5xx, 429, timeouts) are retried via ``retry_call``
        using the client's ``RetryConfig``; after exhaustion the final
        error is treated as an RBAC failure and an empty list is returned.
        """
        try:
            ns_list = retry_call(
                lambda: self.core.list_namespace(
                    _request_timeout=self.timeouts.operation_seconds
                ).items,
                operation="list_namespace",
                retry_config=self.retries,
            )
        except ApiException as exc:
            logger.warning("Cannot list namespaces (RBAC?): %s", exc)
            return []
        except Exception as exc:
            logger.warning("Cannot list namespaces after retries: %s", exc)
            return []

        results: list[NamespaceInfo] = []
        for ns in ns_list:
            name = ns.metadata.name
            if name in self.exclude_namespaces:
                continue
            if self.namespace_filter and name not in self.namespace_filter:
                continue
            results.append(
                NamespaceInfo(
                    name=name,
                    labels=dict(ns.metadata.labels or {}),
                )
            )
        return results

    def get_namespace_pod_count(self, namespace: str) -> int:
        """Count running pods in a namespace."""
        try:
            pods = self.core.list_namespaced_pod(
                namespace,
                field_selector="status.phase=Running",
                _request_timeout=self.timeouts.operation_seconds,
            )
            return len(pods.items)
        except ApiException as exc:
            logger.warning("Cannot list pods in %s: %s", namespace, exc)
            return 0

    def _collect_pods(
        self, namespace: str
    ) -> tuple[list[PodResourceInfo], str | None]:
        """Fetch pods in a namespace, preserving the final API error.

        Runs the per-namespace pod listing through ``retry_call`` so
        transient 5xx/429/timeout failures are retried with backoff. When
        retries are exhausted (or a non-transient RBAC failure occurs),
        the final exception is translated into a short, stable reason
        string and returned alongside an empty pod list so the caller can
        record the failure rather than silently losing it.

        Args:
            namespace: Namespace to list pods in.

        Returns:
            A ``(pods, error)`` tuple where ``pods`` is the list of
            ``PodResourceInfo`` objects parsed from the API response (empty
            on failure) and ``error`` is a human-readable reason string for
            the final failure, or ``None`` when the listing succeeded.
        """
        try:
            pods = retry_call(
                lambda: self.core.list_namespaced_pod(
                    namespace,
                    _request_timeout=self.timeouts.operation_seconds,
                ).items,
                operation="list_namespaced_pod",
                retry_config=self.retries,
            )
        except ApiException as exc:
            reason = _reason(exc)
            logger.warning("Cannot list pods in %s: %s", namespace, reason)
            return [], reason
        except Exception as exc:
            reason = _reason(exc)
            logger.warning(
                "Cannot list pods in %s after retries: %s", namespace, reason
            )
            return [], reason

        results: list[PodResourceInfo] = []
        for pod in pods:
            pod_spec = pod.spec if pod.spec is not None else None
            owner = pod.metadata.owner_references
            workload_kind = owner[0].kind if owner else "Pod"
            workload_name = owner[0].name if owner else pod.metadata.name

            containers = pod_spec.containers if pod_spec is not None else None
            containers = containers or []
            agg = ResourceQuantities()
            container_infos: list[ContainerResourceInfo] = []

            for c in containers:
                resources = _extract_resource_quantities(c.resources or {})
                agg.cpu_millicores_request += resources.cpu_millicores_request
                agg.cpu_millicores_limit += resources.cpu_millicores_limit
                agg.memory_bytes_request += resources.memory_bytes_request
                agg.memory_bytes_limit += resources.memory_bytes_limit
                container_infos.append(
                    ContainerResourceInfo(name=c.name, resources=resources)
                )

            restarts = sum(
                (cs.restart_count or 0)
                for cs in (pod.status.container_statuses or [])
            )

            results.append(
                PodResourceInfo(
                    name=pod.metadata.name,
                    namespace=namespace,
                    node_name=pod_spec.node_name if pod_spec is not None else None,
                    workload_kind=workload_kind,
                    workload_name=workload_name,
                    labels=dict(pod.metadata.labels or {}),
                    annotations=dict(pod.metadata.annotations or {}),
                    containers=container_infos,
                    resources=agg,
                    restart_count=restarts,
                )
            )
        return results, None

    def get_pods(self, namespace: str) -> list[PodResourceInfo]:
        """Fetch all pods in a namespace with their resource data.

        Returns a list of ``PodResourceInfo`` objects populated with
        resource requests/limits from the pod spec. Transient API failures
        (5xx, 429, timeouts) are retried via ``retry_call`` using the
        client's ``RetryConfig``; after exhaustion the final error is
        treated as an RBAC failure and an empty list is returned.

        Use ``get_all_pods`` when you also need the per-namespace failure
        reasons surfaced as a ``ScanResult``.
        """
        pods, _error = self._collect_pods(namespace)
        return pods

    def get_all_pods(self) -> ScanResult:
        """Fetch pods across all non-excluded namespaces as a ScanResult.

        Iterates over every namespace returned by ``get_namespaces`` and
        lists pods in each via ``_collect_pods``. The returned
        ``ScanResult`` preserves the final API error for any namespace
        whose pod listing failed after retries were exhausted:

        * ``ok`` — every namespace listed cleanly, no errors.
        * ``partial`` — at least one namespace failed but some pods were
          still collected; ``errors`` holds one ``"namespace: reason"``
          string per failure.
        * ``failed`` — no pods could be collected (either no namespaces
          were visible, or every namespace failed); ``errors`` records
          the underlying reason(s) and ``pods`` is empty.

        Args:
            None.

        Returns:
            A ``ScanResult`` carrying the successfully collected pods and
            one human-readable error string per failed namespace.
        """
        namespaces = self.get_namespaces()
        if not namespaces:
            return ScanResult.failure(
                ["get_namespaces: no readable namespaces (RBAC or cluster down)"]
            )

        all_pods: list[PodResourceInfo] = []
        errors: list[str] = []
        for ns in namespaces:
            pods, error = self._collect_pods(ns.name)
            all_pods.extend(pods)
            if error is not None:
                errors.append(f"{ns.name}: {error}")

        if errors and not all_pods:
            return ScanResult.failure(errors)
        if errors:
            return ScanResult.partial_success(all_pods, errors)
        return ScanResult.success(all_pods)

    def get_nodes_with_pods(self) -> dict[str, list[str]]:
        """Map node name to list of pod names running on it."""
        node_pods: dict[str, list[str]] = {}
        try:
            pods = self.core.list_pod_for_all_namespaces(
                _request_timeout=self.timeouts.operation_seconds
            ).items
        except ApiException as exc:
            logger.warning("Cannot list pods cluster-wide: %s", exc)
            return {}
        for pod in pods:
            node = (pod.spec.node_name or "unscheduled").strip()
            node_pods.setdefault(node, []).append(pod.metadata.name)
        return node_pods

    def close(self) -> None:
        """Release any held API client resources."""
        self._core_api = None
        self._apps_api = None
        self._connected = False


__all__ = [
    "K8sClient",
    "_parse_cpu_to_millicores",
    "_parse_memory_to_bytes",
    "_K8S_AVAILABLE",
]
