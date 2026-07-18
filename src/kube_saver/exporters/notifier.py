"""Slack and Teams notification helpers for kube-saver."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport


@dataclass
class NotificationMessage:
    """Structured outgoing notification payload."""

    channel: str
    title: str
    text: str
    payload: dict[str, str] = field(default_factory=dict)


class NotificationRateLimiter:
    """Simple in-memory rate limiter for alerts."""

    def __init__(self, min_interval_seconds: int = 3600) -> None:
        self.min_interval = timedelta(seconds=min_interval_seconds)
        self._last_sent_at: dict[str, datetime] = {}

    def allow(self, key: str, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        last = self._last_sent_at.get(key)
        if last and now - last < self.min_interval:
            return False
        self._last_sent_at[key] = now
        return True


def build_daily_summary(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
    *,
    channel: str = "slack",
) -> NotificationMessage:
    title = "kube-saver daily waste summary"
    text = (
        f"Pods: {resource_report.total_pods} | "
        f"CPU waste: {resource_report.total_cpu_waste_millicores:.0f}m | "
        f"Memory waste: {resource_report.total_memory_waste_bytes // 1024**2}Mi | "
        f"Monthly waste: ${cost_report.total_cost_waste.monthly_usd:.2f}"
    )
    if channel == "teams":
        payload = {"title": title, "text": text}
    else:
        payload = {"text": f"*{title}*\n{text}"}
    return NotificationMessage(channel=channel, title=title, text=text, payload=payload)


def build_spike_alert(
    cost_report: CostWasteReport,
    *,
    threshold_monthly_usd: float,
    channel: str = "slack",
) -> NotificationMessage | None:
    if cost_report.total_cost_waste.monthly_usd < threshold_monthly_usd:
        return None
    title = "kube-saver critical waste spike"
    text = f"Monthly waste reached ${cost_report.total_cost_waste.monthly_usd:.2f}"
    payload = {"text": text} if channel == "slack" else {"title": title, "text": text}
    return NotificationMessage(channel=channel, title=title, text=text, payload=payload)


__all__ = [
    "NotificationMessage",
    "NotificationRateLimiter",
    "build_daily_summary",
    "build_spike_alert",
]
