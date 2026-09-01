"""kube-saver CLI entry point.

Subcommands::

    kube-saver              Launch the TUI dashboard (default).
    kube-saver report       Generate self-contained HTML report.
    kube-saver pr-plan      Generate local PR plan files.
    kube-saver notify       Write daily summary + spike alert files.
    kube-saver serve        Start the HTTP API server.
    kube-saver doctor       Check kubeconfig + cluster connectivity + RBAC.
    kube-saver version      Print version information.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from kube_saver import __version__, exitcodes
from kube_saver.analyzers.cost_waste import CostWasteReport, analyze_cost_waste
from kube_saver.analyzers.resource_waste import (
    ResourceWasteReport,
    analyze_resource_waste,
)
from kube_saver.collectors.k8s_client import K8sClient
from kube_saver.models.core import Recommendation, ScanResult
from kube_saver.pricing.engine import PricingEngine
from kube_saver.recommenders.engine import generate_recommendations

# ── Helpers ────────────────────────────────────────────────────────────────


def _run_analysis() -> tuple[
    ResourceWasteReport, CostWasteReport, list[Recommendation], ScanResult
]:
    """Run the full analysis pipeline.

    Returns the resource report, cost report, recommendations, and the
    ``ScanResult`` from the pod scan so callers (the HTTP server) can
    surface ``degraded`` state in their JSON response.
    """
    from kube_saver.config import load_config
    config = load_config()
    client = K8sClient(timeouts=config.timeouts, retries=config.retries)
    client.connect()
    scan = client.get_all_pods()
    pods = scan.pods
    namespaces = client.get_namespaces()

    resource_report = analyze_resource_waste(namespaces, pods, metrics_available=True)
    pricing = PricingEngine()
    cost_report = analyze_cost_waste(resource_report, pricing)
    recs = generate_recommendations(resource_report, pricing, config=config)
    return resource_report, cost_report, recs, scan


def _safe_run_analysis() -> tuple[
    ResourceWasteReport, CostWasteReport, list[Recommendation], ScanResult
]:
    """Run the analysis pipeline and translate failures into stable exit codes.

    Maps underlying exceptions to documented exit codes so CI and automation
    can depend on them:

    * FileNotFoundError / kubernetes ConfigException -> CONFIG_ERROR (2)
    * ConnectionError / OSError / TimeoutError     -> CONNECTION_ERROR (3)
    * ApiException (HTTP 401/403)                  -> CONNECTION_ERROR (3)
    * ApiException (any other HTTP)                -> ANALYSIS_ERROR (4)
    * Any other exception                          -> GENERAL_ERROR (1)

    Note: a *partial* scan (``ScanResult.partial``) is not an error — the
    pipeline still completes and the ``ScanResult`` is returned so the
    degraded flag can surface in the HTTP response. Exit codes only fire
    when the pipeline cannot run at all.
    """
    # Resolve exception classes from the kubernetes package lazily so this
    # module can be imported without it installed.
    config_exc_cls: type | None = None
    api_exc_cls: type | None = None
    try:
        from kubernetes.client.rest import (  # type: ignore[import-untyped]
            ApiException as _ApiExc,
        )
        from kubernetes.config.config_exception import (  # type: ignore[import-untyped]
            ConfigException as _ConfigExc,
        )
        config_exc_cls = _ConfigExc
        api_exc_cls = _ApiExc
    except Exception:
        pass

    try:
        return _run_analysis()
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        click.echo(f"Error: kubeconfig not found — {exc}", err=True)
        click.echo(
            "Run `kube-saver doctor` to diagnose, or set KUBECONFIG to a valid file.",
            err=True,
        )
        raise SystemExit(exitcodes.CONFIG_ERROR) from exc
    except RuntimeError as exc:
        # Raised by K8sClient.connect() when the kubernetes package is missing.
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(exitcodes.CONFIG_ERROR) from exc
    except BaseException as exc:
        if config_exc_cls is not None and isinstance(exc, config_exc_cls):
            click.echo(
                f"Error: kubeconfig problem — {exc}",
                err=True,
            )
            click.echo(
                "Check that your kubeconfig exists and the requested context is spelled correctly.",
                err=True,
            )
            raise SystemExit(exitcodes.CONFIG_ERROR) from exc
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            click.echo(
                f"Error: cannot reach the Kubernetes API — {exc}",
                err=True,
            )
            click.echo(
                "Run `kube-saver doctor` to check connectivity. "
                "If running in a container, verify the kubeconfig mount.",
                err=True,
            )
            raise SystemExit(exitcodes.CONNECTION_ERROR) from exc
        if api_exc_cls is not None and isinstance(exc, api_exc_cls):
            status = getattr(exc, "status", None) or "unknown"
            if status in (401, 403):
                click.echo(
                    f"Error: API auth failure (HTTP {status}) — {exc}",
                    err=True,
                )
                click.echo(
                    "Check RBAC permissions. See: kube-saver doctor",
                    err=True,
                )
                raise SystemExit(exitcodes.CONNECTION_ERROR) from exc
            click.echo(
                f"Error: Kubernetes API returned HTTP {status} — {exc}",
                err=True,
            )
            raise SystemExit(exitcodes.ANALYSIS_ERROR) from exc
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(exitcodes.GENERAL_ERROR) from exc


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
    resource_report, cost_report, recs, _scan = _safe_run_analysis()
    from kube_saver.exporters.report_generator import generate_html_report
    result = generate_html_report(resource_report, cost_report, recs)
    Path(output).write_text(result.html, encoding="utf-8")
    click.echo(f"Report written to {output}")


# ── PR Plan ───────────────────────────────────────────────────────────────


@cli.command("pr-plan")
@click.option("-d", "--dir", "out_dir", default=".kube-saver", help="Output directory for plan files.")
def pr_plan(out_dir: str) -> None:
    """Generate local PR plan files (summary, patches, review)."""
    resource_report, cost_report, recs, _scan = _safe_run_analysis()
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
    resource_report, cost_report, _recs, _scan = _safe_run_analysis()
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
@click.option("--expose", is_flag=True, default=False, help="Confirm that you want to expose the API on the network.")
def serve(port: int, bind: str, expose: bool) -> None:
    """Start the HTTP API server.

    By default the API binds to 127.0.0.1 (loopback only) and is only
    reachable from the local machine. The API has no authentication, so
    exposing it on a network interface without a reverse proxy is unsafe.
    """
    from kube_saver.server import build_server

    is_loopback = bind in ("127.0.0.1", "localhost", "::1")

    if bind == "0.0.0.0":
        if not expose:
            click.echo(
                "Error: binding to 0.0.0.0 exposes the API on ALL network interfaces.\n"
                "The kube-saver API has no authentication — do this only behind a reverse proxy.\n\n"
                "If you understand the risk, use --expose to confirm.",
                err=True,
            )
            raise SystemExit(exitcodes.CONFIG_ERROR)
        click.echo(
            "WARNING: Binding to 0.0.0.0 — the API is reachable from every network interface.\n"
            "         No authentication is enforced. Use a reverse proxy with TLS and auth.",
            err=True,
        )
    elif not is_loopback:
        if not expose:
            click.echo(
                f"Error: binding to {bind} exposes the API on the network.\n"
                "The kube-saver API has no authentication.\n\n"
                "Use --expose to confirm, or leave the default loopback bind.",
                err=True,
            )
            raise SystemExit(exitcodes.CONFIG_ERROR)
        click.echo(
            f"WARNING: Binding to {bind} — the API is reachable on this network interface.\n"
            "         No authentication is enforced. Use a reverse proxy with TLS and auth.",
            err=True,
        )
    else:
        click.echo(f"API bound to loopback ({bind}) — only local access permitted.")

    def _build_report() -> dict[str, object]:
        rr, cr, recs, scan = _safe_run_analysis()
        from kube_saver.exporters.json_output import build_json_report
        from kube_saver.models.core import ClusterInfo
        return build_json_report(
            cluster=ClusterInfo(name="", context=""),
            resource_report=rr,
            cost_report=cr,
            recommendations=recs,
            degraded=scan.partial or scan.failed,
            degraded_errors=scan.errors,
        )

    server = build_server(report_builder=_build_report, host=bind, port=port)
    click.echo(f"kube-saver API listening on http://{bind}:{port}")
    click.echo("Endpoints: /healthz  /readyz  /api/v1/report  /openapi.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nShutting down.")
        server.shutdown()


# ── Doctor ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("-c", "--context", default=None, help="Kubeconfig context to check (default: current).")
def doctor(context: str | None) -> None:
    """Check kubeconfig, context, cluster connectivity, and required permissions."""
    from kube_saver.config import load_config
    from kube_saver.doctor import run_doctor

    config = load_config()
    use_color = sys.stdout.isatty()
    report = run_doctor(context=context, timeouts=config.timeouts)
    click.echo(report.render(use_color=use_color))
    if not report.ok:
        raise SystemExit(exitcodes.GENERAL_ERROR)


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
