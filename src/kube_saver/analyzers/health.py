"""Health scoring for kube-saver.

Phase 2 — Step 13.
"""

from __future__ import annotations

from kube_saver.analyzers.resource_waste import PodWaste


def pod_health_score(pw: PodWaste) -> float:
    """Return a 0-100 efficiency score for a pod.

    Higher is better.
    """
    score = 100.0

    score -= pw.cpu_waste_ratio * 50
    score -= pw.memory_waste_ratio * 40

    if pw.pod.had_oom_events:
        score -= 25

    if not pw.has_usage_data:
        score -= 10

    return round(max(min(score, 100.0), 0.0), 1)
