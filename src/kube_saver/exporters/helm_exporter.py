"""Helm values export helpers for kube-saver recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from kube_saver.exporters.yaml_exporter import build_patch_plan
from kube_saver.models.core import Recommendation


@dataclass
class HelmExportResult:
    """Generated Helm override values and diff lines."""

    chart_mode: str
    values: dict[str, Any]
    values_yaml: str
    diff_lines: list[str] = field(default_factory=list)


def export_helm_values(
    recommendations: list[Recommendation],
    *,
    namespace: str,
    workload_name: str,
    chart_mode: str = "helm3",
    with_comments: bool = True,
) -> HelmExportResult:
    """Generate a Helm values override file for one workload."""
    if chart_mode not in {"helm2", "helm3"}:
        raise ValueError("chart_mode must be 'helm2' or 'helm3'")

    plans = build_patch_plan(recommendations)
    matched = None
    for (ns, _kind, name), plan in plans.items():
        if ns == namespace and name == workload_name:
            matched = plan
            break

    values: dict[str, Any] = {
        "resources": {
            "requests": {},
            "limits": {},
        }
    }
    diff_lines: list[str] = []
    if matched:
        if matched.cpu_request:
            values["resources"]["requests"]["cpu"] = matched.cpu_request
        if matched.memory_request:
            values["resources"]["requests"]["memory"] = matched.memory_request
        if matched.cpu_limit:
            values["resources"]["limits"]["cpu"] = matched.cpu_limit
        if matched.memory_limit:
            values["resources"]["limits"]["memory"] = matched.memory_limit
        diff_lines = matched.comments[:]

    values_yaml = yaml.safe_dump(values, sort_keys=False)
    if with_comments and diff_lines:
        prefix = [f"# kube-saver ({chart_mode}): {line}" for line in diff_lines]
        values_yaml = "\n".join(prefix + [values_yaml])

    return HelmExportResult(
        chart_mode=chart_mode,
        values=values,
        values_yaml=values_yaml,
        diff_lines=diff_lines,
    )


__all__ = ["HelmExportResult", "export_helm_values"]
