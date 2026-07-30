"""Pre-flight diagnostics for kube-saver.

Provides the ``kube-saver doctor`` subcommand that checks:

1. kubeconfig presence and parsability
2. Active context selection
3. Cluster API reachability
4. Required RBAC permissions for the analyses kube-saver performs
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    """Outcome of a single diagnostic check."""

    name: str
    ok: bool
    detail: str = ""
    hint: str = ""

    def render(self, use_color: bool) -> str:
        marker = ("✓" if self.ok else "✗")
        if use_color:
            if self.ok:
                marker = f"\033[32m{marker}\033[0m"
                name_fmt = f"\033[1m{self.name}\033[0m"
            else:
                marker = f"\033[31m{marker}\033[0m"
                name_fmt = f"\033[1m\033[31m{self.name}\033[0m"
        else:
            name_fmt = self.name

        line = f"  {marker} {name_fmt}"
        if self.detail:
            line += f"\n      {self.detail}"
        if self.hint and not self.ok:
            line += f"\n      hint: {self.hint}"
        return line


@dataclass
class DoctorReport:
    """Aggregate result of running ``kube-saver doctor``."""

    kubeconfig_path: str | None = None
    context: str | None = None
    server_version: str | None = None
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def render(self, use_color: bool = True) -> str:
        lines: list[str] = []
        header = "kube-saver doctor"
        if use_color:
            header = f"\033[1m{header}\033[0m"
        lines.append(header)
        lines.append("-" * len("kube-saver doctor"))

        if self.kubeconfig_path:
            lines.append(f"kubeconfig: {self.kubeconfig_path}")
        if self.context:
            lines.append(f"context:    {self.context}")
        if self.server_version:
            lines.append(f"server:     {self.server_version}")

        lines.append("")
        for check in self.checks:
            lines.append(check.render(use_color))

        lines.append("")
        if self.ok:
            summary = "All checks passed. kube-saver is ready to run."
            if use_color:
                summary = f"\033[32m{summary}\033[0m"
        else:
            failed = sum(1 for c in self.checks if not c.ok)
            summary = f"{failed} check(s) failed. Resolve the issues above before running kube-saver."
            if use_color:
                summary = f"\033[31m{summary}\033[0m"
        lines.append(summary)
        return "\n".join(lines)


# ── Permission set ────────────────────────────────────────────────────────


# Resources + verbs that kube-saver needs to read for its default scan.
# Kept conservative — kube-saver is read-only.
REQUIRED_RBAC: list[tuple[str | None, str, str]] = [
    # (api_group, resource, verb)
    ("", "pods", "list"),
    ("", "pods", "get"),
    ("", "namespaces", "list"),
    ("", "nodes", "list"),
    ("apps", "deployments", "list"),
    ("apps", "deployments", "get"),
    ("apps", "replicasets", "list"),
    ("apps", "statefulsets", "list"),
    ("apps", "daemonsets", "list"),
    ("metrics.k8s.io", "pods", "list"),
    ("metrics.k8s.io", "nodes", "list"),
]


def _import_kubernetes() -> tuple[Any, Any, Any]:
    """Import the kubernetes client submodules.

    Returns ``(client, config, ApiException)`` or ``(None, None, None)`` if
    the package is not installed. Wrapped in a helper so tests can patch
    the module-level bindings.
    """
    try:
        from kubernetes import client as k8s_client  # type: ignore[import-untyped]
        from kubernetes import config as k8s_config
        from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]
        return k8s_client, k8s_config, ApiException
    except ImportError:
        return None, None, None


def _authorize_with(k8s_client: Any, kind: str, verb: str, api_group: str | None = None) -> bool:
    """Run a ``SelfSubjectAccessReview`` to check if the current subject can ``verb`` ``kind``."""
    try:
        resource_attrs = k8s_client.V1ResourceAttributes(
            resource=kind,
            verb=verb,
            group=api_group or "",
        )
        spec = k8s_client.V1SelfSubjectAccessReviewSpec(
            resource_attributes=resource_attrs,
        )
        review = k8s_client.V1SelfSubjectAccessReview(spec=spec)
        authorization = k8s_client.AuthorizationV1Api()
        response = authorization.create_self_subject_access_review(review)
        return bool(response.status and response.status.allowed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SAR for %s/%s failed: %s", kind, verb, exc)
        return False


# ── Main runner ───────────────────────────────────────────────────────────


def _resolve_kubeconfig_path() -> str | None:
    """Find the kubeconfig path that kube-saver would use."""
    explicit = os.environ.get("KUBECONFIG")
    if explicit:
        # KUBECONFIG may contain multiple paths; use the first existing one.
        for part in explicit.split(os.pathsep):
            if part and Path(part).exists():
                return part
        return explicit.split(os.pathsep)[0] or None
    default = Path.home() / ".kube" / "config"
    return str(default)


def run_doctor(context: str | None = None) -> DoctorReport:
    """Execute every doctor check and return a ``DoctorReport``.

    The function never raises — every check produces a ``CheckResult`` so the
    caller can render all results even if some fail.
    """
    report = DoctorReport()
    report.kubeconfig_path = _resolve_kubeconfig_path()
    report.context = context or "default"

    # ── Check 1: kubeconfig file ──────────────────────────────────────────
    if report.kubeconfig_path and Path(report.kubeconfig_path).exists():
        report.checks.append(
            CheckResult(
                name="kubeconfig",
                ok=True,
                detail=f"found at {report.kubeconfig_path}",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                name="kubeconfig",
                ok=False,
                detail=f"not found at {report.kubeconfig_path or '~/.kube/config'}",
                hint="set KUBECONFIG or run `kubectl config view` to verify your setup",
            )
        )
        # Without kubeconfig nothing else can succeed — short-circuit.
        return report

    # ── Check 2: load kubeconfig ──────────────────────────────────────────
    k8s_client, k8s_config, api_exception = _import_kubernetes()
    if k8s_client is None or k8s_config is None:
        report.checks.append(
            CheckResult(
                name="kubernetes client",
                ok=False,
                detail="the 'kubernetes' Python package is not installed",
                hint="pip install kube-saver",
            )
        )
        return report
    assert k8s_client is not None
    assert k8s_config is not None

    try:
        if context:
            k8s_config.load_kube_config(context=context)
        else:
            # Prefer explicit kubeconfig if we resolved one ourselves.
            try:
                k8s_config.load_kube_config(
                    config_file=report.kubeconfig_path,
                    context=None,
                )
            except k8s_config.ConfigException:
                # In-cluster fallback (will only work if running inside a pod).
                k8s_config.load_incluster_config()
    except k8s_config.ConfigException as exc:
        report.checks.append(
            CheckResult(
                name="kubeconfig parses",
                ok=False,
                detail=str(exc),
                hint="verify the file syntax with `kubectl config view`",
            )
        )
        return report

    # ── Check 3: active context resolves ──────────────────────────────────
    try:
        active = k8s_config.list_kube_config_contexts(config_file=report.kubeconfig_path)
        contexts = [c.get("name") for c in (active[0] if active else [])]
        current = active[1] if len(active) > 1 else None
        current_name = current.get("name") if current else None
        if context and context not in contexts:
            report.checks.append(
                CheckResult(
                    name="context",
                    ok=False,
                    detail=f"context '{context}' not in kubeconfig",
                    hint=f"available contexts: {', '.join(contexts) or '(none)'}",
                )
            )
            return report
        report.context = current_name or context or "default"
        report.checks.append(
            CheckResult(
                name="context",
                ok=True,
                detail=f"active context is '{report.context}'",
            )
        )
    except Exception as exc:  # noqa: BLE001
        report.checks.append(
            CheckResult(
                name="context",
                ok=False,
                detail=f"could not list contexts: {exc}",
                hint="run `kubectl config get-contexts` to inspect your kubeconfig",
            )
        )
        return report

    # ── Check 4: cluster reachability ─────────────────────────────────────
    assert api_exception is not None
    try:
        version_api = k8s_client.VersionApi()
        version_info = version_api.get_code()
        git_version = getattr(version_info, "git_version", None) or "unknown"
        report.server_version = git_version
        report.checks.append(
            CheckResult(
                name="cluster reachable",
                ok=True,
                detail=f"server reports {git_version}",
            )
        )
    except api_exception as exc:
        report.checks.append(
            CheckResult(
                name="cluster reachable",
                ok=False,
                detail=f"API server unreachable: {exc}",
                hint="check VPN, network policies, and the API server endpoint",
            )
        )
        return report
    except Exception as exc:  # noqa: BLE001
        report.checks.append(
            CheckResult(
                name="cluster reachable",
                ok=False,
                detail=str(exc),
                hint="check that kubectl cluster-info works in this context",
            )
        )
        return report

    # ── Check 5: required RBAC permissions ────────────────────────────────
    for api_group, kind, verb in REQUIRED_RBAC:
        display_name = f"{api_group}/{kind}" if api_group else kind
        if _authorize_with(k8s_client, kind, verb, api_group=api_group or None):
            report.checks.append(
                CheckResult(
                    name=f"rbac {verb} {display_name}",
                    ok=True,
                    detail="allowed",
                )
            )
        else:
            report.checks.append(
                CheckResult(
                    name=f"rbac {verb} {display_name}",
                    ok=False,
                    detail="denied",
                    hint=(
                        f"grant the service account permission to {verb} {display_name} "
                        "cluster-wide (e.g. via 'view' ClusterRole)"
                    ),
                )
            )

    return report


__all__ = [
    "CheckResult",
    "DoctorReport",
    "REQUIRED_RBAC",
    "_import_kubernetes",
    "_authorize_with",
    "run_doctor",
]
