from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis
from kube_saver.analyzers.resource_waste import NamespaceAnalysis, ResourceWasteReport
from kube_saver.exporters.prometheus import render_prometheus_metrics
from kube_saver.exporters.report_generator import generate_html_report
from kube_saver.models.core import CostInfo, NamespaceInfo, Recommendation


def _resource_report() -> ResourceWasteReport:
    return ResourceWasteReport(
        namespaces=[NamespaceAnalysis(namespace=NamespaceInfo(name="default"), pod_count=3)],
        total_cpu_waste_millicores=1500,
        total_memory_waste_bytes=768 * 1024**2,
        total_cpu_request_millicores=3000,
        total_pods=3,
        metrics_available=True,
        has_real_usage=True,
    )


def _cost_report() -> CostWasteReport:
    return CostWasteReport(
        total_cost_waste=CostInfo(monthly_usd=61.98),
        namespaces=[
            NamespaceCostAnalysis(
                namespace="default",
                cost_waste=CostInfo(monthly_usd=61.98),
                cpu_waste_millicores=1500,
                memory_waste_bytes=768 * 1024**2,
                efficiency_score=50.0,
            )
        ],
    )


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            target_kind="Deployment",
            target_name="nginx-wasteful",
            target_namespace="default",
            resource_type="cpu-request",
            current_value="1000m",
            suggested_value="150m",
        )
    ]


def test_render_prometheus_metrics() -> None:
    text = render_prometheus_metrics(_resource_report(), _cost_report())
    assert "kube_saver_waste_cpu_millicores" in text
    assert 'namespace="default"' in text
    assert "61.980000" in text


def test_generate_html_report() -> None:
    report = generate_html_report(_resource_report(), _cost_report(), _recommendations())
    assert "kube-saver executive summary" in report.html
    assert "nginx-wasteful" in report.html
    assert "$61.98" in report.html
    # Charts should be present for non-empty namespace data
    assert "Cost Waste by Namespace" in report.html
    assert "Efficiency by Namespace" in report.html
