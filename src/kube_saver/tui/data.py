"""Data loading layer for the TUI.

Reads real cluster data and caches it so screens can access it without
blocking the UI thread.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from kube_saver.analyzers.alerts import Alert, evaluate_alerts
from kube_saver.analyzers.cost_waste import CostWasteReport, analyze_cost_waste
from kube_saver.analyzers.resource_waste import (
    ResourceWasteReport,
    analyze_resource_waste,
)
from kube_saver.collectors.k8s_client import K8sClient
from kube_saver.collectors.runtime import RuntimeCollector
from kube_saver.config import KubeSaverConfig
from kube_saver.models.core import (
    ClusterInfo,
    Currency,
    MetricSource,
    Recommendation,
)
from kube_saver.pricing.engine import PricingEngine
from kube_saver.recommenders.engine import generate_recommendations

logger = logging.getLogger(__name__)


@dataclass
class TUIData:
    """All pre-computed data for the TUI screens."""

    connected: bool = False
    error: str | None = None
    cluster: ClusterInfo | None = None
    resource_report: ResourceWasteReport | None = None
    cost_report: CostWasteReport | None = None
    recommendations: list[Recommendation] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    currency: Currency = Currency.USD
    exchange_rate: float = 1.0
    metrics_available: bool = False
    metric_source: MetricSource = MetricSource.ESTIMATED
    loaded_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)


def load_data(config: KubeSaverConfig) -> TUIData:
    """Load and analyze all cluster data. Returns a TUIData snapshot."""
    data = TUIData(
        currency=config.currency,
        exchange_rate=config.exchange_rate_from_usd,
    )

    try:
        client = K8sClient(
            context=config.kubeconfig_context,
            exclude_namespaces=config.exclude_namespaces,
        )
        client.connect()
    except Exception as exc:
        data.error = f"Connection failed: {exc}"
        logger.warning("K8s connection failed: %s", exc)
        return data

    try:
        data.cluster = client.get_cluster_info()
        namespaces = client.get_namespaces()
        pods = client.get_all_pods()
    except Exception as exc:
        data.error = f"Failed to read cluster: {exc}"
        logger.warning("Cluster read failed: %s", exc)
        return data

    runtime = RuntimeCollector(prefer_ebpf=True)
    runtime_result = runtime.collect_all_pods(pods)
    data.metrics_available = runtime_result.metrics_available
    data.metric_source = runtime_result.source
    data.warnings.extend(runtime_result.warnings)

    try:
        data.resource_report = analyze_resource_waste(
            namespaces, pods, data.metrics_available
        )
    except Exception as exc:
        logger.warning("Resource analysis failed: %s", exc)

    pricing = PricingEngine(provider=config.cloud_provider, tier=config.provider_tier)
    if config.pricing_has_custom_rates():
        pricing.set_rate(
            cpu_per_core_hour=config.pricing.cpu_per_core_hour_usd,
            memory_per_gb_hour=config.pricing.memory_per_gb_hour_usd,
        )

    if data.resource_report:
        try:
            data.cost_report = analyze_cost_waste(data.resource_report, pricing)
        except Exception as exc:
            logger.warning("Cost analysis failed: %s", exc)

        try:
            data.recommendations = generate_recommendations(data.resource_report, pricing)
        except Exception as exc:
            logger.warning("Recommendations failed: %s", exc)

        if data.cost_report is not None:
            try:
                data.alerts = evaluate_alerts(
                    data.resource_report,
                    data.cost_report,
                    config.alerts,
                )
            except Exception as exc:
                logger.warning("Alerts failed: %s", exc)

    data.connected = True
    data.loaded_at = datetime.now()
    return data
