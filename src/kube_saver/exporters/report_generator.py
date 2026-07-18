"""HTML report generation for kube-saver."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.models.core import Recommendation


@dataclass
class HtmlReportResult:
    """Generated HTML management report."""

    html: str
    title: str = "kube-saver report"
    pdf_supported: bool = False


def generate_html_report(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
    recommendations: list[Recommendation],
) -> HtmlReportResult:
    """Generate a simple HTML report for management review."""
    rec_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(rec.target_namespace)}</td>"
            f"<td>{escape(rec.target_kind)}</td>"
            f"<td>{escape(rec.target_name)}</td>"
            f"<td>{escape(rec.resource_type)}</td>"
            f"<td>{escape(rec.current_value)}</td>"
            f"<td>{escape(rec.suggested_value)}</td>"
            "</tr>"
        )
        for rec in recommendations
    )
    ns_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(ns.namespace)}</td>"
            f"<td>{ns.cost_waste.monthly_usd:.2f}</td>"
            f"<td>{ns.efficiency_score:.1f}</td>"
            "</tr>"
        )
        for ns in cost_report.namespaces
    )
    html = f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>kube-saver report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>kube-saver executive summary</h1>
  <div class=\"summary\">
    <div class=\"card\"><strong>Total pods</strong><br>{resource_report.total_pods}</div>
    <div class=\"card\"><strong>CPU waste</strong><br>{resource_report.total_cpu_waste_millicores:.0f}m</div>
    <div class=\"card\"><strong>Memory waste</strong><br>{resource_report.total_memory_waste_bytes // 1024**2}Mi</div>
    <div class=\"card\"><strong>Monthly savings potential</strong><br>${cost_report.total_cost_waste.monthly_usd:.2f}</div>
  </div>

  <h2>Namespace breakdown</h2>
  <table>
    <thead><tr><th>Namespace</th><th>Monthly waste (USD)</th><th>Efficiency</th></tr></thead>
    <tbody>{ns_rows}</tbody>
  </table>

  <h2>Recommendations</h2>
  <table>
    <thead><tr><th>Namespace</th><th>Kind</th><th>Name</th><th>Resource</th><th>Current</th><th>Suggested</th></tr></thead>
    <tbody>{rec_rows}</tbody>
  </table>
</body>
</html>
""".strip()
    return HtmlReportResult(html=html)


__all__ = ["HtmlReportResult", "generate_html_report"]
