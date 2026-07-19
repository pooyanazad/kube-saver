#!/usr/bin/env python3
"""kube-saver demo — shows the full pipeline with realistic fake data.

Run:  source .venv/bin/activate && python3 examples/demo.py
No Kubernetes cluster needed — purely demonstrates what kube-saver does.
"""

from __future__ import annotations

from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ClusterInfo,
    CostInfo,
    MetricSource,
    NamespaceInfo,
    NamespaceWaste,
    PodResourceInfo,
    Recommendation,
    ResourceQuantities,
    ResourceWaste,
    WasteReport,
)
from kube_saver.pricing.engine import PricingEngine
from kube_saver.config import load_config, default_config_yaml

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich import box
    from rich.text import Text
    from rich.progress import BarColumn, Progress, TextColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("[rich not installed — falling back to plain text output]")


# ── Fake cluster data ──────────────────────────────────────────────────────

def build_fake_cluster() -> ClusterInfo:
    return ClusterInfo(
        name="prod-us-east-1",
        context="arn:aws:eks:us-east-1:123456789:cluster/prod",
        provider=CloudProvider.AWS,
        version="1.29.3",
        node_count=12,
        total_cpu_millicores=480_000,   # 480 cores
        total_memory_bytes=2_048 * 1024**3,  # 2 TB
    )


def build_fake_namespaces() -> list[NamespaceInfo]:
    return [
        NamespaceInfo(
            name="default",
            labels={"env": "production", "team": "platform"},
            pod_count=84,
        ),
        NamespaceInfo(
            name="payments",
            labels={"env": "production", "team": "payments"},
            pod_count=56,
        ),
        NamespaceInfo(
            name="analytics",
            labels={"env": "production", "team": "data"},
            pod_count=112,
        ),
        NamespaceInfo(
            name="staging",
            labels={"env": "staging", "team": "platform"},
            pod_count=42,
        ),
        NamespaceInfo(
            name="monitoring",
            labels={"env": "production", "team": "sre"},
            pod_count=18,
        ),
    ]


# Each tuple: (pod_name, namespace, workload_name, cpu_req_m, cpu_actual_m, mem_req_Gi, mem_actual_Gi, restarts)
FAKE_PODS = [
    # default namespace — heavy waste
    ("api-gateway-7f8b9c-xk2j",   "default", "api-gateway",   4000,  310,  8, 1.2, 0),
    ("auth-service-a1b2c3-mn4p",  "default", "auth-service",  2000,  180,  4, 0.9, 0),
    ("config-server-5d6e7f-qr9s", "default", "config-server", 2000,   45,  4, 0.3, 0),
    ("rate-limiter-8g9h0j-tu3v",  "default", "rate-limiter",  1000,   12,  2, 0.1, 0),

    # payments — moderate waste
    ("checkout-api-1a2b3c-xy78",  "payments", "checkout-api",  3000,  890,  6, 2.1, 1),
    ("payment-proc-4d5e6f-op23",  "payments", "payment-proc",  4000, 1200,  8, 3.4, 0),
    ("webhook-relay-7g8h9i-ab45","payments", "webhook-relay",  500,   40,  1, 0.2, 0),

    # analytics — high waste (bursty workload, over-provisioned)
    ("spark-driver-1x2y3z-cd67",  "analytics", "spark-driver", 8000,  420, 16, 2.8, 3),
    ("spark-exec-4a5b6e-ef89",    "analytics", "spark-exec",   4000,  280,  8, 1.5, 0),
    ("dashboard-api-f7g8h9-gh12", "analytics", "dashboard-api",1000,   90,  2, 0.4, 0),

    # staging — efficient (right-sized)
    ("staging-app-1k2l3m-jk34",   "staging", "staging-app",   1000,  650,  2, 1.1, 0),
    ("staging-test-4n5o6p-lm56",  "staging", "staging-test",   500,  420,  1, 0.7, 0),

    # monitoring — efficient
    ("prometheus-1q2r3s-mn78",    "monitoring", "prometheus",  2000, 1400,  8, 5.2, 0),
    ("grafana-4t5u6v-op90",       "monitoring", "grafana",      500,  180,  1, 0.3, 0),
    ("alertmanager-7w8x9y-qr12",  "monitoring", "alertmanager", 500,  290,  1, 0.4, 0),
]


def build_fake_pods() -> list[PodResourceInfo]:
    """Build PodResourceInfo objects from the FAKE_PODS table."""
    results: list[PodResourceInfo] = []
    for (
        pod_name, namespace, workload, cpu_req_m, cpu_act_m,
        mem_req_gi, mem_act_gi, restarts,
    ) in FAKE_PODS:
        results.append(
            PodResourceInfo(
                name=pod_name,
                namespace=namespace,
                node_name=f"node-{namespace[:4]}",
                workload_kind="Deployment",
                workload_name=workload,
                resources=ResourceQuantities(
                    cpu_millicores_request=float(cpu_req_m),
                    cpu_millicores_limit=float(cpu_req_m * 2),
                    memory_bytes_request=mem_req_gi * 1024**3,
                    memory_bytes_limit=int(mem_req_gi * 1.5 * 1024**3),
                ),
                actual=ActualUsage(
                    cpu_millicores=float(cpu_act_m),
                    memory_bytes=int(mem_act_gi * 1024**3),
                    source=MetricSource.METRICS_SERVER,
                    sample_count=100,
                ),
                restart_count=restarts,
            )
        )
    return results


# ── Analysis pipeline ──────────────────────────────────────────────────────

def calculate_waste(pods: list[PodResourceInfo]) -> tuple[
    ResourceWaste,
    ResourceWaste,
    list[NamespaceWaste],
]:
    """Calculate waste per pod, per namespace, and totals."""
    ns_waste: dict[str, NamespaceWaste] = {}
    all_namespaces = build_fake_namespaces()
    ns_map = {ns.name: ns for ns in all_namespaces}

    total = ResourceWaste()
    total_requested = ResourceWaste()

    for pod in pods:
        cpu_waste = max(pod.resources.cpu_millicores_request - pod.actual.cpu_millicores, 0)
        mem_waste = max(pod.resources.memory_bytes_request - pod.actual.memory_bytes, 0)

        total.cpu_millicores += cpu_waste
        total.memory_bytes += mem_waste
        total_requested.cpu_millicores += pod.resources.cpu_millicores_request
        total_requested.memory_bytes += pod.resources.memory_bytes_request

        ns_name = pod.namespace
        if ns_name not in ns_waste:
            ns_waste[ns_name] = NamespaceWaste(
                namespace=ns_map.get(ns_name, NamespaceInfo(name=ns_name)),
                pod_count=0,
            )
        nsw = ns_waste[ns_name]
        nsw.pod_count += 1
        nsw.waste.cpu_millicores += cpu_waste
        nsw.waste.memory_bytes += mem_waste

    # Compute efficiency scores per namespace
    for nsw in ns_waste.values():
        req_cpu = sum(
            p.resources.cpu_millicores_request
            for p in pods
            if p.namespace == nsw.namespace.name
        )
        if req_cpu > 0:
            utilized = sum(
                p.actual.cpu_millicores
                for p in pods
                if p.namespace == nsw.namespace.name
            ) / req_cpu
            nsw.efficiency_score = round(utilized * 100, 1)

    # Sort by waste descending
    sorted_ns = sorted(ns_waste.values(), key=lambda x: x.waste.cpu_millicores, reverse=True)

    return total, total_requested, sorted_ns


def generate_recommendations(pods: list[PodResourceInfo]) -> list[Recommendation]:
    """Generate recommendations based on actual usage."""
    recs: list[Recommendation] = []
    for pod in pods:
        req = pod.resources
        act = pod.actual

        # CPU request recommendation
        if req.cpu_millicores_request > 0:
            cpu_util = act.cpu_millicores / req.cpu_millicores_request
            if cpu_util < 0.3:
                suggested = max(act.cpu_millicores * 1.5, 50)  # 150% of actual
                recs.append(Recommendation(
                    target_name=pod.workload_name,
                    target_namespace=pod.namespace,
                    container_name=pod.name.split("-")[0],
                    resource_type="cpu-request",
                    current_value=f"{int(req.cpu_millicores_request)}m",
                    suggested_value=f"{int(suggested)}m",
                    confidence="high" if cpu_util < 0.15 else "medium",
                    reason=f"Utilization only {cpu_util:.0%} — suggested 150% of actual usage",
                ))

        # Memory request recommendation
        if req.memory_bytes_request > 0:
            mem_util = act.memory_bytes / req.memory_bytes_request
            if mem_util < 0.3:
                suggested = max(act.memory_bytes * 1.2, 64 * 1024**2)
                recs.append(Recommendation(
                    target_name=pod.workload_name,
                    target_namespace=pod.namespace,
                    container_name=pod.name.split("-")[0],
                    resource_type="memory-request",
                    current_value=_fmt_bytes(req.memory_bytes_request),
                    suggested_value=_fmt_bytes(int(suggested)),
                    confidence="high" if mem_util < 0.15 else "medium",
                    reason=f"Utilization only {mem_util:.0%} — suggested 120% of actual usage",
                ))

    return sorted(recs, key=lambda r: r.estimated_savings.monthly_usd, reverse=True)


def _fmt_bytes(b: int) -> str:
    if b >= 1024**3:
        return f"{b / 1024**3:.1f}Gi"
    if b >= 1024**2:
        return f"{b / 1024**2:.0f}Mi"
    return f"{b}B"


# ── Rich display ───────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def display_report(
    cluster: ClusterInfo,
    total_waste: ResourceWaste,
    total_requested: ResourceWaste,
    ns_waste: list[NamespaceWaste],
    recommendations: list[Recommendation],
    engine: PricingEngine,
) -> None:
    console = Console()

    # ── Header ─────────────────────────────────────────────────────────────
    console.print()
    header = Text()
    header.append("  kube-saver ", style="bold cyan")
    header.append(" v1.0.0  ", style="dim")
    header.append("│ ", style="dim")
    header.append(f"Cluster: {cluster.name} ", style="bold white")
    header.append("│ ", style="dim")
    header.append(f"Provider: {cluster.provider.value.upper()} ", style="bold green")
    header.append("│ ", style="dim")
    header.append(f"Version: {cluster.version} ", style="dim")
    header.append("│ ", style="dim")
    header.append(f"Nodes: {cluster.node_count}", style="bold")
    console.print(Panel(header, box=box.DOUBLE, border_style="cyan"))

    # ── Summary cards ──────────────────────────────────────────────────────
    total_cost = engine.cost_from_waste(total_waste)
    req_cost = engine.cost_from_waste(total_requested)
    total_pods = sum(nw.pod_count for nw in ns_waste)
    overall_eff = ((total_requested.cpu_millicores - total_waste.cpu_millicores)
                   / max(total_requested.cpu_millicores, 1) * 100)

    waste_cpu_cores = total_waste.cpu_millicores / 1000
    waste_mem_gb = total_waste.memory_bytes / 1024**3
    total_cpu_cores = total_requested.cpu_millicores / 1000
    total_mem_gb = total_requested.memory_bytes / 1024**3

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="bold cyan")
    summary.add_column(style="bold white", justify="right")
    summary.add_column()
    summary.add_row("Total Waste",
                     f"${total_cost.monthly_usd:,.2f}/mo",
                     f"  ({total_cost.yearly_usd:,.2f}/yr)")
    summary.add_row("Total Cost",
                     f"${req_cost.monthly_usd:,.2f}/mo",
                     "")
    summary.add_row("CPU Waste",
                     f"{waste_cpu_cores:,.0f} of {total_cpu_cores:,.0f} cores",
                     f"  ({total_waste.cpu_millicores/total_requested.cpu_millicores*100:.0f}% wasted)")
    summary.add_row("Memory Waste",
                     f"{waste_mem_gb:,.0f} of {total_mem_gb:,.0f} GB",
                     f"  ({total_waste.memory_bytes/total_requested.memory_bytes*100:.0f}% wasted)")
    summary.add_row("Pods", str(total_pods), "")
    summary.add_row("Efficiency",
                     f"{overall_eff:.0f}%",
                     "  [red]◄ low  high ►[/red]")

    console.print(Panel(summary, title="[bold]Cluster Summary[/bold]", border_style="blue"))

    # ── Namespace waste table ──────────────────────────────────────────────
    ns_table = Table(
        title="Namespace Waste Breakdown",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        title_style="bold magenta",
        header_style="bold cyan",
    )
    ns_table.add_column("#", style="dim", width=3)
    ns_table.add_column("Namespace", style="bold white", min_width=16)
    ns_table.add_column("Pods", justify="right")
    ns_table.add_column("CPU Waste", justify="right")
    ns_table.add_column("Mem Waste", justify="right")
    ns_table.add_column("Monthly $", justify="right", style="bold yellow")
    ns_table.add_column("Efficiency", justify="center")

    for i, nw in enumerate(ns_waste, 1):
        ns_cost = engine.cost_from_waste(nw.waste)
        eff = nw.efficiency_score
        color = _score_color(eff)
        eff_bar = f"[{color}]{eff:.0f}%[/{color}]"
        ns_table.add_row(
            str(i),
            nw.namespace.name,
            str(nw.pod_count),
            f"{nw.waste.cpu_millicores/1000:.1f} cores",
            f"{nw.waste.memory_bytes/1024**3:.0f} GB",
            f"${ns_cost.monthly_usd:,.0f}",
            eff_bar,
        )
    console.print(ns_table)

    # ── Recommendations table ──────────────────────────────────────────────
    rec_table = Table(
        title="Top Recommendations",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        title_style="bold magenta",
        header_style="bold cyan",
    )
    rec_table.add_column("#", style="dim", width=3)
    rec_table.add_column("Workload", style="bold white", min_width=18)
    rec_table.add_column("Namespace", style="dim")
    rec_table.add_column("Resource", style="bold")
    rec_table.add_column("Current", style="red")
    rec_table.add_column("→")
    rec_table.add_column("Suggested", style="green")
    rec_table.add_column("Confidence", justify="center")
    rec_table.add_column("Reason", max_width=50)

    for i, rec in enumerate(recommendations[:10], 1):
        conf_color = "green" if rec.confidence == "high" else "yellow"
        rec_table.add_row(
            str(i),
            rec.target_name,
            rec.target_namespace,
            rec.resource_type,
            rec.current_value,
            "→",
            f"[green]{rec.suggested_value}[/green]",
            f"[{conf_color}]{rec.confidence}[/{conf_color}]",
            rec.reason,
        )
    console.print(rec_table)

    # ── Footer ─────────────────────────────────────────────────────────────
    console.print(
        Panel(
            f"[bold green]Total estimated savings:[/bold green] "
            f"[yellow]${total_cost.monthly_usd:,.2f}/month[/yellow] "
            f"([bold]${total_cost.yearly_usd:,.2f}/year[/bold])",
            title="[bold cyan]Savings Potential[/bold cyan]",
            border_style="yellow",
        )
    )
    console.print(
        "[dim]kube-saver v0.1.0 — https://github.com/pooyanazad/kube-saver[/dim]\n"
    )


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    if not HAS_RICH:
        print("Error: rich is required. Install with: pip install rich")
        return 1

    console = Console()
    console.print("\n[bold cyan]kube-saver demo[/bold cyan] — using realistic fake data\n")

    # Build fake data
    cluster = build_fake_cluster()
    pods = build_fake_pods()

    # Load config
    config = load_config()
    console.print(f"[dim]Config: provider={config.cloud_provider.value}, tier={config.provider_tier}[/dim]")

    # Pricing engine
    engine = PricingEngine(provider=cluster.provider, tier=config.provider_tier)
    console.print(f"[dim]Pricing: {engine.rate.label} — ${engine.rate.cpu_per_core_hour_usd}/core/hr, ${engine.rate.memory_per_gb_hour_usd}/GB/hr[/dim]\n")

    # Analyze
    total_waste, total_requested, ns_waste = calculate_waste(pods)

    # Annotate savings
    for nw in ns_waste:
        nw.cost_waste = engine.cost_from_waste(nw.waste)

    # Recommendations
    recommendations = generate_recommendations(pods)
    for rec in recommendations:
        if rec.resource_type == "cpu-request":
            cpu_m = float(rec.suggested_value.replace("m", ""))
            rec.estimated_savings = engine.cost_from_resources(
                cpu_millicores=float(rec.current_value.replace("m", "")) - cpu_m,
                memory_bytes=0,
            )

    # Display
    display_report(cluster, total_waste, total_requested, ns_waste, recommendations, engine)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
