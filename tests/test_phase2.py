"""Tests for Phase 2 analysis engine."""

from kube_saver.analyzers.alerts import evaluate_alerts
from kube_saver.analyzers.cost_waste import analyze_cost_waste
from kube_saver.analyzers.health import pod_health_score
from kube_saver.analyzers.resource_waste import PodWaste, analyze_resource_waste
from kube_saver.config import AlertConfig
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
)
from kube_saver.pricing import PricingEngine


def _make_pod(
    name: str,
    ns: str,
    cpu_req: float = 1000,
    cpu_act: float = 100,
    mem_req: int = 1024 * 1024 * 1024,
    mem_act: int = 100 * 1024 * 1024,
    restarts: int = 0,
) -> PodResourceInfo:
    return PodResourceInfo(
        name=name,
        namespace=ns,
        workload_kind="Deployment",
        workload_name=name.split("-")[0],
        resources=ResourceQuantities(
            cpu_millicores_request=cpu_req,
            cpu_millicores_limit=cpu_req * 2,
            memory_bytes_request=mem_req,
            memory_bytes_limit=mem_req * 2,
        ),
        actual=ActualUsage(
            cpu_millicores=cpu_act,
            memory_bytes=mem_act,
            source=MetricSource.METRICS_SERVER,
            sample_count=10,
        ),
        restart_count=restarts,
    )


def test_resource_waste_basic_analysis() -> None:
    pod = _make_pod("api-v1", "default", cpu_req=1000, cpu_act=200)
    report = analyze_resource_waste(
        namespaces=[NamespaceInfo(name="default")],
        pods=[pod],
        metrics_available=True,
    )
    assert report.total_pods == 1
    assert report.total_cpu_waste_millicores == 800
    assert report.namespaces[0].deployments[0].name == "api"


def test_resource_waste_no_usage_falls_back_to_request() -> None:
    pod = _make_pod("worker-1", "jobs", cpu_req=500, cpu_act=0, mem_req=200 * 1024**2, mem_act=0)
    pod.actual = ActualUsage(source=MetricSource.ESTIMATED)
    report = analyze_resource_waste([NamespaceInfo(name="jobs")], [pod], metrics_available=False)
    assert report.total_cpu_waste_millicores == 500
    assert report.total_memory_waste_bytes == 200 * 1024**2
    assert report.has_real_usage is False


def test_cost_waste_monthly_calculation() -> None:
    pod = _make_pod("api-v1", "default", cpu_req=1000, cpu_act=200)
    resource = analyze_resource_waste([NamespaceInfo(name="default")], [pod], metrics_available=True)
    pricing = PricingEngine(provider=CloudProvider.AWS, tier="general")
    cost = analyze_cost_waste(resource, pricing)
    assert cost.total_cost_waste.monthly_usd > 0
    assert cost.total_requested_cost.monthly_usd >= cost.total_cost_waste.monthly_usd
    assert 0 <= cost.waste_ratio <= 1


def test_health_score_penalizes_waste_and_oom() -> None:
    pw = PodWaste(
        pod=_make_pod("api", "default", cpu_req=1000, cpu_act=50, mem_req=1024**3, mem_act=10 * 1024**3, restarts=2),
        cpu_waste_ratio=0.95,
        memory_waste_ratio=0.0,
        has_usage_data=True,
    )
    score = pod_health_score(pw)
    assert score < 70


def test_alerts_trigger_on_high_waste() -> None:
    pod = _make_pod("api", "default", cpu_req=1000, cpu_act=50)
    resource = analyze_resource_waste([NamespaceInfo(name="default")], [pod], metrics_available=True)
    pricing = PricingEngine(provider=CloudProvider.AWS)
    cost = analyze_cost_waste(resource, pricing)
    alerts = evaluate_alerts(resource, cost, AlertConfig(warning_monthly_usd=0.01, warning_waste_ratio=0.1))
    assert any(a.level in {"warning", "critical"} for a in alerts)
