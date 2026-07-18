"""Kubernetes API client for kube-saver.

Wraps the official ``kubernetes`` Python client to fetch cluster state:
namespaces, deployments, pods, nodes, and their resource requests/limits.

Handles RBAC failures gracefully — if a resource cannot be read we skip it
rather than crashing the entire scan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from kube_saver.models.core import (
    CloudProvider,
    ClusterInfo,
    ContainerResourceInfo,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
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
    """

    context: str | None = None
    namespace_filter: list[str] | None = None
    exclude_namespaces: set[str] = field(default_factory=lambda: {
        "kube-system", "kube-public", "kube-node-lease",
    })

    _core_api: object = field(default=None, init=False, repr=False)
    _apps_api: object = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)

    def connect(self) -> None:
        """Load kubeconfig and build API clients.

        Raises:
            RuntimeError: If the ``kubernetes`` package is not installed.
            kubernetes.config.config_exception.ConfigException:
                If kubeconfig cannot be loaded.
        """
        if not _K8S_AVAILABLE:
            raise RuntimeError(
                "The 'kubernetes' package is required. "
                "Install it with: pip install kube-saver"
            )
        try:
            k8s_config.load_kube_config(context=self.context or None)
        except k8s_config.ConfigException:
            if self.context:
                raise
            k8s_config.load_incluster_config()
        self._core_api = k8s_client.CoreV1Api()
        self._apps_api = k8s_client.AppsV1Api()
        self._connected = True
        logger.info("Kubeconfig loaded successfully")

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
        across all worker nodes.
        """
        version = "unknown"
        try:
            version_api = k8s_client.VersionApi()
            version_info = version_api.get_code()
            version = getattr(version_info, "git_version", None) or "unknown"
        except Exception:
            version = "unknown"

        try:
            nodes = self.core.list_node().items
        except ApiException as exc:
            logger.warning("Cannot list nodes (RBAC?): %s", exc)
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

        Respects ``namespace_filter`` and ``exclude_namespaces``.
        """
        try:
            ns_list = self.core.list_namespace().items
        except ApiException as exc:
            logger.warning("Cannot list namespaces (RBAC?): %s", exc)
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
                namespace, field_selector="status.phase=Running"
            )
            return len(pods.items)
        except ApiException as exc:
            logger.warning("Cannot list pods in %s: %s", namespace, exc)
            return 0

    def get_pods(self, namespace: str) -> list[PodResourceInfo]:
        """Fetch all pods in a namespace with their resource data.

        Returns a list of ``PodResourceInfo`` objects populated with
        resource requests/limits from the pod spec.
        """
        try:
            pods = self.core.list_namespaced_pod(namespace).items
        except ApiException as exc:
            logger.warning("Cannot list pods in %s: %s", namespace, exc)
            return []

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
                    containers=container_infos,
                    resources=agg,
                    restart_count=restarts,
                )
            )
        return results

    def get_all_pods(self) -> list[PodResourceInfo]:
        """Fetch pods across all non-excluded namespaces."""
        all_pods: list[PodResourceInfo] = []
        for ns in self.get_namespaces():
            all_pods.extend(self.get_pods(ns.name))
        return all_pods

    def get_nodes_with_pods(self) -> dict[str, list[str]]:
        """Map node name to list of pod names running on it."""
        node_pods: dict[str, list[str]] = {}
        try:
            pods = self.core.list_pod_for_all_namespaces().items
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
