"""Real-cluster Phase 2 validation script.

Runs the full analysis pipeline against the live cluster and prints results.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from kube_saver.collectors.k8s_client import K8sClient
from kube_saver.collectors.metrics import MetricsCollector
from kube_saver.analyzers.resource_waste import analyze_resource_waste
from kube_saver.analyzers.cost_waste import analyze_cost_waste
from kube_saver.analyzers.health import pod_health_score
from kube_saver.analyzers.alerts import evaluate_alerts
from kube_saver.config import load_config
from kube_saver.pricing import PricingEngine


def main() -> None:
    console = Console()
    config = load_config()
    pricing = PricingEngine(provider=config.cloud_provider)

    console.print("\n[bold cyan]kube-saver Phase 2 — Real Cluster Analysis[/bold cyan]\n")

    client = K8sClient()
    try:
        client.connect()
    except Exception as e:
        console.print(f"[red]Failed to connect to cluster:[/red] {e}")
        return

    cluster = client.get_cluster_info()
    console.print(f"[green]Connected to:[/green] {cluster.name} (v{cluster.version})")

    namespaces = client.get_namespaces()
    pods = client.get_all_pods()
    console.print(f"[green]Namespaces:[/green] {len(namespaces)}  [green]Pods:[/green] {len(pods)}")

    metrics = MetricsCollector()
    metrics.collect_all_pods(pods)
    metrics_available = bool(metrics.available)
    console.print(f"[green]Metrics available:[/green] {metrics_available}  [green]Source:[/green] {metrics.source.value}")

    resource_report = analyze_resource_waste(namespaces, pods, metrics_available)

    console.print(f"\n[bold]Resource Waste Summary[/bold]")
    console.print(f"  Total CPU requested:  {resource_report.total_cpu_request_millicores:.0f}m")
    console.print(f"  Total CPU wasted:     {resource_report.total_cpu_waste_millicores:.0f}m")
    console.print(f"  Total Mem requested:  {resource_report.total_memory_request_bytes / 1024**3:.2f}Gi")
    console.print(f"  Total Mem wasted:     {resource_report.total_memory_waste_bytes / 1024**3:.2f}Gi")

    cost_report = analyze_cost_waste(resource_report, pricing)

    currency = config.currency
    rate = config.exchange_rate_from_usd
    sym = currency.symbol

    console.print(f"\n[bold]Cost Waste Summary[/bold]")
    console.print(f"  Total requested cost/month: {sym}{cost_report.total_requested_cost.monthly_usd * rate:.2f} {currency.code}")
    console.print(f"  Total waste cost/month:     {sym}{cost_report.total_cost_waste.monthly_usd * rate:.2f} {currency.code}")
    console.print(f"  Annual waste estimate:      {sym}{cost_report.total_cost_waste.yearly_usd * rate:.2f} {currency.code}")
    console.print(f"  Waste ratio:                {cost_report.waste_ratio:.1%}")

    if cost_report.namespaces:
        ns_table = Table(title="Namespace Cost Breakdown", show_lines=False)
        ns_table.add_column("Namespace", style="cyan")
        ns_table.add_column("Pods", justify="right")
        ns_table.add_column("CPU Waste", justify="right")
        ns_table.add_column("Mem Waste", justify="right")
        ns_table.add_column(f"/month ({currency.code})", justify="right")
        ns_table.add_column("Efficiency", justify="right")

        for ns in cost_report.namespaces:
            ns_pods = next(
                (n for n in resource_report.namespaces if n.namespace.name == ns.namespace), None
            )
            pod_count = len(ns_pods.pod_waste) if ns_pods else 0
            ns_table.add_row(
                ns.namespace,
                str(pod_count),
                f"{ns.cpu_waste_millicores:.0f}m",
                f"{ns.memory_waste_bytes / 1024**2:.0f}Mi",
                f"{sym}{ns.cost_waste.monthly_usd * rate:.2f}",
                f"{ns.efficiency_score:.1f}%",
            )

        console.print(ns_table)

    alerts = evaluate_alerts(resource_report, cost_report, config.alerts)
    if alerts:
        alert_table = Table(title="Alerts")
        alert_table.add_column("Level", style="bold")
        alert_table.add_column("Scope")
        alert_table.add_column("Target")
        alert_table.add_column("Message")
        for alert in alerts:
            style = "red" if alert.level == "critical" else "yellow"
            msg = alert.message
            if "Monthly waste" in msg:
                msg = msg.replace("$", sym)
            alert_table.add_row(Text(alert.level, style=style), alert.scope, alert.target, msg)
        console.print(alert_table)
    else:
        console.print("[green]No alerts triggered.[/green]")

    from kube_saver.recommenders.engine import generate_recommendations
    recs = generate_recommendations(resource_report, pricing)

    if recs:
        rec_table = Table(title=f"Top Recommendations ({len(recs)} total)")
        rec_table.add_column("Target", style="cyan")
        rec_table.add_column("Type")
        rec_table.add_column("Current", justify="right")
        rec_table.add_column("Suggested", justify="right")
        rec_table.add_column("Confidence")
        rec_table.add_column(f"/month ({currency.code})", justify="right")
        for rec in recs[:10]:
            rec_table.add_row(
                f"{rec.target_namespace}/{rec.target_name}",
                rec.resource_type,
                rec.current_value,
                rec.suggested_value,
                rec.confidence,
                f"{sym}{rec.estimated_savings.monthly_usd * rate:.2f}",
            )
        console.print(rec_table)
    else:
        console.print("[green]No recommendations — cluster looks healthy![/green]")

    console.print(f"\n[dim]Analysis complete. kube-saver v0.2.0-dev | currency: {currency.code} (rate {rate})[/dim]\n")




if __name__ == "__main__":
    main()
