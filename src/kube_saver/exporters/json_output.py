"""JSON serialization helpers for kube-saver automation outputs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from kube_saver.analyzers.cost_waste import CostWasteReport
from kube_saver.analyzers.resource_waste import ResourceWasteReport
from kube_saver.models.core import ClusterInfo, Recommendation


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def build_json_report(
    *,
    cluster: ClusterInfo | None,
    resource_report: ResourceWasteReport | None,
    cost_report: CostWasteReport | None,
    recommendations: list[Recommendation],
) -> dict[str, Any]:
    """Build structured JSON-compatible report output."""
    return {
        "cluster": _convert(cluster),
        "resource_report": _convert(resource_report),
        "cost_report": _convert(cost_report),
        "recommendations": [_convert(rec) for rec in recommendations],
    }


def _convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [_convert(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _convert(v) for k, v in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        raw = asdict(value)
        return {k: _convert(v) for k, v in raw.items()}
    return _json_default(value)


__all__ = ["build_json_report"]
