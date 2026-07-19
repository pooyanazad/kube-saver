"""HTML report generation for kube-saver.

Generates a self-contained HTML report with pure CSS bar charts.
No external CDN or JavaScript dependencies — works fully offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from kube_saver.analyzers.cost_waste import CostWasteReport, NamespaceCostAnalysis
from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.models.core import Recommendation


@dataclass
class HtmlReportResult:
    """Generated HTML management report.

    Attributes:
        html: Complete HTML string (self-contained, no external resources).
        title: Report title used in ``<title>`` and ``<h1>``.
    """

    html: str
    title: str = "kube-saver report"


def _ns_bar_chart(namespaces: list[NamespaceCostAnalysis]) -> str:
    """Return a pure-CSS horizontal bar chart for namespace cost waste."""
    if not namespaces:
        return ""
    # namespaces is list of NamespaceCostAnalysis
    max_waste = max(ns.cost_waste.monthly_usd for ns in namespaces) or 1.0
    rows: list[str] = []
    for ns in sorted(namespaces, key=lambda n: -n.cost_waste.monthly_usd):
        pct = (ns.cost_waste.monthly_usd / max_waste) * 100
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{escape(ns.namespace)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct:.1f}%">'
            f'${ns.cost_waste.monthly_usd:.2f}'
            f"</div></div></div>"
        )
    return "\n".join(rows)


def _efficiency_chart(namespaces: list[NamespaceCostAnalysis]) -> str:
    """Return a pure-CSS chart for namespace efficiency scores."""
    if not namespaces:
        return ""
    rows: list[str] = []
    for ns in sorted(namespaces, key=lambda n: n.efficiency_score):
        score = ns.efficiency_score
        color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 50 else "#ef4444"
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{escape(ns.namespace)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill eff" style="width:{score:.1f}%;background:{color}">'
            f"{score:.1f}%"
            f"</div></div></div>"
        )
    return "\n".join(rows)


_CSS = """body{font-family:system-ui,-apple-system,sans-serif;max-width:1100px;margin:0 auto;
padding:24px;color:#1f2937;background:#fff}
h1,h2{color:#111827}
h1{border-bottom:2px solid #3b82f6;padding-bottom:8px}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
gap:12px;margin:20px 0}
.card{border:1px solid #d1d5db;border-radius:8px;padding:16px;background:#f9fafb;
text-align:center}
.card strong{display:block;font-size:.85rem;color:#6b7280;margin-bottom:4px}
.card .val{font-size:1.5rem;font-weight:700;color:#111827}
.chart-section{margin:24px 0}
.bar-row{display:flex;align-items:center;margin-bottom:6px}
.bar-label{min-width:140px;text-align:right;padding-right:10px;font-size:.85rem;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;height:24px;background:#e5e7eb;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;font-size:.75rem;color:#fff;
padding:0 6px;min-width:40px;display:flex;align-items:center;white-space:nowrap}
table{border-collapse:collapse;width:100%;margin-top:16px}
th,td{border:1px solid #d1d5db;padding:8px 10px;text-align:left;font-size:.9rem}
th{background:#f3f4f6;position:sticky;top:0}
@media print{body{padding:0}.bar-track{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
"""


def generate_html_report(
    resource_report: ResourceWasteReport,
    cost_report: CostWasteReport,
    recommendations: list[Recommendation],
) -> HtmlReportResult:
    """Generate a self-contained HTML report with charts.

    Args:
        resource_report: Pod-level waste analysis.
        cost_report: Cost-impact analysis.
        recommendations: Optimization recommendations.

    Returns:
        ``HtmlReportResult`` with complete HTML (no external deps).
    """
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
    ns_table_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(ns.namespace)}</td>"
            f"<td>${ns.cost_waste.monthly_usd:.2f}</td>"
            f"<td>{ns.efficiency_score:.1f}%</td>"
            "</tr>"
        )
        for ns in cost_report.namespaces
    )
    waste_chart = _ns_bar_chart(cost_report.namespaces)
    eff_chart = _efficiency_chart(cost_report.namespaces)

    charts_html = ""
    if waste_chart:
        charts_html += (
            '<h2>Cost Waste by Namespace</h2>'
            '<div class="chart-section">' + waste_chart + "</div>"
        )
    if eff_chart:
        charts_html += (
            '<h2>Efficiency by Namespace</h2>'
            '<div class="chart-section">' + eff_chart + "</div>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>kube-saver report</title>
<style>{_CSS}</style>
</head>
<body>
<h1>kube-saver executive summary</h1>
<div class="summary">
  <div class="card"><strong>Total pods</strong><span class="val">{resource_report.total_pods}</span></div>
  <div class="card"><strong>CPU waste</strong><span class="val">{resource_report.total_cpu_waste_millicores:.0f}m</span></div>
  <div class="card"><strong>Memory waste</strong><span class="val">{resource_report.total_memory_waste_bytes // 1024**2}Mi</span></div>
  <div class="card"><strong>Monthly savings</strong><span class="val">${cost_report.total_cost_waste.monthly_usd:.2f}</span></div>
</div>

{charts_html}

<h2>Namespace Breakdown</h2>
<table>
<thead><tr><th>Namespace</th><th>Monthly waste (USD)</th><th>Efficiency</th></tr></thead>
<tbody>{ns_table_rows}</tbody>
</table>

<h2>Recommendations ({len(recommendations)})</h2>
<table>
<thead><tr><th>Namespace</th><th>Kind</th><th>Name</th><th>Resource</th><th>Current</th><th>Suggested</th></tr></thead>
<tbody>{rec_rows}</tbody>
</table>
</body>
</html>""".strip()
    return HtmlReportResult(html=html)


__all__ = ["HtmlReportResult", "generate_html_report"]
