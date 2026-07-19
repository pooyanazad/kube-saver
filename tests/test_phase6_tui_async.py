"""Async Textual integration tests for Phase 6."""

from __future__ import annotations

from datetime import datetime

import pytest
from textual.app import App
from textual.widgets import DataTable, Static

from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis
from kube_saver.analyzers.resource_waste import (
    NamespaceAnalysis,
    PodWaste,
    ResourceWasteReport,
)
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ClusterInfo,
    CostInfo,
    Currency,
    NamespaceInfo,
    PodResourceInfo,
    Recommendation,
    ResourceQuantities,
)
from kube_saver.tui.app import (
    CostDashboard,
    Dashboard,
    NamespaceDetail,
    RecommendationsView,
    SummaryBar,
)
from kube_saver.tui.data import TUIData


class _NavApp(App):
    """Minimal wrapper that pushes the Dashboard as a screen for navigation tests."""

    def __init__(self, data: TUIData) -> None:
        super().__init__()
        self._sample = data

    def on_mount(self) -> None:
        self.push_screen(Dashboard(self._sample))


def _sample_tui_data() -> TUIData:
    pod = PodResourceInfo(
        name="api-0",
        namespace="team-a",
        workload_kind="Deployment",
        workload_name="api",
        resources=ResourceQuantities(
            cpu_millicores_request=1000,
            cpu_millicores_limit=1500,
            memory_bytes_request=1024 * 1024**2,
            memory_bytes_limit=1536 * 1024**2,
        ),
        actual=ActualUsage(
            cpu_millicores=250,
            memory_bytes=256 * 1024**2,
        ),
        restart_count=1,
    )
    pod_waste = PodWaste(
        pod=pod,
        cpu_waste_millicores=750,
        memory_waste_bytes=768 * 1024**2,
        cpu_waste_ratio=0.75,
        memory_waste_ratio=0.75,
        has_usage_data=True,
    )
    namespace = NamespaceInfo(name="team-a", labels={"env": "production"}, pod_count=1)
    ns_analysis = NamespaceAnalysis(
        namespace=namespace,
        pod_count=1,
        pod_waste=[pod_waste],
        cpu_waste_millicores=750,
        memory_waste_bytes=768 * 1024**2,
        cpu_request_millicores=1000,
        memory_request_bytes=1024 * 1024**2,
        efficiency_score=25,
    )
    resource_report = ResourceWasteReport(
        namespaces=[ns_analysis],
        total_cpu_waste_millicores=750,
        total_memory_waste_bytes=768 * 1024**2,
        total_cpu_request_millicores=1000,
        total_memory_request_bytes=1024 * 1024**2,
        total_pods=1,
        metrics_available=True,
        has_real_usage=True,
    )
    cost_report = CostWasteReport(
        total_cost_waste=CostInfo(monthly_usd=42.5, yearly_usd=510.0),
        total_requested_cost=CostInfo(monthly_usd=100.0, yearly_usd=1200.0),
        namespaces=[
            NamespaceCostAnalysis(
                namespace="team-a",
                cost_waste=CostInfo(monthly_usd=42.5, yearly_usd=510.0),
                cpu_waste_millicores=750,
                memory_waste_bytes=768 * 1024**2,
                efficiency_score=25,
            )
        ],
    )
    recommendation = Recommendation(
        target_kind="Deployment",
        target_name="api",
        target_namespace="team-a",
        container_name="api-0",
        resource_type="cpu-request",
        current_value="1000m",
        suggested_value="300m",
        confidence="high",
        reason="Observed usage stays far below requested CPU.",
        estimated_savings=CostInfo(monthly_usd=20.0, yearly_usd=240.0),
    )
    return TUIData(
        connected=True,
        cluster=ClusterInfo(
            name="demo-cluster",
            context="demo",
            provider=CloudProvider.UNKNOWN,
            version="1.30.0",
            node_count=2,
            total_cpu_millicores=4000,
            total_memory_bytes=8 * 1024**3,
        ),
        resource_report=resource_report,
        cost_report=cost_report,
        recommendations=[recommendation],
        alerts=[],
        currency=Currency.USD,
        exchange_rate=1.0,
        metrics_available=True,
        loaded_at=datetime(2024, 1, 1, 12, 0, 0),
    )


@pytest.mark.asyncio
async def test_textual_dashboard_renders() -> None:
    data = _sample_tui_data()
    app = _NavApp(data)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, Dashboard)

        summary = app.screen.query_one(SummaryBar)
        rendered = str(summary.render())
        assert "demo-cluster" in rendered
        assert "Efficiency" in rendered

        table = app.screen.query_one("#ns_table", DataTable)
        app.screen._populate_table(table)
        assert len(table.rows) == 1
        row_key = next(iter(table.rows.keys()))
        assert str(row_key.value) == "team-a"

        status = app.screen.query_one("#status", Static)
        status_text = str(status.renderable)
        assert "connected" in status_text or "USD" in status_text


@pytest.mark.asyncio
async def test_textual_navigation_between_screens() -> None:
    data = _sample_tui_data()
    app = _NavApp(data)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, Dashboard)

        app.screen.action_show_cost()
        await pilot.pause()
        assert isinstance(app.screen, CostDashboard)

        app.screen.action_go_back()
        await pilot.pause()
        assert isinstance(app.screen, Dashboard)

        app.screen.action_show_recs()
        await pilot.pause()
        assert isinstance(app.screen, RecommendationsView)

        app.screen.action_go_back()
        await pilot.pause()
        assert isinstance(app.screen, Dashboard)

        app.screen.action_drill_down()
        await pilot.pause()
        assert isinstance(app.screen, NamespaceDetail)
        ns = app.screen.namespace
        assert getattr(ns, "value", ns) == "team-a"
