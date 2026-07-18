"""kube-saver CLI entry point.

Subcommands::

    kube-saver              Launch the TUI dashboard (default).
    kube-saver report       Generate self-contained HTML report.
    kube-saver pr-plan      Generate local PR plan files.
    kube-saver notify       Write daily summary + spike alert files.
    kube-saver serve        Start the HTTP API server.
    kube-saver version      Print version information.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from kube_saver import __version__
from kube_saver.analyzers.cost_waste import CostWasteReport, analyze_cost_waste
from kube_saver.analyzers.resource_waste import (
    ResourceWasteReport,
    analyze_resource_waste,
)
from kube_saver.collectors.k8s_client import K8sClient
from kube_saver.models.core import Recommendation
from kube_saver.pricing.engine import PricingEngine
from kube_saver.recommenders.engine import generate_recommendations

# ── Helpers ────────────────────────────────────────────────────────────────


def _run_analysis() -> tuple[ResourceWasteReport, CostWasteReport, list[Recommendation]]:
    """Run the full analysis pipeline."""
    client = K8sClient()
    client.connect()
    pods = client.get_all_pods()
    namespaces = client.get_namespaces()

    resource_report = analyze_resource_waste(namespaces, pods, metrics_available=True)
    pricing = PricingEngine()
    cost_report = analyze_cost_waste(resource_report, pricing)
    recs = generate_recommendations(resource_report, pricing)
    return resource_report, cost_report, recs


# ── Root group ────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """kube-saver: Kubernetes cost & waste analyzer."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)


# ── TUI (default) ────────────────────────────────────────────────────────


@cli.command()
def tui() -> None:
    """Launch the interactive TUI dashboard (default)."""
    from kube_saver.config import load_config
    try:
        from kube_saver.tui.app import KubeSaverApp
    except ImportError as exc:
        click.echo(f"Error: TUI dependencies missing: {exc}", err=True)
        click.echo("Install with: pip install kube-saver", err=True)
        raise SystemExit(1) from exc

    config = load_config()
    app = KubeSaverApp(config)
    app.run()


# ── Report ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("-o", "--output", default="kube-saver-report.html", help="Output HTML file path.")
def report(output: str) -> None:
    """Generate a self-contained HTML executive report."""
    resource_report, cost_report, recs = _run_analysis()
    from kube_saver.exporters.report_generator import generate_html_report
    result = generate_html_report(resource_report, cost_report, recs)
    Path(output).write_text(result.html, encoding="utf-8")
    click.echo(f"Report written to {output}")


# ── PR Plan ───────────────────────────────────────────────────────────────


@cli.command("pr-plan")
@click.option("-d", "--dir", "out_dir", default=".kube-saver", help="Output directory for plan files.")
def pr_plan(out_dir: str) -> None:
    """Generate local PR plan files (summary, patches, review)."""
    resource_report, cost_report, recs = _run_analysis()
    from kube_saver.exporters.pr_generator import apply_plan_locally, generate_pr_plan
    plan = generate_pr_plan(recs)
    path = apply_plan_locally(plan, output_dir=out_dir)
    click.echo(f"PR plan written to {path}/")
    click.echo("  - summary.md")
    click.echo("  - apply-patches.sh")
    click.echo("  - README.md")
    click.echo("  - review.txt")


# ── Notify ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("-d", "--dir", "out_dir", default="kube-saver-notifications", help="Output directory.")
@click.option("--threshold", default=100.0, help="Monthly USD threshold for spike alerts.")
def notify(out_dir: str, threshold: float) -> None:
    """Write daily summary + spike alert Markdown files to disk."""
    resource_report, cost_report, _recs = _run_analysis()
    from kube_saver.exporters.notifier import (
        build_daily_summary,
        build_spike_alert,
        write_notification,
    )

    summary = build_daily_summary(resource_report, cost_report)
    path = write_notification(summary, output_dir=out_dir)
    click.echo(f"Daily summary: {path}")

    spike = build_spike_alert(cost_report, threshold_monthly_usd=threshold)
    if spike is not None:
        path = write_notification(spike, output_dir=out_dir)
        click.echo(f"Spike alert:   {path}")
    else:
        click.echo(f"No spike alert (waste under ${threshold:.2f} threshold)")


# ── Serve ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("-p", "--port", default=8080, help="Port to listen on.")
@click.option("-b", "--bind", default="127.0.0.1", help="Address to bind to (default: loopback only).")
def serve(port: int, bind: str) -> None:
    """Start the HTTP API server."""
    from kube_saver.server import build_server

    if bind not in ("127.0.0.1", "localhost", "::1"):
        click.echo(
            f"WARNING: Binding to {bind} exposes the API on the network. "
            "kube-saver API has no authentication \u2014 use a reverse proxy for production.",
            err=True,
        )

    def _build_report() -> dict[str, object]:
        rr, cr, recs = _run_analysis()
        from kube_saver.exporters.json_output import build_json_report
        from kube_saver.models.core import ClusterInfo
        return build_json_report(
            cluster=ClusterInfo(name="", context=""),
            resource_report=rr,
            cost_report=cr,
            recommendations=recs,
        )

    server = build_server(report_builder=_build_report, host=bind, port=port)
    click.echo(f"kube-saver API listening on http://{bind}:{port}")
    click.echo("Endpoints: /healthz  /readyz  /api/v1/report  /openapi.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nShutting down.")
        server.shutdown()


# ── Version ───────────────────────────────────────────────────────────────


@cli.command()
def version() -> None:
    """Print kube-saver version."""
    click.echo(f"kube-saver {__version__}")


def main() -> int:
    """Entry point for ``kube-saver`` console script."""
    cli()
    return 0


if __name__ == "__main__":
    sys.exit(main())
