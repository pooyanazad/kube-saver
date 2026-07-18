"""Local notification helpers for kube-saver.

Writes Markdown summary/alert files to disk.  No external URLs or
webhooks — everything is self-contained so kube-saver works anywhere
without external service dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport


@dataclass
class NotificationMessage:
    """Structured notification payload (written to disk as Markdown)."""

    title: str
    text: str
    filename: str
    details: list[str] = field(default_factory=list)


class NotificationRateLimiter:
    """Simple in-memory rate limiter to avoid writing the same alert twice
    within a configurable window.
    """

    def __init__(self, min_interval_seconds: int = 3600) -> None:
        self.min_interval = timedelta(seconds=min_interval_seconds)
        self._last_sent_at: dict[str, datetime] = {}

    def allow(self, key: str, now: datetime | None = None) -> bool:
        """Return True if *key* may fire now."""
        now = now or datetime.now()
        last = self._last_sent_at.get(key)
        if last and now - last < self.min_interval:
            return False
        self._last_sent_at[key] = now
        return True


# ── Builders ──────────────────────────────────────────────────────────────


def build_daily_summary(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
) -> NotificationMessage:
    """Return a Markdown daily-waste summary.

    Args:
        resource_report: Pod-level waste analysis.
        cost_report: Cost-impact analysis.

    Returns:
        A ``NotificationMessage`` ready for ``write_notification``.
    """
    title = "kube-saver daily waste summary"
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("## Overview\n")
    lines.append(f"- Pods analysed: {resource_report.total_pods}")
    lines.append(f"- CPU waste: {resource_report.total_cpu_waste_millicores:.0f} millicores")
    lines.append(f"- Memory waste: {resource_report.total_memory_waste_bytes // 1024**2} Mi")
    lines.append(f"- Monthly cost waste: ${cost_report.total_cost_waste.monthly_usd:.2f}\n")
    if cost_report.namespaces:
        lines.append("## Namespace Breakdown\n")
        lines.append("| Namespace | Monthly Waste ($) | Efficiency % |")
        lines.append("|-----------|------------------|-------------|")
        for ns in cost_report.namespaces:
            lines.append(f"| {ns.namespace} | {ns.cost_waste.monthly_usd:.2f} | {ns.efficiency_score:.1f} |")
    text = "\n".join(lines)
    return NotificationMessage(title=title, text=text, filename="daily-summary.md")


def build_spike_alert(
    cost_report: CostWasteReport,
    *,
    threshold_monthly_usd: float,
) -> NotificationMessage | None:
    """Return a spike alert if waste exceeds the threshold.

    Args:
        cost_report: Cost-impact analysis.
        threshold_monthly_usd: Monthly USD waste that triggers the alert.

    Returns:
        A ``NotificationMessage`` or ``None`` if under threshold.
    """
    if cost_report.total_cost_waste.monthly_usd < threshold_monthly_usd:
        return None
    title = "kube-saver critical waste spike"
    waste = cost_report.total_cost_waste.monthly_usd
    lines: list[str] = [
        f"# {title}\n",
        f"Monthly waste reached **${waste:.2f}** (threshold: ${threshold_monthly_usd:.2f}).\n",
        "## Top Namespaces\n",
    ]
    for ns in sorted(cost_report.namespaces, key=lambda n: -n.cost_waste.monthly_usd)[:5]:
        lines.append(f"- **{ns.namespace}**: ${ns.cost_waste.monthly_usd:.2f}")
    return NotificationMessage(title=title, text="\n".join(lines), filename="spike-alert.md")


# ── Writer ────────────────────────────────────────────────────────────────


def write_notification(
    msg: NotificationMessage,
    output_dir: str | Path = ".",
) -> Path:
    """Write *msg* to ``<output_dir>/<filename>`` and return the path.

    Creates *output_dir* if it doesn't exist.  Each call appends a
    timestamp suffix so historical alerts are preserved.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    stem = Path(msg.filename).stem
    suffix = Path(msg.filename).suffix or ".md"
    path = out / f"{stem}-{ts}{suffix}"
    path.write_text(msg.text + "\n", encoding="utf-8")
    return path


__all__ = [
    "NotificationMessage",
    "NotificationRateLimiter",
    "build_daily_summary",
    "build_spike_alert",
    "write_notification",
]
