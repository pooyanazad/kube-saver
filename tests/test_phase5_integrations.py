from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis
from kube_saver.analyzers.resource_waste import NamespaceAnalysis, ResourceWasteReport
from kube_saver.exporters.notifier import NotificationRateLimiter, build_daily_summary, build_spike_alert
from kube_saver.exporters.pr_generator import generate_pr_plan
from kube_saver.models.core import CostInfo, NamespaceInfo, Recommendation


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            target_kind="Deployment",
            target_name="demo",
            target_namespace="default",
            resource_type="cpu-request",
            current_value="500m",
            suggested_value="150m",
        )
    ]


def _resource_report() -> ResourceWasteReport:
    return ResourceWasteReport(
        namespaces=[NamespaceAnalysis(namespace=NamespaceInfo(name="default"), pod_count=2)],
        total_cpu_waste_millicores=1200,
        total_memory_waste_bytes=512 * 1024**2,
        total_pods=2,
        metrics_available=True,
        has_real_usage=True,
    )


def _cost_report(monthly: float = 123.45) -> CostWasteReport:
    return CostWasteReport(
        total_cost_waste=CostInfo(monthly_usd=monthly),
        namespaces=[
            NamespaceCostAnalysis(
                namespace="default",
                cost_waste=CostInfo(monthly_usd=monthly),
                cpu_waste_millicores=1200,
                memory_waste_bytes=512 * 1024**2,
                efficiency_score=40.0,
            )
        ],
    )



def test_generate_pr_plan_dry_run() -> None:
    plan = generate_pr_plan(_recommendations(), provider="github", dry_run=True)
    assert plan.provider == "github"
    assert plan.dry_run is True
    assert "500m -> 150m" in plan.body
    assert plan.branch_name.startswith("kube-saver/")



def test_build_daily_summary_for_slack() -> None:
    msg = build_daily_summary(_resource_report(), _cost_report(), channel="slack")
    assert msg.channel == "slack"
    assert "daily waste summary" in msg.title
    assert "$123.45" in msg.text
    assert "text" in msg.payload



def test_build_spike_alert_and_rate_limit() -> None:
    msg = build_spike_alert(_cost_report(monthly=900.0), threshold_monthly_usd=500.0, channel="teams")
    assert msg is not None
    assert msg.channel == "teams"

    limiter = NotificationRateLimiter(min_interval_seconds=3600)
    assert limiter.allow("critical/default") is True
    assert limiter.allow("critical/default") is False
