"""End-to-end tests for Step 43."""

from __future__ import annotations

from kube_saver.analyzers.alerts import evaluate_alerts
from kube_saver.analyzers.cost_waste import analyze_cost_waste
from kube_saver.analyzers.health import pod_health_score
from kube_saver.analyzers.resource_waste import analyze_resource_waste
from kube_saver.collectors.runtime import RuntimeCollector
from kube_saver.config import AlertConfig
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
)
from kube_saver.pricing.engine import PricingEngine
from kube_saver.recommenders.engine import generate_recommendations


class _NoMetricsCollector:
    def __init__(self) -> None:
        self.available = False

    def collect_all_pods(self, pods):
        return {}


class _UnavailableEbpfCollector:
    def collect_all_pods(self, pods):
        from kube_saver.collectors.ebpf import EbpfCollectionResult
        from kube_saver.collectors.ebpf_safety import EbpfSafetyReport

        return EbpfCollectionResult(
            supported=False,
            warnings=["ebpf unavailable in e2e test"],
            safety=EbpfSafetyReport(supported=False, reasons=["test"]),
            metrics={},
        )



def _pod(name: str, namespace: str, cpu_req: float, cpu_act: float, mem_req_mi: int, mem_act_mi: int, restarts: int = 0) -> PodResourceInfo:
    return PodResourceInfo(
        name=name,
        namespace=namespace,
        workload_kind="Deployment",
        workload_name=name.split("-")[0],
        resources=ResourceQuantities(
            cpu_millicores_request=cpu_req,
            memory_bytes_request=mem_req_mi * 1024**2,
        ),
        actual=ActualUsage(
            cpu_millicores=cpu_act,
            memory_bytes=mem_act_mi * 1024**2,
            source=MetricSource.METRICS_SERVER,
        ),
        restart_count=restarts,
    )


class TestEndToEndWorkflow:
    def test_full_workflow_connect_collect_analyze_recommend(self) -> None:
        namespaces = [NamespaceInfo(name="default")]
        pods = [
            _pod("api-0", "default", cpu_req=1000, cpu_act=100, mem_req_mi=1024, mem_act_mi=128),
            _pod("api-1", "default", cpu_req=1000, cpu_act=150, mem_req_mi=1024, mem_act_mi=160),
        ]
        resource = analyze_resource_waste(namespaces, pods, metrics_available=True)
        pricing = PricingEngine(provider=CloudProvider.AWS)
        cost = analyze_cost_waste(resource, pricing)
        recs = generate_recommendations(resource, pricing)
        alerts = evaluate_alerts(resource, cost, AlertConfig(warning_monthly_usd=0.01, warning_waste_ratio=0.1))

        assert resource.total_pods == 2
        assert resource.has_real_usage is True
        assert cost.total_cost_waste.monthly_usd > 0
        assert recs
        assert alerts

    def test_multi_namespace_workflow(self) -> None:
        namespaces = [NamespaceInfo(name="team-a"), NamespaceInfo(name="team-b")]
        pods = [
            _pod("api-0", "team-a", cpu_req=1000, cpu_act=100, mem_req_mi=1024, mem_act_mi=128),
            _pod("worker-0", "team-b", cpu_req=500, cpu_act=50, mem_req_mi=512, mem_act_mi=64),
        ]
        resource = analyze_resource_waste(namespaces, pods, metrics_available=True)
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(resource, pricing)

        assert len(resource.namespaces) == 2
        assert {ns.namespace.name for ns in resource.namespaces} == {"team-a", "team-b"}
        assert {rec.target_namespace for rec in recs} == {"team-a", "team-b"}

    def test_error_handling_no_metrics_and_no_ebpf(self) -> None:
        pods = [_pod("api-0", "default", cpu_req=1000, cpu_act=0, mem_req_mi=512, mem_act_mi=0)]
        collector = RuntimeCollector(prefer_ebpf=True)
        collector.ebpf = _UnavailableEbpfCollector()
        collector.metrics = _NoMetricsCollector()

        result = collector.collect_all_pods(pods)
        resource = analyze_resource_waste([NamespaceInfo(name="default")], pods, metrics_available=result.metrics_available)

        assert result.source == MetricSource.ESTIMATED
        assert result.metrics_available is False
        assert result.used_fallback is True
        assert result.warnings
        assert resource.has_real_usage is False
        assert resource.total_cpu_waste_millicores == 1000

    def test_scale_with_many_pods(self) -> None:
        namespaces = [NamespaceInfo(name="bulk")]
        pods = [
            _pod(f"api-{i}", "bulk", cpu_req=1000, cpu_act=100, mem_req_mi=256, mem_act_mi=64)
            for i in range(1000)
        ]
        resource = analyze_resource_waste(namespaces, pods, metrics_available=True)
        pricing = PricingEngine(provider=CloudProvider.AWS)
        cost = analyze_cost_waste(resource, pricing)
        recs = generate_recommendations(resource, pricing)

        assert resource.total_pods == 1000
        assert cost.total_cost_waste.monthly_usd > 0
        assert len(recs) >= 1000

    def test_long_running_stability_repeated_analysis(self) -> None:
        namespaces = [NamespaceInfo(name="default")]
        pods = [_pod("api-0", "default", cpu_req=1000, cpu_act=100, mem_req_mi=512, mem_act_mi=64, restarts=1)]
        pricing = PricingEngine(provider=CloudProvider.AWS)

        scores = []
        for _ in range(20):
            resource = analyze_resource_waste(namespaces, pods, metrics_available=True)
            recs = generate_recommendations(resource, pricing)
            scores.append(pod_health_score(resource.namespaces[0].pod_waste[0]))
            assert recs

        assert len(scores) == 20
        assert all(score <= 100 for score in scores)
