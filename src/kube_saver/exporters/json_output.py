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
    degraded: bool | None = None,
    degraded_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build structured JSON-compatible report output.

    Args:
        cluster: Cluster metadata (may be None).
        resource_report: Resource waste report (may be None).
        cost_report: Cost waste report (may be None).
        recommendations: List of recommendations.
        degraded: When True, the underlying pod scan was partial — the
            numbers are real but incomplete. ``None`` omits the field for
            backward compatibility with older callers.
        degraded_errors: One human-readable error string per failed
            namespace when ``degraded`` is True. ``None`` omits the field.

    Returns:
        A JSON-serializable dict. Always includes the four core sections;
        adds ``degraded`` and ``degraded_errors`` only when the scan was
        degraded so automation can rely on ``payload["degraded"] is True``.
    """
    payload: dict[str, Any] = {
        "cluster": _convert(cluster),
        "resource_report": _convert(resource_report),
        "cost_report": _convert(cost_report),
        "recommendations": [_convert(rec) for rec in recommendations],
    }
    if degraded is not None:
        payload["degraded"] = bool(degraded)
        payload["degraded_errors"] = list(degraded_errors or [])
    return payload


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
