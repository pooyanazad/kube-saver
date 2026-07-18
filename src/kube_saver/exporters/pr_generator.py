"""Git PR generation helpers for kube-saver."""

from __future__ import annotations

from dataclasses import dataclass, field

from kube_saver.models.core import Recommendation


@dataclass
class PullRequestPlan:
    """Dry-run or executable PR creation plan."""

    provider: str
    branch_name: str
    title: str
    body: str
    files: dict[str, str] = field(default_factory=dict)
    dry_run: bool = True


def generate_pr_plan(
    recommendations: list[Recommendation],
    *,
    provider: str = "github",
    branch_prefix: str = "kube-saver",
    dry_run: bool = True,
) -> PullRequestPlan:
    """Generate a PR plan without performing network calls."""
    if provider not in {"github", "gitlab"}:
        raise ValueError("provider must be 'github' or 'gitlab'")

    branch_name = f"{branch_prefix}/optimize-resources"
    title = "Apply kube-saver resource recommendations"
    lines = [
        "## Summary",
        f"- Recommendations: {len(recommendations)}",
        "",
        "## Before / After",
    ]
    for rec in recommendations:
        lines.append(
            f"- {rec.target_namespace}/{rec.target_kind}/{rec.target_name} {rec.resource_type}: {rec.current_value} -> {rec.suggested_value}"
        )
    lines.extend([
        "",
        "## Safety",
        f"- Dry run: {'yes' if dry_run else 'no'}",
    ])
    body = "\n".join(lines)
    files = {
        "kube-saver-pr-summary.txt": body,
    }
    return PullRequestPlan(
        provider=provider,
        branch_name=branch_name,
        title=title,
        body=body,
        files=files,
        dry_run=dry_run,
    )


__all__ = ["PullRequestPlan", "generate_pr_plan"]
