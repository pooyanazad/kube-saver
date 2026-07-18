"""YAML export helpers for kube-saver recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from kube_saver.models.core import Recommendation


@dataclass
class YamlExportResult:
    """Result of generating an optimized workload manifest."""

    manifest: dict[str, Any]
    yaml_text: str
    changes: list[str] = field(default_factory=list)
    valid: bool = True


@dataclass
class WorkloadPatchPlan:
    """Structured recommendation set for one workload."""

    namespace: str
    kind: str
    name: str
    cpu_request: str | None = None
    memory_request: str | None = None
    cpu_limit: str | None = None
    memory_limit: str | None = None
    comments: list[str] = field(default_factory=list)


@dataclass
class DryRunYamlExport:
    """Dry-run export preview."""

    changes: list[str] = field(default_factory=list)
    yaml_text: str = ""


def build_patch_plan(recommendations: list[Recommendation]) -> dict[tuple[str, str, str], WorkloadPatchPlan]:
    plans: dict[tuple[str, str, str], WorkloadPatchPlan] = {}
    for rec in recommendations:
        key = (rec.target_namespace, rec.target_kind, rec.target_name)
        plan = plans.setdefault(
            key,
            WorkloadPatchPlan(
                namespace=rec.target_namespace,
                kind=rec.target_kind,
                name=rec.target_name,
            ),
        )
        plan.comments.append(
            f"{rec.resource_type}: {rec.current_value} -> {rec.suggested_value}"
        )
        if rec.resource_type == "cpu-request":
            plan.cpu_request = rec.suggested_value
        elif rec.resource_type == "memory-request":
            plan.memory_request = rec.suggested_value
        elif rec.resource_type == "cpu-limit":
            plan.cpu_limit = rec.suggested_value
        elif rec.resource_type == "memory-limit":
            plan.memory_limit = rec.suggested_value
    return plans


def export_deployment_yaml(
    manifest: dict[str, Any],
    recommendations: list[Recommendation],
    *,
    dry_run: bool = False,
) -> YamlExportResult | DryRunYamlExport:
    """Generate optimized workload YAML from an existing manifest.

    Preserves labels/annotations by mutating only container resources.
    """
    manifest_copy = yaml.safe_load(yaml.safe_dump(manifest))
    patch_plans = build_patch_plan(recommendations)
    meta = manifest_copy.get("metadata", {})
    namespace = meta.get("namespace", "default")
    kind = manifest_copy.get("kind", "Deployment")
    name = meta.get("name", "")
    plan = patch_plans.get((namespace, kind, name))
    changes: list[str] = []
    if not plan:
        text = yaml.safe_dump(manifest_copy, sort_keys=False)
        result = YamlExportResult(manifest=manifest_copy, yaml_text=text, changes=[], valid=_is_valid_manifest(manifest_copy))
        return DryRunYamlExport(changes=[], yaml_text=text) if dry_run else result

    spec = manifest_copy.setdefault("spec", {})
    template = spec.setdefault("template", {})
    pod_spec = template.setdefault("spec", {})
    containers = pod_spec.setdefault("containers", [])

    for container in containers:
        resources = container.setdefault("resources", {})
        requests = resources.setdefault("requests", {})
        limits = resources.setdefault("limits", {})
        if plan.cpu_request:
            old = requests.get("cpu", "unset")
            requests["cpu"] = plan.cpu_request
            changes.append(f"cpu request: {old} -> {plan.cpu_request}")
        if plan.memory_request:
            old = requests.get("memory", "unset")
            requests["memory"] = plan.memory_request
            changes.append(f"memory request: {old} -> {plan.memory_request}")
        if plan.cpu_limit:
            old = limits.get("cpu", "unset")
            limits["cpu"] = plan.cpu_limit
            changes.append(f"cpu limit: {old} -> {plan.cpu_limit}")
        if plan.memory_limit:
            old = limits.get("memory", "unset")
            limits["memory"] = plan.memory_limit
            changes.append(f"memory limit: {old} -> {plan.memory_limit}")

    comment_lines = [f"# kube-saver: {line}" for line in plan.comments]
    yaml_body = yaml.safe_dump(manifest_copy, sort_keys=False)
    yaml_text = "\n".join(comment_lines + [yaml_body]) if comment_lines else yaml_body
    if dry_run:
        return DryRunYamlExport(changes=changes or plan.comments, yaml_text=yaml_text)
    return YamlExportResult(
        manifest=manifest_copy,
        yaml_text=yaml_text,
        changes=changes or plan.comments,
        valid=_is_valid_manifest(manifest_copy),
    )


def _is_valid_manifest(manifest: dict[str, Any]) -> bool:
    try:
        metadata = manifest["metadata"]
        spec = manifest["spec"]["template"]["spec"]
        containers = spec["containers"]
    except (KeyError, TypeError):
        return False
    return bool(metadata.get("name") and isinstance(containers, list) and containers)


__all__ = [
    "DryRunYamlExport",
    "WorkloadPatchPlan",
    "YamlExportResult",
    "build_patch_plan",
    "export_deployment_yaml",
]
