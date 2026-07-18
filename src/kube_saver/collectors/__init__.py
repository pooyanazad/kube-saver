"""kube-saver collectors — data collection from K8s API, metrics-server, and eBPF.

Submodules:
    k8s_client    - Kubernetes API wrapper (namespaces, pods, nodes)
    metrics       - metrics-server integration for actual usage data
    runtime       - unified runtime collector with fallback chain
    ebpf          - eBPF collector integration layer
    ebpf_safety   - kernel/capability safety checks for eBPF
"""

from kube_saver.collectors.ebpf import EbpfCollectionResult, EbpfCollector
from kube_saver.collectors.ebpf_safety import EbpfSafetyReport, check_ebpf_safety
from kube_saver.collectors.k8s_client import K8sClient
from kube_saver.collectors.metrics import MetricsCollector
from kube_saver.collectors.runtime import RuntimeCollectionResult, RuntimeCollector

__all__ = [
    "EbpfCollector",
    "EbpfCollectionResult",
    "EbpfSafetyReport",
    "K8sClient",
    "MetricsCollector",
    "RuntimeCollector",
    "RuntimeCollectionResult",
    "check_ebpf_safety",
]
