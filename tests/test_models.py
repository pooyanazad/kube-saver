"""Tests for kube-saver data models."""

from datetime import datetime

from kube_saver.models.core import (
    ActualUsage,
    ClusterInfo,
    CloudProvider,
    ContainerResourceInfo,
    CostInfo,
    MetricSource,
    NamespaceInfo,
    NamespaceWaste,
    PodResourceInfo,
    Recommendation,
    ResourceQuantities,
    ResourceWaste,
    WasteReport,
)


def test_cluster_info_defaults() -> None:
    info = ClusterInfo(name="test", context="test")
    assert info.provider == CloudProvider.UNKNOWN
    assert info.node_count == 0
    assert info.total_cpu_millicores == 0


def test_resource_quantities_has_requests_and_limits() -> None:
    rq = ResourceQuantities(
        cpu_millicores_request=100,
        cpu_millicores_limit=200,
        memory_bytes_request=1024,
        memory_bytes_limit=2048,
    )
    assert rq.has_requests is True
    assert rq.has_limits is True

    rq2 = ResourceQuantities()
    assert rq2.has_requests is False
    assert rq2.has_limits is False


def test_cost_info_arithmetic() -> None:
    a = CostInfo.from_hourly(1.0)
    b = CostInfo.from_hourly(2.0)
    total = a + b
    assert total.hourly_usd == 3.0
    assert total.daily_usd == (a.daily_usd + b.daily_usd)
    # 730 hours/month is AWS standard
    assert total.monthly_usd == 3.0 * 730


def test_actual_usage_defaults() -> None:
    a = ActualUsage()
    assert a.source == MetricSource.ESTIMATED
    assert a.sample_count == 1
    assert isinstance(a.observed_at, datetime)


def test_namespace_info_production_detection() -> None:
    prod = NamespaceInfo(name="myapp", labels={"env": "production"})
    assert prod.is_production is True

    staging = NamespaceInfo(name="myapp", labels={"env": "staging"})
    assert staging.is_production is False

    named = NamespaceInfo(name="prod")
    assert named.is_production is True


def test_pod_oom_detection() -> None:
    pod = PodResourceInfo(name="api", restart_count=0)
    assert pod.had_oom_events is False

    pod.restart_count = 5
    assert pod.had_oom_events is True


def test_container_resource_info() -> None:
    cr = ContainerResourceInfo(
        name="nginx",
        resources=ResourceQuantities(cpu_millicores_request=200),
        actual=ActualUsage(cpu_millicores=50, sample_count=10),
    )
    assert cr.name == "nginx"
    assert cr.resources.cpu_millicores_request == 200
    assert cr.actual.cpu_millicores == 50


def test_recommendation_default_confidence() -> None:
    rec = Recommendation(
        target_name="api",
        resource_type="cpu-request",
        current_value="1000m",
        suggested_value="200m",
    )
    assert rec.confidence == "medium"
    assert rec.target_kind == "Deployment"


def test_waste_report_aggregates() -> None:
    report = WasteReport(
        cluster=ClusterInfo(name="test", context="test"),
        total_pods=10,
        waste=ResourceWaste(cpu_millicores=5000, memory_bytes=10_000_000),
    )
    assert report.total_pods == 10
    assert report.waste.cpu_millicores == 5000
    assert isinstance(report.generated_at, datetime)


def test_namespace_waste_efficiency_default() -> None:
    nw = NamespaceWaste(namespace=NamespaceInfo(name="ns"))
    assert nw.efficiency_score == 100.0
    assert nw.pod_count == 0


def test_resource_waste_default_zero() -> None:
    rw = ResourceWaste()
    assert rw.cpu_millicores == 0.0
    assert rw.memory_bytes == 0