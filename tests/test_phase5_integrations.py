"""Phase 5 integration tests — PR plan, notifications, exporters, server."""

from pathlib import Path

from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis
from kube_saver.analyzers.resource_waste import NamespaceAnalysis, ResourceWasteReport
from kube_saver.exporters.notifier import (
    NotificationRateLimiter,
    build_daily_summary,
    build_spike_alert,
    write_notification,
)
from kube_saver.exporters.pr_generator import apply_plan_locally, generate_pr_plan
from kube_saver.models.core import CostInfo, NamespaceInfo, Recommendation


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            target_kind="Deployment",
            target_name="demo",
            target_namespace="default",
            container_name="app",
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
    plan = generate_pr_plan(_recommendations())
    assert plan.dry_run is True
    assert "500m" in plan.body
    assert "150m" in plan.body
    assert plan.branch_name.startswith("kube-saver/")
    assert "summary.md" in plan.files
    assert "apply-patches.sh" in plan.files
    patch = plan.files["apply-patches.sh"]
    assert "--type=strategic" in patch
    assert '"name":"app"' in patch
    assert "--type=merge" not in patch


def test_pr_plan_skips_ephemeral_replicaset_target() -> None:
    recommendation = _recommendations()[0]
    recommendation.target_kind = "ReplicaSet"

    patch = generate_pr_plan([recommendation]).files["apply-patches.sh"]

    assert "Skipped default/ReplicaSet/demo" in patch
    assert "kubectl patch" not in patch


def test_apply_plan_locally(tmp_path: Path) -> None:
    plan = generate_pr_plan(_recommendations())
    out = apply_plan_locally(plan, output_dir=tmp_path)
    assert (out / "summary.md").exists()
    assert (out / "apply-patches.sh").exists()
    assert (out / "README.md").exists()
    content = (out / "summary.md").read_text()
    assert "150m" in content



def test_build_daily_summary() -> None:
    msg = build_daily_summary(_resource_report(), _cost_report())
    assert "daily waste summary" in msg.title
    assert "$123.45" in msg.text
    assert msg.filename == "daily-summary.md"


def test_build_spike_alert_and_rate_limit() -> None:
    msg = build_spike_alert(_cost_report(monthly=900.0), threshold_monthly_usd=500.0)
    assert msg is not None
    assert "spike" in msg.title

    # Under threshold → None
    assert build_spike_alert(_cost_report(monthly=100.0), threshold_monthly_usd=500.0) is None

    limiter = NotificationRateLimiter(min_interval_seconds=3600)
    assert limiter.allow("critical/default") is True
    assert limiter.allow("critical/default") is False


def test_write_notification(tmp_path: Path) -> None:
    """write_notification should create a Markdown file with timestamp."""
    msg = build_daily_summary(_resource_report(), _cost_report())
    path = write_notification(msg, output_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".md"
    assert path.stem.startswith("daily-summary-")
    content = path.read_text()
    assert "kube-saver daily waste summary" in content
    assert "$123.45" in content


def test_write_notification_does_not_overwrite(tmp_path: Path) -> None:
    """Calling write_notification twice should produce two distinct files."""
    msg = build_daily_summary(_resource_report(), _cost_report())
    p1 = write_notification(msg, output_dir=tmp_path)
    p2 = write_notification(msg, output_dir=tmp_path)
    assert p1 != p2
    assert p1.exists() and p2.exists()
